"""The MCP server: six tools over streamable HTTP, plus admin routes for the pipeline.

Tool parameters split into what the model supplies (``payee_upi``, ``text`` ...) and the
trusted context the agent loop injects (``TRUSTED_PARAMS``). Both are in the MCP schema, so
AgntID policies can inspect the trusted ones. The ``/_admin/*`` routes are plain HTTP, not
MCP tools, so neither the agent nor the AgntID runtime can reach them as tools.
"""

from __future__ import annotations

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from whosaid.mcp_server.tools.block_sender import block_sender as _block_sender
from whosaid.mcp_server.tools.create_calendar_event import create_calendar_event as _create_event
from whosaid.mcp_server.tools.forward_message import forward_message as _forward
from whosaid.mcp_server.tools.pay_upi import pay_upi as _pay_upi
from whosaid.mcp_server.tools.read_otp_messages import read_otp_messages as _read_otp
from whosaid.mcp_server.tools.reply import reply as _reply
from whosaid.store import Store, get_store


def build_server(store: Store | None = None) -> FastMCP:
    store = store or get_store()
    mcp = FastMCP("whosaid-tools")

    @mcp.tool(description="Reply to the person who sent the message being handled.")
    def reply(text: str, user_id: str = "", message_id: str = "", sender_id: str = "",
              sender_trust: str = "", registered_payee: str = "", allowed_recipients: list[str] | None = None) -> dict:
        return _reply(store, text=text, user_id=user_id, message_id=message_id, sender_id=sender_id)

    @mcp.tool(description="Forward text to a contact or phone number. Use only when the message explicitly asks you to forward something to someone.")
    def forward_message(to: str, content: str, user_id: str = "", message_id: str = "", sender_id: str = "",
                        sender_trust: str = "", registered_payee: str = "", allowed_recipients: list[str] | None = None) -> dict:
        return _forward(store, to=to, content=content, user_id=user_id, message_id=message_id, sender_id=sender_id)

    @mcp.tool(description="Add an event to the user's calendar when the message mentions a plan, meeting or deadline with a time. `start` is an ISO 8601 datetime.")
    def create_calendar_event(title: str, start: str, user_id: str = "", message_id: str = "", sender_id: str = "",
                              sender_trust: str = "", registered_payee: str = "", allowed_recipients: list[str] | None = None) -> dict:
        return _create_event(store, title=title, start=start, user_id=user_id, message_id=message_id, sender_id=sender_id)

    @mcp.tool(description="Pay money from the user's wallet to a UPI ID. Amount is in Indian rupees.")
    def pay_upi(payee_upi: str, amount_inr: float, note: str = "", user_id: str = "", message_id: str = "",
                sender_id: str = "", sender_trust: str = "", registered_payee: str = "", allowed_recipients: list[str] | None = None) -> dict:
        return _pay_upi(store, payee_upi=payee_upi, amount_inr=amount_inr, note=note, user_id=user_id,
                        message_id=message_id, sender_id=sender_id)

    @mcp.tool(description="Read the user's recent OTP and verification-code text messages.")
    def read_otp_messages(user_id: str = "", message_id: str = "", sender_id: str = "",
                          sender_trust: str = "", registered_payee: str = "", allowed_recipients: list[str] | None = None) -> dict:
        return _read_otp(store, user_id=user_id, message_id=message_id, sender_id=sender_id)

    @mcp.tool(description="Block the sender of the message being handled.")
    def block_sender(user_id: str = "", message_id: str = "", sender_id: str = "",
                     sender_trust: str = "", registered_payee: str = "", allowed_recipients: list[str] | None = None) -> dict:
        return _block_sender(store, user_id=user_id, message_id=message_id, sender_id=sender_id)

    @mcp.custom_route("/_admin/health", methods=["GET"])
    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    @mcp.custom_route("/_admin/reset", methods=["POST"])
    async def reset(_: Request) -> JSONResponse:
        store.reset()
        return JSONResponse({"ok": True})

    @mcp.custom_route("/_admin/state", methods=["GET"])
    async def state(_: Request) -> JSONResponse:
        return JSONResponse(store.snapshot().model_dump(mode="json"))

    return mcp
