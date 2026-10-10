#!/usr/bin/env bash
# QuotePulse self-proving demo. SAMPLE / fictional Bay Heat Co data.
# Usage: bash demo.sh [--break]
#   --break  sabotage one assertion so SUMMARY fails (exit 1), for verify-the-checks.
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=src

BREAK=0
if [ "${1:-}" = "--break" ]; then
  BREAK=1
fi

rm -rf data
mkdir -p data

passed=0
failed=0

record() {
  if [ "$1" -eq 0 ]; then
    echo "$2: PASS"
    passed=$((passed + 1))
  else
    echo "$2: FAIL"
    failed=$((failed + 1))
  fi
}

CLI=(python3 src/cli.py)
AS_OF=2026-10-10
FIXTURE=fixtures/bay_heat_estimates.json

echo "QuotePulse demo. SAMPLE / fictional HVAC shop: Bay Heat Co."
echo "Open estimates get day 3/7/14 chase touches under quotepulse."
echo "Control policy memory_only never schedules touches."
echo "as_of=${AS_OF}"
if [ "$BREAK" -eq 1 ]; then
  echo "BREAK MODE: one assertion is intentionally weakened."
fi
echo

echo "=== memory_only ==="
"${CLI[@]}" check \
  --estimates "$FIXTURE" \
  --as-of "$AS_OF" \
  --policy memory_only \
  --out data/memory_only.json
echo

echo "=== quotepulse ==="
"${CLI[@]}" check \
  --estimates "$FIXTURE" \
  --as-of "$AS_OF" \
  --policy quotepulse \
  --out data/quotepulse.json
echo

"${CLI[@]}" compare \
  --estimates "$FIXTURE" \
  --as-of "$AS_OF" \
  --outdir data >/dev/null

echo "=== checks ==="

rc=0
python3 - <<'PY' || rc=1
import json
exp = json.load(open("fixtures/expected.json"))["memory_only"]
run = json.load(open("data/memory_only.json"))
by = {c["estimate_id"]: c["classification"] for c in run["classified"]}
ok = (
    by["E1"] == exp["E1"]
    and by["E2"] == exp["E2"]
    and by["E3"] == exp["E3"]
    and by["E4"] == exp["E4"]
)
raise SystemExit(0 if ok else 1)
PY
record $rc "CHECK 1 (memory_only classes: E1 silent, E2 expired_open, E3 ok_pending, E4 won)"

rc=0
python3 - <<'PY' || rc=1
import json
exp = json.load(open("fixtures/expected.json"))["memory_only"]
run = json.load(open("data/memory_only.json"))
cents = run["silent_expired_cents"]
ids = sorted(run["by_class"]["silent"] + run["by_class"]["expired_open"])
ok = cents == exp["silent_expired_cents"] and ids == sorted(exp["silent_expired_ids"])
dollars = f"${cents // 100}.{cents % 100:02d}"
print(f"  memory_only silent+expired = {cents} cents ({dollars})")
raise SystemExit(0 if ok else 1)
PY
record $rc "CHECK 2 (memory_only silent+expired = 1100000 cents / \$11000.00 on E1+E2)"

rc=0
python3 - <<'PY' || rc=1
import json
exp = json.load(open("fixtures/expected.json"))["quotepulse"]
run = json.load(open("data/quotepulse.json"))
by = {c["estimate_id"]: c["classification"] for c in run["classified"]}
ok = (
    by["E1"] == exp["E1"]
    and by["E2"] == exp["E2"]
    and by["E3"] == exp["E3"]
    and by["E4"] == exp["E4"]
)
raise SystemExit(0 if ok else 1)
PY
record $rc "CHECK 3 (quotepulse classes: E1 follow_up_due, E2 expired_open, E3 ok_pending, E4 won)"

rc=0
python3 - <<'PY' || rc=1
import json
exp = json.load(open("fixtures/expected.json"))["quotepulse"]
run = json.load(open("data/quotepulse.json"))
ok = run["by_class"]["follow_up_due"] == exp["follow_up_due_ids"]
e1 = next(c for c in run["classified"] if c["estimate_id"] == "E1")
ok = ok and any("touch_due:2026-10-10" in r for r in e1["reasons"])
touches = [t for t in run["touches"] if t["estimate_id"] == "E1"]
ok = ok and any(t["due_at"] == "2026-10-10" and t["sent_at"] is None for t in touches)
print(f"  E1 day-3 touch due today: {[t['due_at'] for t in touches if t['due_at']=='2026-10-10']}")
raise SystemExit(0 if ok else 1)
PY
record $rc "CHECK 4 (quotepulse schedules day-3 touch for E1 due 2026-10-10, unsent)"

rc=0
python3 - <<'PY' || rc=1
import json
from pathlib import Path
mem = json.load(open("data/memory_only.json"))
pulse = json.load(open("data/quotepulse.json"))
ok = (
    mem["by_class"]["silent"] == ["E1"]
    and pulse["by_class"]["follow_up_due"] == ["E1"]
    and pulse["by_class"]["expired_open"] == ["E2"]
    and Path("data/report.html").is_file()
)
print(
    "  chase delta: E1 memory_only=silent -> quotepulse=follow_up_due; "
    "E2 expired_open both; report.html present"
)
raise SystemExit(0 if ok else 1)
PY
record $rc "CHECK 5 (chase recovers E1 visibility; HTML report written)"

if [ "$BREAK" -eq 1 ]; then
  echo
  echo "=== break path (expect FAIL on sabotaged check) ==="
  rc=0
  python3 - <<'PY' || rc=1
import json
run = json.load(open("data/quotepulse.json"))
by = {c["estimate_id"]: c["classification"] for c in run["classified"]}
# Sabotage: assert E1 is silent (false under quotepulse; real class is follow_up_due).
ok = by["E1"] == "silent"
raise SystemExit(0 if ok else 1)
PY
  record $rc "CHECK BREAK (sabotaged: expect E1 silent under quotepulse)"
fi

echo
echo "SUMMARY: ${passed} passed, ${failed} failed"
if [ "$failed" -ne 0 ]; then
  exit 1
fi
echo "ALL CLAIMS PASSED"
