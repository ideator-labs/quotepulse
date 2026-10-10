"""QuotePulse: estimate-chase ledger for small trades.

Classify open estimates under quotepulse (scheduled touches) vs memory_only
(no touches). Pure stdlib. SAMPLE / fictional fixtures only.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

Status = Literal["open", "won", "lost"]
Channel = Literal["sms", "email"]
Policy = Literal["quotepulse", "memory_only"]
Classification = Literal[
    "won",
    "lost",
    "expired_open",
    "follow_up_due",
    "silent",
    "ok_pending",
]

DEFAULT_TOUCH_OFFSETS_DAYS = (3, 7, 14)
DEFAULT_CHANNELS: tuple[Channel, ...] = ("sms", "email", "sms")


@dataclass(frozen=True)
class Estimate:
    id: str
    customer: str
    job: str
    amount_cents: int
    sent_at: str  # ISO date YYYY-MM-DD
    expires_at: str
    status: Status


@dataclass(frozen=True)
class Touch:
    estimate_id: str
    due_at: str  # ISO date
    channel: Channel
    sent_at: str | None  # null until sent


@dataclass(frozen=True)
class Classified:
    estimate_id: str
    amount_cents: int
    classification: Classification
    reasons: list[str]


@dataclass
class Run:
    policy: Policy
    as_of: str
    shop: str
    classified: list[Classified] = field(default_factory=list)
    touches: list[Touch] = field(default_factory=list)

    def ids_for(self, label: Classification) -> list[str]:
        return [c.estimate_id for c in self.classified if c.classification == label]

    def cents_for(self, *labels: Classification) -> int:
        wanted = set(labels)
        return sum(
            c.amount_cents for c in self.classified if c.classification in wanted
        )

    def to_dict(self) -> dict:
        return {
            "policy": self.policy,
            "as_of": self.as_of,
            "shop": self.shop,
            "classified": [asdict(c) for c in self.classified],
            "touches": [asdict(t) for t in self.touches],
            "by_class": {
                label: self.ids_for(label)  # type: ignore[arg-type]
                for label in (
                    "won",
                    "lost",
                    "expired_open",
                    "follow_up_due",
                    "silent",
                    "ok_pending",
                )
            },
            "at_risk_cents": self.cents_for("silent", "expired_open", "follow_up_due"),
            "silent_expired_cents": self.cents_for("silent", "expired_open"),
        }


def parse_date(s: str) -> date:
    return date.fromisoformat(s)


def load_estimates(path: Path) -> list[Estimate]:
    raw = json.loads(path.read_text())
    return [Estimate(**row) for row in raw["estimates"]]


def schedule_touches(
    estimates: list[Estimate],
    offsets: tuple[int, ...] = DEFAULT_TOUCH_OFFSETS_DAYS,
    channels: tuple[Channel, ...] = DEFAULT_CHANNELS,
) -> list[Touch]:
    """Plan unsent touches at day offsets after sent_at. Open estimates only."""
    touches: list[Touch] = []
    for est in estimates:
        if est.status != "open":
            continue
        sent = parse_date(est.sent_at)
        for i, days in enumerate(offsets):
            channel = channels[i % len(channels)]
            due = (sent + timedelta(days=days)).isoformat()
            touches.append(
                Touch(
                    estimate_id=est.id,
                    due_at=due,
                    channel=channel,
                    sent_at=None,
                )
            )
    return touches


def classify_estimate(
    est: Estimate,
    as_of: date,
    policy: Policy,
    touches: list[Touch],
    first_offset_days: int = DEFAULT_TOUCH_OFFSETS_DAYS[0],
) -> Classified:
    reasons: list[str] = []

    if est.status == "won":
        return Classified(est.id, est.amount_cents, "won", ["status:won"])
    if est.status == "lost":
        return Classified(est.id, est.amount_cents, "lost", ["status:lost"])

    expires = parse_date(est.expires_at)
    if as_of > expires:
        return Classified(
            est.id,
            est.amount_cents,
            "expired_open",
            [f"as_of>{est.expires_at}", "status:open"],
        )

    est_touches = [t for t in touches if t.estimate_id == est.id]
    sent = parse_date(est.sent_at)

    if policy == "memory_only":
        # No touches scheduled. Past first chase day with no record => silent.
        chase_start = sent + timedelta(days=first_offset_days)
        if as_of >= chase_start:
            return Classified(
                est.id,
                est.amount_cents,
                "silent",
                [
                    "policy:memory_only",
                    "no_touches",
                    f"as_of>={chase_start.isoformat()}",
                ],
            )
        return Classified(
            est.id,
            est.amount_cents,
            "ok_pending",
            [
                "policy:memory_only",
                f"before_chase_day:{chase_start.isoformat()}",
            ],
        )

    # quotepulse
    due_unsent = [
        t for t in est_touches if parse_date(t.due_at) <= as_of and t.sent_at is None
    ]
    if due_unsent:
        due_unsent.sort(key=lambda t: t.due_at)
        t0 = due_unsent[0]
        return Classified(
            est.id,
            est.amount_cents,
            "follow_up_due",
            [
                f"touch_due:{t0.due_at}",
                f"channel:{t0.channel}",
                "sent_at:null",
            ],
        )

    future = [t for t in est_touches if parse_date(t.due_at) > as_of]
    if future:
        future.sort(key=lambda t: t.due_at)
        nxt = future[0]
        return Classified(
            est.id,
            est.amount_cents,
            "ok_pending",
            [f"next_touch:{nxt.due_at}", f"channel:{nxt.channel}"],
        )

    # All planned touches past and never sent (edge).
    if est_touches:
        return Classified(
            est.id,
            est.amount_cents,
            "silent",
            ["all_touches_past_unsent"],
        )

    # Open, no touches planned (shouldn't happen under quotepulse for open est).
    return Classified(
        est.id,
        est.amount_cents,
        "silent",
        ["no_touches_planned"],
    )


def run_policy(
    estimates: list[Estimate],
    as_of: str,
    policy: Policy,
    shop: str = "Bay Heat Co",
) -> Run:
    as_of_d = parse_date(as_of)
    touches: list[Touch] = []
    if policy == "quotepulse":
        touches = schedule_touches(estimates)

    run = Run(policy=policy, as_of=as_of, shop=shop, touches=touches)
    for est in estimates:
        run.classified.append(
            classify_estimate(est, as_of_d, policy, touches)
        )
    return run


def cents_to_dollars(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}${cents // 100}.{cents % 100:02d}"


def render_run(run: Run) -> str:
    lines = [
        f"shop={run.shop}  policy={run.policy}  as_of={run.as_of}",
        f"SAMPLE / fictional HVAC estimates",
        "",
    ]
    for c in run.classified:
        lines.append(
            f"  {c.estimate_id}  {cents_to_dollars(c.amount_cents):>10}  "
            f"{c.classification:<14}  {', '.join(c.reasons)}"
        )
    if run.touches:
        lines.append("")
        lines.append(f"touches scheduled: {len(run.touches)}")
        for t in run.touches:
            lines.append(
                f"  {t.estimate_id}  due={t.due_at}  {t.channel}  sent={t.sent_at}"
            )
    silent_exp = run.cents_for("silent", "expired_open")
    at_risk = run.cents_for("silent", "expired_open", "follow_up_due")
    lines.append("")
    lines.append(
        f"silent+expired: {silent_exp} cents ({cents_to_dollars(silent_exp)})"
    )
    lines.append(
        f"at_risk (silent+expired+follow_up_due): {at_risk} cents "
        f"({cents_to_dollars(at_risk)})"
    )
    return "\n".join(lines)


def write_run(run: Run, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(run.to_dict(), indent=2) + "\n")


def write_html_report(memory: Run, pulse: Run, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    def rows(run: Run) -> str:
        out = []
        for c in run.classified:
            out.append(
                "<tr>"
                f"<td>{c.estimate_id}</td>"
                f"<td>{cents_to_dollars(c.amount_cents)}</td>"
                f"<td>{c.classification}</td>"
                f"<td>{', '.join(c.reasons)}</td>"
                "</tr>"
            )
        return "\n".join(out)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>QuotePulse SAMPLE report</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; }}
table {{ border-collapse: collapse; margin-bottom: 2rem; }}
th, td {{ border: 1px solid #ccc; padding: 0.4rem 0.6rem; text-align: left; }}
.note {{ color: #666; }}
</style>
</head>
<body>
<h1>QuotePulse</h1>
<p class="note">SAMPLE / fictional data for Bay Heat Co. Not real customers.</p>
<p>as_of={memory.as_of}</p>
<h2>memory_only (control)</h2>
<table>
<tr><th>id</th><th>amount</th><th>class</th><th>reasons</th></tr>
{rows(memory)}
</table>
<p>silent+expired: {memory.cents_for('silent', 'expired_open')} cents
({cents_to_dollars(memory.cents_for('silent', 'expired_open'))})</p>
<h2>quotepulse</h2>
<table>
<tr><th>id</th><th>amount</th><th>class</th><th>reasons</th></tr>
{rows(pulse)}
</table>
<p>follow_up_due: {', '.join(pulse.ids_for('follow_up_due')) or '(none)'}</p>
</body>
</html>
"""
    path.write_text(html)
