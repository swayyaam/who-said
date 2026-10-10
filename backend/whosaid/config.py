"""Settings from the environment (and backend/.env, which is gitignored).

One frozen object, built once by ``load_settings``. Nothing else in the package reads
``os.environ``; every other module takes a ``Settings`` (or the one field it needs).
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from whosaid.schemas import Enforcement

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEMO_DATA_DIR = Path(__file__).resolve().parent / "data" / "demo"
# Committed LLM answers for the demo dataset only (not covered by the .cache/ gitignore).
DEMO_FIXTURE_DIR = DEMO_DATA_DIR / "cache"


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
    # Shared secret for the tool server's /mcp endpoint: the AgntID runtime's bearer credential.
    # Empty means "no check" (tests, quick local use). The separate secret for the AgntID-OFF demo
    # path is deliberately NOT here: see direct_access_secret().
    tool_server_secret: str = Field(default="", repr=False)
    # The tool server only honours the OFF-mode (direct) secret when this is true. A production
    # deployment leaves it false, which removes the bypass entirely.
    demo_allow_direct: bool = False

    # AgntID runtime (phase c)
    agntid_mcp_url: str = "http://localhost:8082/mcp"
    agntid_access_token: str = Field(default="", repr=False)

    # Profile learning (see whosaid.profile.params)
    profile_min_alpha: float = 0.1
    profile_min_evidence: int = 2
    profile_downgrade_below: float = -0.4
    profile_mute_below: float = -0.7
    profile_upgrade_above: float = 0.6

    # API server
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"  # the Vite dev server

    # Behaviour
    payment_limit_inr: float = 10_000.0
    agent_concurrency: int = 1
    agent_max_turns: int = 4
    cache_dir: Path = Path(".cache")
    nonce_secret: str = Field(default="whosaid-demo-nonce-secret", repr=False)
    log_level: str = "INFO"


def direct_access_secret(enforcement: "Enforcement") -> str:
    """The credential for the direct (AgntID OFF) path to the tool server.

    Read from the environment ONLY when enforcement is OFF. With enforcement ON this returns ""
    without touching the environment, so the ON path can never hold the bypass credential.
    """
    from whosaid.schemas import Enforcement

    if enforcement is not Enforcement.OFF:
        return ""
    return os.environ.get("DIRECT_ACCESS_SECRET", "").strip()


def profile_params(settings: "Settings"):
    """The profile tunables from settings, as the profile package's own parameter object."""
    from whosaid.profile.params import ProfileParams

    return ProfileParams(
        min_alpha=settings.profile_min_alpha, min_evidence=settings.profile_min_evidence,
        downgrade_below=settings.profile_downgrade_below, mute_below=settings.profile_mute_below,
        upgrade_above=settings.profile_upgrade_above,
    )


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
        tool_server_secret=_env("TOOL_SERVER_SECRET", ""),
        demo_allow_direct=_env("DEMO_ALLOW_DIRECT", "false").lower() in {"1", "true", "yes"},
        agntid_mcp_url=_env("AGNTID_MCP_URL", d.agntid_mcp_url),
        agntid_access_token=_env("AGNTID_ACCESS_TOKEN", ""),
        profile_min_alpha=float(_env("PROFILE_MIN_ALPHA", str(d.profile_min_alpha))),
        profile_min_evidence=int(_env("PROFILE_MIN_EVIDENCE", str(d.profile_min_evidence))),
        profile_downgrade_below=float(_env("PROFILE_DOWNGRADE_BELOW", str(d.profile_downgrade_below))),
        profile_mute_below=float(_env("PROFILE_MUTE_BELOW", str(d.profile_mute_below))),
        profile_upgrade_above=float(_env("PROFILE_UPGRADE_ABOVE", str(d.profile_upgrade_above))),
        api_host=_env("API_HOST", d.api_host),
        api_port=int(_env("API_PORT", str(d.api_port))),
        cors_origins=_env("CORS_ORIGINS", d.cors_origins),
        payment_limit_inr=float(_env("PAYMENT_LIMIT_INR", str(d.payment_limit_inr))),
        agent_concurrency=int(_env("AGENT_CONCURRENCY", str(d.agent_concurrency))),
        cache_dir=Path(_env("CACHE_DIR", str(d.cache_dir))),
        nonce_secret=_env("NONCE_SECRET", d.nonce_secret),
        log_level=_env("LOG_LEVEL", d.log_level).upper(),
    )
