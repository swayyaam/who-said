"""Roll message results up into a RunSummary. Pure; the dashboard's per-run numbers."""

from __future__ import annotations

from collections import Counter, defaultdict

from whosaid.schemas import Enforcement, MessageResult, RunSummary, TrustBreakdown


def summarize(
    results: list[MessageResult],
    *,
    enforcement: Enforcement,
    model: str = "",
    run_id: str = "",
    dataset_id: str = "",
) -> RunSummary:
    by_action = Counter(r.routing.action.value for r in results)
    by_trust: dict[str, TrustBreakdown] = defaultdict(TrustBreakdown)
    attempted = allowed = denied = executed = harmful = 0
    harmful_money = total_money = 0.0
    controls_total = controls_ok = 0

    for r in results:
        b = by_trust[r.trust.level.value]
        b.messages += 1
        for a in r.agent.attempts:
            attempted += 1
            b.attempted += 1
            if a.decision.allowed:
                allowed += 1
                b.allowed += 1
            else:
                denied += 1
                b.denied += 1
            if a.executed:
                executed += 1
                b.executed += 1
            if a.harmful:
                harmful += 1
                b.harmful_executed += 1
        harmful_money += r.harmful_money_lost_inr
        total_money += r.money_moved_inr
        if r.legit_actions_ok is not None:
            controls_total += 1
            controls_ok += int(r.legit_actions_ok)

    return RunSummary(
        run_id=run_id,
        dataset_id=dataset_id,
        enforcement=enforcement,
        model=model,
        messages=len(results),
        by_action={a: by_action.get(a, 0) for a in ("notify", "digest", "mute")},
        agent_runs=sum(1 for r in results if r.agent.ran),
        actions_attempted=attempted,
        actions_allowed=allowed,
        actions_denied=denied,
        actions_executed=executed,
        harmful_executed=harmful,
        harmful_money_lost_inr=round(harmful_money, 2),
        total_money_moved_inr=round(total_money, 2),
        controls_total=controls_total,
        controls_ok=controls_ok,
        by_trust_level=dict(by_trust),
    )
