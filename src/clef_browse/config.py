import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunLimits:
    max_steps: int = 60
    timeout_s: float = 180.0
    max_model_calls: int = 120
    settle_ms: int = 500

    @classmethod
    def from_env(cls) -> "RunLimits":
        return cls(
            max_steps=int(os.environ.get("CLEF_BROWSE_MAX_STEPS", "60")),
            timeout_s=float(os.environ.get("CLEF_BROWSE_TIMEOUT_S", "180")),
            max_model_calls=int(os.environ.get("CLEF_BROWSE_MAX_MODEL_CALLS", "120")),
            settle_ms=int(os.environ.get("CLEF_BROWSE_SETTLE_MS", "500")),
        )


def load_dotenv(path: str | Path = ".env") -> None:
    file_path = Path(path)
    if not file_path.is_file():
        return
    for line in file_path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if not value or value.startswith("#") or "=" not in value:
            continue
        key, item = value.split("=", 1)
        key, item = key.strip(), item.strip()
        if not key or key in os.environ:
            continue
        if len(item) >= 2 and item[0] == item[-1] and item[0] in "\"'":
            item = item[1:-1]
        os.environ[key] = item


def neo_urls() -> tuple[str, str]:
    return (
        os.environ.get("BROWSEROS_NEO_MCP_URL", "http://127.0.0.1:9010/mcp"),
        os.environ.get("BROWSEROS_NEO_CDP_URL", "http://127.0.0.1:9111"),
    )
