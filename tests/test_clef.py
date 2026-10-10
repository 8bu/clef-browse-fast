import json

import httpx
import pytest

from clef_browse.clef import (
    ClefBadResponse,
    ClefClient,
    ClefConfig,
    ClefError,
    ClefUnavailable,
    cost_usd,
    make_decider,
    validate_choice,
)


def _config(**overrides):
    values = {"account_id": "account", "token": "secret", **overrides}
    return ClefConfig(**values)


def _answer(choice, probabilities, confidence=0.9):
    return {"type": "choice", "choice": choice, "probabilities": probabilities, "confidence": confidence}


def _state(actions=None, text="page text"):
    return {
        "url": "https://example.test/",
        "title": "Example",
        "text": text,
        "actions": actions or [],
    }


def _click_action(node="button", label="Save"):
    return {"id": f"click-{label.lower()}", "kind": "click", "node": node, "label": label, "role": "button"}


def test_run_accepts_both_response_envelopes_and_reports_usage():
    payloads = iter(
        [
            {"model": "clef", "answers": {"q": 1}, "usage": {"input_tokens": 12, "output_tokens": 3}},
            {
                "success": True,
                "result": {"model": "clef", "answers": {"q": 2}, "usage": {"input_tokens": 4}},
                "errors": [],
            },
        ]
    )
    client = ClefClient(_config(), transport=httpx.MockTransport(lambda _: httpx.Response(200, json=next(payloads))))
    assert client.run({"q": {"type": "choice"}}, {"page": {}}) == {"q": 1}
    assert client.last_meta["input_tokens"] == 12
    assert client.last_meta["output_tokens"] == 3
    assert client.run({"q": {"type": "choice"}}, {"page": {}}) == {"q": 2}
    assert client.last_meta["input_tokens"] == 4
    client.close()


def test_cloudflare_failure_raises_response_error():
    client = ClefClient(
        _config(),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"success": False, "errors": [{"message": "bad"}]})
        ),
    )
    with pytest.raises(ClefBadResponse, match="bad"):
        client.run({"q": {}}, {})
    client.close()


def test_retry_503_then_success_sleeps_and_records_attempts(monkeypatch):
    responses = iter([httpx.Response(503), httpx.Response(200, json={"answers": {"q": "ok"}, "usage": {}})])
    delays = []
    monkeypatch.setattr("clef_browse.clef.time.sleep", delays.append)
    client = ClefClient(_config(), transport=httpx.MockTransport(lambda _: next(responses)))
    assert client.run({"q": {}}, {}) == {"q": "ok"}
    assert delays == [0.5]
    assert client.last_meta["attempts"] == 2
    client.close()


def test_non_retryable_4xx_is_not_retried():
    attempts = 0

    def respond(_):
        nonlocal attempts
        attempts += 1
        return httpx.Response(400, json={"error": "invalid"})

    client = ClefClient(_config(), transport=httpx.MockTransport(respond))
    with pytest.raises(ClefBadResponse, match="400"):
        client.run({"q": {}}, {})
    assert attempts == 1
    client.close()


def test_429_retries_then_raises_unavailable(monkeypatch):
    attempts = 0
    delays = []

    def respond(_):
        nonlocal attempts
        attempts += 1
        return httpx.Response(429)

    monkeypatch.setattr("clef_browse.clef.time.sleep", delays.append)
    client = ClefClient(_config(max_attempts=3), transport=httpx.MockTransport(respond))
    with pytest.raises(ClefUnavailable):
        client.run({"q": {}}, {})
    assert attempts == 3
    assert delays == [0.5, 1.0]
    client.close()


@pytest.mark.parametrize(
    "answer,ids",
    [
        (_answer("a", {"a": 0.5, "b": 0.4}), ["a", "b"]),
        (_answer("b", {"a": 0.6, "b": 0.4}), ["a", "b"]),
        (_answer("a", {"a": 0.7, "b": 0.3}), ["a", "b", "c"]),
    ],
)
def test_choice_validation_rejects_bad_probability_sets(answer, ids):
    with pytest.raises(ClefBadResponse):
        validate_choice(answer, ids)


def test_choice_validation_accepts_probability_sum_tolerance():
    answer = _answer("a", {"a": 0.6, "b": 0.41})
    assert validate_choice(answer, ["a", "b"]) == answer


def test_single_candidate_adds_none_choice_and_returns_none_without_action():
    def respond(request):
        body = json.loads(request.content)
        options = body["questions"]["click_target"]["criteria"]
        assert set(options) == {"1", "none"}
        return httpx.Response(
            200,
            json={
                "model": "clef",
                "answers": {
                    "operation": _answer("CLICK", {"CLICK": 0.9, "DONE": 0.05, "BLOCKED": 0.05}),
                    "click_target": _answer("none", {"1": 0.01, "none": 0.99}),
                },
                "usage": {"input_tokens": 19, "output_tokens": 5},
            },
        )

    client = ClefClient(_config(), transport=httpx.MockTransport(respond))
    decision = make_decider(client)(_state([_click_action()]), "Save", [])
    assert decision["choice"] == "none"
    assert decision["target"] == "none"
    assert decision["_meta"]["input_tokens"] == 19
    assert decision["_meta"]["output_tokens"] == 5
    assert decision["_meta"]["attempts"] == 1
    assert decision["_meta"]["elements_offered"] == 1
    client.close()


def test_state_truncation_keeps_question_ids_aligned():
    received = {}

    def respond(request):
        body = json.loads(request.content)
        received.update(body)
        target_options = body["questions"]["click_target"]["criteria"]
        target_probs = {option: (0.99 if option == "1" else 0.01) for option in target_options}
        return httpx.Response(
            200,
            json={
                "answers": {
                    "operation": _answer("CLICK", {"CLICK": 0.9, "DONE": 0.05, "BLOCKED": 0.05}),
                    "click_target": _answer("1", target_probs),
                },
                "usage": {},
            },
        )

    actions = [_click_action("first", "First"), _click_action("second", "Second")]
    client = ClefClient(_config(state_max_chars=260), transport=httpx.MockTransport(respond))
    decision = make_decider(client)(_state(actions, text="x" * 500), "click first", [])
    state = received["state"]
    target_options = received["questions"]["click_target"]["criteria"]
    assert len(json.dumps(state)) <= 260
    assert set(target_options) == {"1", "none"}
    assert set(target_options) - {"none"} <= {element["index"] for element in state["elements"]}
    assert decision["_meta"]["state_chars"] <= 260
    assert decision["choice"] == "click-first"
    client.close()


def test_only_the_clef_model_is_accepted():
    for model in ("clef-flash", "clef-omni", ""):
        with pytest.raises(ClefError, match="only 'clef' is supported"):
            ClefConfig(account_id="account", token="secret", model=model)
    env = {"CLOUDFLARE_ACCOUNT_ID": "account", "CLOUDFLARE_AUTH_TOKEN": "secret"}
    with pytest.raises(ClefError, match="only 'clef' is supported"):
        ClefConfig.from_env({**env, "CLEF_MODEL": "clef-flash"})
    with pytest.raises(ClefError, match="CLEF_ESCALATION_MODEL is no longer supported"):
        ClefConfig.from_env({**env, "CLEF_ESCALATION_MODEL": "clef"})
    assert ClefConfig.from_env(env).model == "clef"


def test_from_env_missing_credentials_does_not_expose_values(capsys):
    with pytest.raises(ClefError) as error:
        ClefConfig.from_env({"CLOUDFLARE_ACCOUNT_ID": "account-secret"})
    assert "account-secret" not in str(error.value)
    assert capsys.readouterr().out == ""


def test_cost_uses_the_clef_input_price():
    assert cost_usd(1_000_000) == 0.24

    def respond(request):
        answers = {"operation": _answer("DONE", {"DONE": 0.9, "BLOCKED": 0.1}, 0.9)}
        return httpx.Response(200, json={"model": "clef", "answers": answers, "usage": {"input_tokens": 1000}})

    client = ClefClient(_config(), transport=httpx.MockTransport(respond))
    decision = make_decider(client)(_state(), "finish", [])
    assert decision["_meta"]["cost_usd"] == pytest.approx(0.00024)
    client.close()
