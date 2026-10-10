"""Settings from the environment (and backend/.env, which is gitignored).

One frozen object, built once by ``load_settings``. Nothing else in the package reads
``os.environ``; every other module takes a ``Settings`` (or the one field it needs).
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEMO_DATA_DIR = Path(__file__).resolve().parent / "data" / "demo"


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    # LLM
    llm_provider: str = "ollama"
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "qwen3.5:2b-mlx"
    llm_reasoning_effort: str = "none"
    llm_api_key: str = Field(default="", repr=False)
    llm_timeout_seconds: float = 120.0

    # Our MCP tool server
    mcp_server_host: str = "127.0.0.1"
    mcp_server_port: int = 8765
    mcp_server_url: str = "http://127.0.0.1:8765/mcp"

    # AgntID runtime (phase c)
    agntid_mcp_url: str = "http://localhost:8082/mcp"
    agntid_access_token: str = Field(default="", repr=False)

    # Behaviour
    payment_limit_inr: float = 10_000.0
    agent_concurrency: int = 1
    agent_max_turns: int = 4
    cache_dir: Path = Path(".cache")
    nonce_secret: str = Field(default="whosaid-demo-nonce-secret", repr=False)
    log_level: str = "INFO"


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    return default if value is None or value.strip() == "" else value.strip()


def load_settings(env_file: Path | None = None) -> Settings:
    """Read settings. A real environment export always wins over the .env file."""
    load_dotenv(env_file or BACKEND_DIR / ".env", override=False)
    d = Settings()
    return Settings(
        llm_provider=_env("LLM_PROVIDER", d.llm_provider),
        llm_base_url=_env("LLM_BASE_URL", d.llm_base_url),
        llm_model=_env("LLM_MODEL", d.llm_model),
        llm_reasoning_effort=_env("LLM_REASONING_EFFORT", d.llm_reasoning_effort),
        llm_api_key=_env("LLM_API_KEY", ""),
        llm_timeout_seconds=float(_env("LLM_TIMEOUT_SECONDS", str(d.llm_timeout_seconds))),
        mcp_server_host=_env("MCP_SERVER_HOST", d.mcp_server_host),
        mcp_server_port=int(_env("MCP_SERVER_PORT", str(d.mcp_server_port))),
        mcp_server_url=_env("MCP_SERVER_URL", d.mcp_server_url),
        agntid_mcp_url=_env("AGNTID_MCP_URL", d.agntid_mcp_url),
        agntid_access_token=_env("AGNTID_ACCESS_TOKEN", ""),
        payment_limit_inr=float(_env("PAYMENT_LIMIT_INR", str(d.payment_limit_inr))),
        agent_concurrency=int(_env("AGENT_CONCURRENCY", str(d.agent_concurrency))),
        cache_dir=Path(_env("CACHE_DIR", str(d.cache_dir))),
        nonce_secret=_env("NONCE_SECRET", d.nonce_secret),
        log_level=_env("LOG_LEVEL", d.log_level).upper(),
    )
