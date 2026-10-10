"""Readable, colored terminal rendering of results (used by the CLI)."""

from __future__ import annotations

import json
import textwrap

from rich.console import Console
from rich.table import Table

from whosaid.schemas import Action, MessageResult, RunSummary, ToolAttempt, TrustLevel

_TRUST_STYLE = {
    TrustLevel.UNKNOWN: "bold red",
    TrustLevel.KNOWN_CONTACT: "bold cyan",
    TrustLevel.GROUP_ADMIN: "bold green",
    TrustLevel.VERIFIED_BUSINESS: "bold green",
}
_ACTION_STYLE = {Action.NOTIFY: "bold cyan", Action.DIGEST: "yellow", Action.MUTE: "dim red"}


def _args(attempt: ToolAttempt) -> str:
    return ", ".join(f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in attempt.call.model_args.items())


def render_result(console: Console, r: MessageResult, *, width: int = 110) -> None:
    kind = r.scenario.kind.value.upper() if r.scenario else ""
    tag = f" [magenta]\\[{kind}: {r.scenario.scenario}][/]" if r.scenario and kind != "BACKGROUND" else ""
    console.print(f"\n[bold]{r.message_id}[/] · {r.user_id} · from {r.sender.sender_id}{tag}")
    wrapped = textwrap.wrap(r.text.replace("\n", " "), width=width - 6)[:3]
    for i, line in enumerate(wrapped):
        console.print(f"  [italic]{'“' if i == 0 else ' '}{line}{'”' if i == len(wrapped) - 1 else ''}[/]")
    lvl = r.trust.level
    console.print(f"  trust  [{_TRUST_STYLE[lvl]}]{lvl.value.upper()}[/]  [dim]{'; '.join(r.trust.reasons)}[/]")
    a = r.routing
    ran = "[bold]agent: yes[/]" if r.agent.ran else "[dim]agent: skipped (not actionable)[/]"
    console.print(f"  route  [{_ACTION_STYLE[a.action]}]{a.action.value.upper()}[/] · {a.message_type.value}  [dim]\\[{a.rule}][/]  {ran}")
    if r.agent.error:
        console.print(f"  [bold red]agent error:[/] {r.agent.error}")
    for at in r.agent.attempts:
        ok = at.decision.allowed
        mark = "[green]✔[/]" if ok else "[bold red]✘[/]"
        style = "green" if ok else "bold red"
        console.print(f"  agent  [bold]{at.call.tool}[/]({_args(at)})")
        console.print(f"         {mark} [{style}]{at.decision.reason}[/]")
        if at.executed:
            extra = f" · ₹{at.money_moved_inr:,.0f} moved" if at.money_moved_inr else ""
            harm = "  [bold white on red] HARMFUL [/]" if at.harmful else ""
            console.print(f"         executed{extra}{harm}")
        elif ok and at.result and at.result.get("status") == "error":
            console.print(f"         [yellow]tool error:[/] {at.result.get('error')}")
    if r.agent.ran:
        s = f"  [dim]{r.agent.llm_calls} llm call(s), {r.agent.llm_cache_hits} cached, {r.agent.latency_ms / 1000:.1f}s[/]"
        console.print(s)
    if r.legit_actions_ok is not None:
        console.print("  control: [green]legitimate actions succeeded[/]" if r.legit_actions_ok
                      else "  control: [bold red]a legitimate action did NOT run[/]")


def render_summary(console: Console, s: RunSummary) -> None:
    t = Table(title=f"Run summary · enforcement {s.enforcement.value.upper()} · {s.model}", show_lines=False)
    t.add_column("metric")
    t.add_column("value", justify="right")
    t.add_row("messages", str(s.messages))
    t.add_row("notify / digest / mute", " / ".join(str(s.by_action.get(k, 0)) for k in ("notify", "digest", "mute")))
    t.add_row("agent runs", str(s.agent_runs))
    t.add_row("actions attempted", str(s.actions_attempted))
    t.add_row("  allowed / denied", f"{s.actions_allowed} / {s.actions_denied}")
    t.add_row("  executed", str(s.actions_executed))
    t.add_row("harmful actions executed", f"[bold red]{s.harmful_executed}[/]" if s.harmful_executed else "[green]0[/]")
    t.add_row("harmful money lost", f"₹{s.harmful_money_lost_inr:,.0f}")
    t.add_row("total money moved", f"₹{s.total_money_moved_inr:,.0f}")
    t.add_row("legitimate controls ok", f"{s.controls_ok} / {s.controls_total}")
    console.print(t)
    bt = Table(title="By sender trust level")
    for col in ("trust level", "msgs", "attempted", "allowed", "denied", "executed", "harmful"):
        bt.add_column(col, justify="right" if col != "trust level" else "left")
    for level, b in sorted(s.by_trust_level.items()):
        bt.add_row(level, str(b.messages), str(b.attempted), str(b.allowed), str(b.denied), str(b.executed), str(b.harmful_executed))
    console.print(bt)
