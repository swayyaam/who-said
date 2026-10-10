"""Pick the gateway for an enforcement mode."""

from __future__ import annotations

from whosaid.agent.tool_gateway import DirectGateway, ToolGateway
from whosaid.config import Settings, direct_access_secret
from whosaid.pipeline import GatewayFactory
from whosaid.schemas import Enforcement


def gateway_factory(settings: Settings, enforcement: Enforcement) -> GatewayFactory:
    if enforcement is Enforcement.OFF:
        return lambda: DirectGateway(settings.mcp_server_url, direct_access_secret(enforcement))
    # ON: the agent knows only the AgntID endpoint (and its optional OAuth token), never the tool server.
    from whosaid.agent.agntid_gateway import AgntIDGateway

    return lambda: AgntIDGateway(settings.agntid_mcp_url, settings.agntid_access_token)
