"""The bundled list of our tools (name, description, schema), for tools AgntID may hide.

With AgntID on, the agent knows only the AgntID endpoint, so it cannot ask the tool server what tools exist.
This manifest is how it still shows the model every tool and records a hidden one as a profile-layer denial.
A test keeps it in step with the live server.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from whosaid.agent.tool_gateway import ToolDescriptor

MANIFEST_PATH = Path(__file__).resolve().parent / "tool_manifest.json"


@lru_cache(maxsize=1)
def load_manifest() -> tuple[ToolDescriptor, ...]:
    return tuple(ToolDescriptor.model_validate(d) for d in json.loads(MANIFEST_PATH.read_text()))


async def build_manifest() -> list[dict]:
    """The manifest as the current tool server defines it."""
    from fastmcp import Client

    from whosaid.mcp_server.server import build_server
    from whosaid.store import Store

    async with Client(build_server(Store())) as c:
        tools = await c.list_tools()
    return [ToolDescriptor(name=t.name, description=t.description or "", input_schema=t.inputSchema).model_dump(exclude={"exposed", "excluded_reason"})
            for t in sorted(tools, key=lambda t: t.name)]


if __name__ == "__main__":
    import asyncio

    MANIFEST_PATH.write_text(json.dumps(asyncio.run(build_manifest()), indent=1) + "\n")
    print(f"wrote {MANIFEST_PATH}")
