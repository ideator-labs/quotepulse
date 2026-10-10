#!/usr/bin/env python3
"""CLI for QuotePulse check runs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from quotepulse import (
    load_estimates,
    render_run,
    run_policy,
    write_html_report,
    write_run,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="QuotePulse estimate-chase ledger")
    sub = p.add_subparsers(dest="cmd", required=True)

    check = sub.add_parser("check", help="Classify estimates under a policy")
    check.add_argument("--estimates", type=Path, required=True)
    check.add_argument("--as-of", required=True, help="ISO date YYYY-MM-DD")
    check.add_argument(
        "--policy",
        choices=("quotepulse", "memory_only"),
        required=True,
    )
    check.add_argument("--shop", default="Bay Heat Co")
    check.add_argument("--out", type=Path, required=True)
    check.add_argument("--quiet", action="store_true")

    both = sub.add_parser(
        "compare",
        help="Run memory_only then quotepulse; write JSON + HTML",
    )
    both.add_argument("--estimates", type=Path, required=True)
    both.add_argument("--as-of", required=True)
    both.add_argument("--shop", default="Bay Heat Co")
    both.add_argument("--outdir", type=Path, required=True)

    args = p.parse_args(argv)
    estimates = load_estimates(args.estimates)

    if args.cmd == "check":
        run = run_policy(
            estimates, as_of=args.as_of, policy=args.policy, shop=args.shop
        )
        write_run(run, args.out)
        if not args.quiet:
            print(render_run(run))
        return 0

    if args.cmd == "compare":
        outdir: Path = args.outdir
        outdir.mkdir(parents=True, exist_ok=True)
        memory = run_policy(
            estimates, as_of=args.as_of, policy="memory_only", shop=args.shop
        )
        pulse = run_policy(
            estimates, as_of=args.as_of, policy="quotepulse", shop=args.shop
        )
        write_run(memory, outdir / "memory_only.json")
        write_run(pulse, outdir / "quotepulse.json")
        write_html_report(memory, pulse, outdir / "report.html")
        print("=== memory_only ===")
        print(render_run(memory))
        print()
        print("=== quotepulse ===")
        print(render_run(pulse))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
