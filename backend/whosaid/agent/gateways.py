"""Pick the gateway for an enforcement mode."""

from __future__ import annotations

from whosaid.agent.tool_gateway import DirectGateway, ToolGateway
from whosaid.config import Settings
from whosaid.errors import ConfigError
from whosaid.pipeline import GatewayFactory
from whosaid.schemas import Enforcement


def gateway_factory(settings: Settings, enforcement: Enforcement) -> GatewayFactory:
    if enforcement is Enforcement.OFF:
        return lambda: DirectGateway(settings.mcp_server_url)
    raise ConfigError("enforcement=on needs the AgntID gateway, which is built in phase c")
