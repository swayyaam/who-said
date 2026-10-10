"""Command line: run a dataset through the pipeline and print what happened.

    whosaid run --dataset demo --enforcement off
    whosaid serve-mcp          # the tool server, as its own process
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
import tempfile
from pathlib import Path

from rich.console import Console

from whosaid.agent.gateways import gateway_factory
from whosaid.config import DEMO_DATA_DIR, DEMO_FIXTURE_DIR, Settings, load_settings, profile_params
from whosaid.errors import WhoSaidError
from whosaid.ingest import load_dataset_dir
from whosaid.llm import build_llm
from whosaid.logging_setup import setup_logging
from whosaid.mcp_server.admin import ServerPreferenceReader, ToolServerAdmin, ensure_tool_server
from whosaid.profile import Preferences, PreferenceError, apply_update, seed_book
from whosaid.pipeline import run_dataset
from whosaid.report import render_comparison, render_result, render_summary
from whosaid.schemas import Enforcement
from whosaid.summary import summarize


def _resolve_dataset(arg: str):
    path = DEMO_DATA_DIR if arg == "demo" else Path(arg)
    return load_dataset_dir(path, name="demo" if arg == "demo" else None)


async def _run(args: argparse.Namespace, settings: Settings, console: Console, *, quiet: bool = False):
    """Run the dataset once. Returns (results, summary)."""
    dataset = _resolve_dataset(args.dataset)
    enforcement = Enforcement(args.enforcement)
    use_fixture = args.dataset == "demo" and not args.no_fixture
    llm = build_llm(settings, fixture_dir=DEMO_FIXTURE_DIR if use_fixture else None)
    console.rule(f"[bold]WhoSaid[/] · dataset {dataset.name} ({len(dataset.messages)} messages) · AgntID {enforcement.value.upper()} · {llm.model}{' · demo fixture cache' if use_fixture else ''}")
    try:
        with ensure_tool_server(settings, spawn=not args.no_spawn) as admin:
            admin.reset_and_seed(dataset.preferences)
            results = await run_dataset(
                dataset, llm=llm, gateway_factory=gateway_factory(settings, enforcement), settings=settings,
                preferences=ServerPreferenceReader(admin), profile_params=profile_params(settings),
                on_result=None if quiet else (lambda r: render_result(console, r)), only=set(args.only) if args.only else None,
                limit=args.limit, concurrency=args.concurrency,
            )
            state = admin.state()
    finally:
        await llm.aclose()
    summary = summarize(results, enforcement=enforcement, model=llm.model, dataset_id=dataset.dataset_id)
    if not quiet:
        console.print()
        render_summary(console, summary)
        _print_preference_changes(console, dataset.preferences, state.preferences)
        spent = sum(e.amount_inr for e in state.ledger if e.tool == "pay_upi" and e.status == "ok")
        console.print(f"[dim]tool-server ledger: ₹{spent:,.0f} actually paid out · {len(state.ledger)} effect(s) recorded[/]")
    return results, summary


async def _compare(args: argparse.Namespace, settings: Settings, console: Console) -> int:
    """Run the dataset with AgntID OFF, then ON, and print them side by side."""
    runs = {}
    for mode in ("off", "on"):
        run_args = argparse.Namespace(**{**vars(args), "enforcement": mode})
        console.print(f"[bold]running with AgntID {mode.upper()}...[/]")
        runs[mode] = await _run(run_args, settings, console, quiet=True)
    render_comparison(console, runs["off"][1], runs["on"][1], runs["off"][0], runs["on"][0])
    return 0


def _print_preference_changes(console: Console, before: dict[str, Preferences], after: dict[str, dict]) -> None:
    changed = [(u, Preferences.model_validate(p)) for u, p in after.items() if Preferences.model_validate(p) != before.get(u, Preferences())]
    if not changed:
        return
    console.print("[bold red]explicit preferences were changed during the run:[/]")
    for user, prefs in changed:
        base = before.get(user, Preferences()).model_dump()
        for key, value in prefs.model_dump().items():
            if value != base[key]:
                console.print(f"  {user}: {key} {base[key]!r} -> [bold]{value!r}[/]")


def _cmd_prefs(args: argparse.Namespace, settings: Settings, console: Console) -> int:
    """Show or change a user's explicit preferences on the running tool server (the user's own path)."""
    admin = ToolServerAdmin(settings.mcp_server_url)
    if not admin.healthy():
        console.print(f"[bold red]no tool server at {settings.mcp_server_url}[/]; start it with: whosaid serve-mcp")
        return 2
    try:
        prefs = admin.get_preferences(args.user)
        if args.prefs_command == "set":
            prefs = admin.put_preferences(args.user, apply_update(prefs, args.key, args.value))
        elif args.prefs_command == "clear":
            prefs = admin.put_preferences(args.user, Preferences())
    except PreferenceError as exc:
        console.print(f"[bold red]error:[/] {exc}")
        return 2
    console.print_json(prefs.model_dump_json())
    return 0


def _cmd_profile(args: argparse.Namespace, console: Console) -> int:
    """Print the learned profile for a user, seeded from the dataset's history in one pass."""
    from rich.table import Table

    dataset = _resolve_dataset(args.dataset)
    book = seed_book(dataset.history, dataset.events)
    scores = book.for_user(args.user).snapshot()
    t = Table(title=f"Learned profile · {args.user} · seeded from {len(dataset.history)} history message(s)")
    for col in ("entity", "score", "interactions"):
        t.add_column(col, justify="left" if col == "entity" else "right")
    for key, s in sorted(scores.items(), key=lambda kv: kv[1].score):
        style = "red" if s.score <= -0.4 else "green" if s.score >= 0.6 else ""
        t.add_row(key, f"[{style}]{s.score:+.2f}[/]" if style else f"{s.score:+.2f}", str(s.n))
    console.print(t if scores else f"[dim]no learned scores for {args.user}[/]")
    prefs = dataset.preferences.get(args.user)
    if prefs:
        console.print("explicit preferences (from the dataset):")
        console.print_json(prefs.model_dump_json())
    return 0


async def _refresh_fixture(args: argparse.Namespace, settings: Settings, console: Console) -> int:
    """Re-record the committed demo fixture by running the demo against the real model."""
    tmp = Path(tempfile.mkdtemp(prefix="whosaid-fixture-"))
    scratch = settings.model_copy(update={"cache_dir": tmp})
    modes = ["off", "on"] if args.enforcement == "both" else [args.enforcement]
    try:
        for mode in modes:
            run_args = argparse.Namespace(dataset="demo", enforcement=mode, only=None, limit=None, concurrency=1,
                                          no_spawn=args.no_spawn, no_fixture=True)
            await _run(run_args, scratch, console, quiet=True)
        target = DEMO_FIXTURE_DIR / "llm"
        if target.exists() and not args.merge:
            shutil.rmtree(target)
        shutil.copytree(tmp / "llm", target, dirs_exist_ok=True)
        count = sum(1 for _ in target.rglob("*.json"))
        console.print(f"[bold green]fixture refreshed:[/] {count} recorded LLM answer(s) in {target}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="whosaid")
    sub = p.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run a dataset through the agent")
    run.add_argument("--dataset", default="demo", help="'demo' or a folder of CSVs")
    run.add_argument("--enforcement", choices=["off", "on"], default="off")
    run.add_argument("--only", nargs="*", help="only these message ids")
    run.add_argument("--limit", type=int)
    run.add_argument("--concurrency", type=int)
    run.add_argument("--model", help="override LLM_MODEL")
    run.add_argument("--no-fixture", action="store_true", help="do not use the committed demo fixture cache")
    run.add_argument("--no-spawn", action="store_true", help="do not start the tool server if it is not running")
    run.add_argument("--verbose", action="store_true", help="print the JSON event log to stderr")
    fx = sub.add_parser("refresh-fixture", help="re-record the committed demo fixture against the real model")
    fx.add_argument("--enforcement", choices=["off", "on", "both"], default="off")
    fx.add_argument("--merge", action="store_true", help="add to the existing fixture instead of replacing it")
    fx.add_argument("--no-spawn", action="store_true")
    pf = sub.add_parser("prefs", help="show/set/clear a user's explicit preferences on the running tool server")
    pf_sub = pf.add_subparsers(dest="prefs_command", required=True)
    for name in ("show", "set", "clear"):
        sp = pf_sub.add_parser(name)
        sp.add_argument("user")
        if name == "set":
            sp.add_argument("key")
            sp.add_argument("value")
    pr = sub.add_parser("profile", help="print a user's learned profile (seeded from the dataset)")
    pr.add_argument("user")
    pr.add_argument("--dataset", default="demo")
    cmp_ = sub.add_parser("compare", help="run the dataset with AgntID OFF then ON and print them side by side")
    cmp_.add_argument("--dataset", default="demo")
    cmp_.add_argument("--only", nargs="*")
    cmp_.add_argument("--limit", type=int)
    cmp_.add_argument("--concurrency", type=int)
    cmp_.add_argument("--model")
    cmp_.add_argument("--no-spawn", action="store_true")
    cmp_.add_argument("--no-fixture", action="store_true")
    sub.add_parser("serve-mcp", help="run the MCP tool server")
    args = p.parse_args(argv)

    if args.command == "serve-mcp":
        from whosaid.mcp_server.__main__ import main as serve

        serve()
        return 0

    settings = load_settings()
    if getattr(args, "model", None):
        settings = settings.model_copy(update={"llm_model": args.model})
    if getattr(args, "verbose", False):
        setup_logging(settings.log_level)
    else:
        settings.cache_dir.mkdir(parents=True, exist_ok=True)
        setup_logging(settings.log_level, stream=open(settings.cache_dir / "whosaid.log", "a", encoding="utf-8"))
    console = Console()
    try:
        if args.command == "compare":
            return asyncio.run(_compare(args, settings, console))
        if args.command == "prefs":
            return _cmd_prefs(args, settings, console)
        if args.command == "profile":
            return _cmd_profile(args, console)
        if args.command == "refresh-fixture":
            return asyncio.run(_refresh_fixture(args, settings, console))
        asyncio.run(_run(args, settings, console))
        return 0
    except WhoSaidError as exc:
        console.print(f"[bold red]error:[/] {exc}")
        for problem in getattr(exc, "problems", [])[1:]:
            console.print(f"  - {problem}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
