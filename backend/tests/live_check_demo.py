"""LIVE check (needs the runtime, tool server, Ollama or the fixture): run the whole demo with AgntID ON and
compare EVERY recorded authorization decision with the oracle. Reports mismatches and the per-layer counts.

    cd backend && PYTHONPATH=tests python tests/live_check_demo.py
"""

from __future__ import annotations

import asyncio
import sys
from collections import Counter

from policy_oracle import decide_layered
from rich.console import Console

from whosaid.agent.gateways import gateway_factory
from whosaid.config import DEMO_DATA_DIR, DEMO_FIXTURE_DIR, load_settings
from whosaid.ingest import load_dataset_dir
from whosaid.llm import build_llm
from whosaid.mcp_server.admin import ServerPreferenceReader, ensure_tool_server
from whosaid.pipeline import run_dataset
from whosaid.schemas import Enforcement


async def main() -> int:
    settings, console = load_settings(), Console(width=160)
    dataset = load_dataset_dir(DEMO_DATA_DIR, name="demo")
    llm = build_llm(settings, fixture_dir=DEMO_FIXTURE_DIR)
    with ensure_tool_server(settings, spawn=False) as admin:
        admin.reset_and_seed(dataset.preferences)
        results = await run_dataset(dataset, llm=llm, gateway_factory=gateway_factory(settings, Enforcement.ON), settings=settings,
                                    preferences=ServerPreferenceReader(admin))
    await llm.aclose()

    layers: Counter[str] = Counter()
    mismatches, checked = [], 0
    for r in results:
        for a in r.agent.attempts:
            want_ok, want_reason, want_layer = decide_layered(a.call.tool, a.call.arguments)
            got_ok, got_layer = a.decision.allowed, a.decision.layer.value
            layer_ok = got_ok or got_layer == want_layer or (want_layer == "policy" and got_layer in {"policy", "intent"})
            checked += 1
            layers[got_layer if not got_ok else "allowed"] += 1
            if got_ok != want_ok or not layer_ok:
                mismatches.append((r.message_id, a.call.tool, f"oracle={want_ok}/{want_layer}", f"AgntID={got_ok}/{got_layer}", a.decision.reason))
    console.print(f"checked {checked} AgntID decisions against the oracle: {dict(layers)}")
    attacks = [r for r in results if r.scenario and r.scenario.kind.value == "attack"]
    controls = [r for r in results if r.scenario and r.scenario.kind.value == "control"]
    console.print(f"attacks blocked (no harmful action executed): {sum(not r.harmful_executed for r in attacks)}/{len(attacks)}")
    console.print(f"controls still passing: {sum(bool(r.legit_actions_ok) for r in controls)}/{len(controls)}")
    for m in mismatches:
        console.print(f"[bold red]MISMATCH[/] {m}")
    console.print("[bold green]ALL DECISIONS MATCH THE ORACLE[/]" if not mismatches else f"[bold red]{len(mismatches)} mismatch(es)[/]")
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
