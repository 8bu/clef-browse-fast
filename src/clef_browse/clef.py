from __future__ import annotations

import json
import math
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from jev_ultrafast.model import action_space
from jev_ultrafast.questions import NEXT_ACTION, TARGET


class ClefError(RuntimeError):
    pass


class ClefUnavailable(ClefError):
    pass


class ClefBadResponse(ClefError):
    pass


@dataclass(frozen=True)
class ClefConfig:
    account_id: str
    token: str
    model: str = "clef"
    timeout_s: float = 20.0
    max_attempts: int = 3
    state_max_chars: int = 48_000
    base_url: str = "https://api.cloudflare.com/client/v4"

    def __post_init__(self):
        if self.model != "clef":
            raise ClefError(f"Unsupported CLEF_MODEL {self.model!r}; only 'clef' is supported")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> ClefConfig:
        values = os.environ if env is None else env
        account = values.get("CLOUDFLARE_ACCOUNT_ID")
        token = values.get("CLOUDFLARE_AUTH_TOKEN")
        if not account or not token:
            raise ClefError("CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_AUTH_TOKEN are required")
        if values.get("CLEF_ESCALATION_MODEL"):
            raise ClefError("CLEF_ESCALATION_MODEL is no longer supported; only the clef model is used")
        return cls(
            account_id=account,
            token=token,
            model=values.get("CLEF_MODEL", "clef"),
        )


class ClefClient:
    def __init__(self, config: ClefConfig, *, transport: httpx.BaseTransport | None = None):
        self.config = config
        self._client = httpx.Client(http2=True, timeout=config.timeout_s, transport=transport)
        self.last_meta: dict[str, Any] = {}

    def close(self) -> None:
        self._client.close()

    def _endpoint(self, model: str) -> str:
        if model != "clef":
            raise ClefBadResponse("Unsupported Clef model")
        return f"{self.config.base_url.rstrip('/')}/accounts/{self.config.account_id}/ai/run/@cf/cloudflare/clef"

    @staticmethod
    def _normalize(payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ClefBadResponse("Clef response must be an object")
        if "success" in payload:
            if payload.get("success") is not True:
                raise ClefBadResponse("Cloudflare request failed: " + json.dumps(payload.get("errors", [])))
            payload = payload.get("result")
        if not isinstance(payload, dict) or not isinstance(payload.get("answers"), dict):
            raise ClefBadResponse("Clef response is missing answers")
        return payload

    def run(self, questions: dict, state: Any, instructions_unused=None) -> dict:
        return self._run_as_model(questions, state, self.config.model)

    def _run_as_model(self, questions: dict, state, model: str) -> dict:
        request_state = _bounded_state(state, questions, self.config.state_max_chars)
        body = {"model": model, "state": request_state, "questions": questions}
        result, model, attempts = self._request(body, model)
        answers = result["answers"]
        usage = result.get("usage", {})
        self.last_meta = {
            "model": result.get("model", model),
            "input_tokens": _token_count(usage.get("input_tokens", 0)),
            "output_tokens": _token_count(usage.get("output_tokens", 0)),
            "attempts": attempts,
            "state_chars": len(json.dumps(request_state, ensure_ascii=False)),
            "elements_offered": len(request_state.get("elements", [])) if isinstance(request_state, dict) else 0,
            "usage": usage,
        }
        self.last_meta["cost_usd"] = cost_usd(self.last_meta["input_tokens"])
        return answers

    def _request(self, body: dict, model: str) -> tuple[dict, str, int]:
        url = self._endpoint(model)
        request_body = {**body, "model": model}
        for attempt in range(self.config.max_attempts):
            try:
                response = self._client.post(
                    url,
                    json=request_body,
                    headers={"Authorization": f"Bearer {self.config.token}"},
                )
            except httpx.TransportError:
                if attempt + 1 == self.config.max_attempts:
                    raise ClefUnavailable("Clef connection failed") from None
                time.sleep(0.5 * 2**attempt)
                continue
            if response.status_code in {429, 500, 502, 503, 504, 529}:
                if attempt + 1 == self.config.max_attempts:
                    raise ClefUnavailable(f"Clef unavailable (HTTP {response.status_code})")
                time.sleep(0.5 * 2**attempt)
                continue
            if response.is_error:
                raise ClefBadResponse(f"Clef returned HTTP {response.status_code}")
            try:
                return self._normalize(response.json()), model, attempt + 1
            except (ValueError, json.JSONDecodeError) as exc:
                raise ClefBadResponse("Clef returned invalid JSON") from exc
        raise ClefUnavailable("Clef unavailable")


def validate_choice(answer: dict, ids: Any) -> dict:
    try:
        probabilities = answer["probabilities"]
        numbers = [*probabilities.values(), answer["confidence"]]
        valid = (
            answer["type"] == "choice"
            and answer["choice"] in ids
            and set(probabilities) == set(ids)
            and all(type(number) in (int, float) and math.isfinite(number) and 0 <= number <= 1 for number in numbers)
            and abs(sum(probabilities.values()) - 1) < 0.02
            and probabilities[answer["choice"]] >= max(probabilities.values()) - 1e-6
        )
    except (AttributeError, KeyError, OverflowError, TypeError, ValueError):
        valid = False
    if not valid:
        raise ClefBadResponse("Invalid Clef choice response")
    return answer


def choose(state: dict, goal: str, history: list) -> dict:
    return _choose(state, goal, history, _default_client())


def _choose(state, goal, history, client: ClefClient) -> dict:
    selected_client = client
    elements, targets, controls = action_space(state["actions"])
    labels = {
        "CLICK": "Click an element, button, menu option, autocomplete suggestion, or calendar day.",
        "TYPE_TEXT": "Enter or replace text in an editable field. A small LLM will supply the value from the goal.",
        "SELECT": "Select an observed dropdown value.",
    }
    operations = {key: labels[key] for key in targets}
    operations.update({key: value["label"] for key, value in controls.items()})
    operations.update(DONE="Every requirement is visibly satisfied.", BLOCKED="No supported operation can progress.")
    questions = {
        "operation": {
            "type": "choice",
            "criteria": operations,
            "instructions": _instructions({"goal": goal, "rules": NEXT_ACTION}),
        }
    }
    target_ids: dict[str, dict[str, dict]] = {}
    for operation, candidates in targets.items():
        identifier = operation.lower() + "_target"
        options = {
            index: {
                "element": f"[{index}] {action['label']}",
                "current_value": action.get("current_value", action.get("value", "")),
                **{key: action[key] for key in ("role", "checked", "selected", "expanded") if key in action},
            }
            for index, action in candidates.items()
        }
        if len(options) == 1:
            options["none"] = "no suitable element"
        target_ids[operation] = candidates
        questions[identifier] = {
            "type": "choice",
            "criteria": options,
            "instructions": _instructions({"goal": goal, "operation": operation, "rules": [NEXT_ACTION, TARGET]}),
        }
    request_state = {
        "page": {key: state[key] for key in ("url", "title", "text")},
        "elements": elements,
        "recent_actions": [
            {key: item.get(key) for key in ("action", "kind", "text", "page_changed")} for item in history[-10:]
        ],
    }
    request_state = _bounded_state(request_state, questions, selected_client.config.state_max_chars)
    # Keep target options aligned with the elements retained by the state cap.
    offered = {str(element["index"]) for element in request_state.get("elements", [])}
    for operation, candidates in list(target_ids.items()):
        identifier = operation.lower() + "_target"
        criteria = questions[identifier]["criteria"]
        for index in list(candidates):
            if index.split(":", 1)[0] not in offered:
                candidates.pop(index, None)
                criteria.pop(index, None)
        if len(criteria) == 1 and "none" not in criteria:
            criteria["none"] = "no suitable element"
        if len(criteria) < 2:
            del questions[identifier]
            del operations[operation]
            target_ids.pop(operation)
    questions["operation"]["criteria"] = operations
    started = time.perf_counter()
    answers = selected_client.run(questions, request_state)
    first_meta = selected_client.last_meta.copy()
    operation_answer = validate_choice(answers.get("operation", {}), operations)
    operation = operation_answer["choice"]
    target = None
    target_answer = None
    probabilities = {}
    if operation in targets:
        target_key = operation.lower() + "_target"
        target_answer = validate_choice(answers.get(target_key, {}), questions[target_key]["criteria"])
        target = target_answer["choice"]
        if target != "none":
            selected_action = targets[operation][target]
            choice = selected_action["id"]
            probabilities = {
                action["id"]: target_answer["probabilities"][index] for index, action in targets[operation].items()
            }
        else:
            choice = "none"
            probabilities = {"none": target_answer["probabilities"]["none"]}
    else:
        choice = controls[operation]["id"] if operation in controls else operation
        probabilities[choice] = operation_answer["probabilities"][operation]
    confidence = operation_answer["confidence"]
    final_meta = first_meta
    return {
        "choice": choice,
        "operation": operation,
        "target": target,
        "confidence": confidence,
        "probabilities": probabilities,
        "operation_probabilities": operation_answer["probabilities"],
        "target_probabilities": target_answer["probabilities"] if target_answer else {},
        "target_confidence": target_answer["confidence"] if target_answer else None,
        "raw_answers": answers,
        "model": final_meta["model"],
        "usage": final_meta.get("usage", {}),
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "request": {"model": final_meta["model"], "state": request_state, "questions": questions},
        "_meta": {
            "model": final_meta["model"],
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "input_tokens": final_meta["input_tokens"],
            "output_tokens": final_meta["output_tokens"],
            "attempts": final_meta["attempts"],
            "cost_usd": final_meta["cost_usd"],
            "state_chars": final_meta["state_chars"],
            "elements_offered": final_meta["elements_offered"],
        },
    }


def _instructions(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _token_count(value: Any) -> int:
    return value if type(value) is int and value >= 0 else 0


def _bounded_state(state: Any, questions: dict, max_chars: int) -> Any:
    if max_chars <= 0:
        raise ClefBadResponse("state_max_chars must be positive")
    result = json.loads(json.dumps(state, ensure_ascii=False))

    def size() -> int:
        return len(json.dumps(result, ensure_ascii=False))

    page = result.get("page") if isinstance(result, dict) else None
    if isinstance(page, dict) and isinstance(page.get("text"), str) and size() > max_chars:
        text = page["text"]
        low, high = 0, len(text)
        while low < high:
            middle = (low + high + 1) // 2
            page["text"] = text[:middle]
            if size() <= max_chars:
                low = middle
            else:
                high = middle - 1
        page["text"] = text[:low]
    elements = result.get("elements") if isinstance(result, dict) else None
    while size() > max_chars and isinstance(elements, list) and elements:
        removed = elements.pop()
        index = str(removed.get("index", ""))
        for question in questions.values():
            criteria = question.get("criteria") if isinstance(question, dict) else None
            if isinstance(criteria, dict):
                for key in list(criteria):
                    if key.split(":", 1)[0] == index:
                        del criteria[key]
    while size() > max_chars and isinstance(result, dict) and result.get("recent_actions"):
        result["recent_actions"].pop(0)
    if size() > max_chars and isinstance(page, dict):
        page["text"] = ""
        for key in ("title", "url"):
            if size() > max_chars:
                page[key] = ""
    if size() > max_chars:
        raise ClefBadResponse("Structured decision state exceeds state_max_chars")
    return result


def _default_client() -> ClefClient:
    global _SHARED_CLIENT
    if _SHARED_CLIENT is None:
        _SHARED_CLIENT = ClefClient(ClefConfig.from_env())
    return _SHARED_CLIENT


_SHARED_CLIENT: ClefClient | None = None


def make_decider(client: ClefClient | None = None) -> Callable[[dict, str, list], dict]:
    bound_client = client or _default_client()

    def decider(state, goal, history):
        return _choose(state, goal, history, bound_client)

    return decider


# USD per 1M input tokens, from https://developers.cloudflare.com/workers-ai/platform/pricing/ (output is free).
CLEF_INPUT_USD_PER_M = 0.24


def cost_usd(input_tokens: int) -> float:
    return input_tokens * CLEF_INPUT_USD_PER_M / 1_000_000
