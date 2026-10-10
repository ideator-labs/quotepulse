# AGENTS.md - QuotePulse

Cold-start handoff for a coding agent with no prior context.

## What it is and the one claim

Small trades shops (HVAC, plumbing, electrical) send estimates and then lose track.
Customers ghost. The estimate expires. Nobody scheduled a follow-up. Dollars sit
silent in a spreadsheet or a tech's memory.

QuotePulse is an estimate-chase ledger. Open estimates get planned touches at
day 3, 7, and 14 after `sent_at`. Each run classifies every estimate on an
`as_of` date:

- `won` / `lost` if status says so
- `expired_open` if still open and `as_of` is past `expires_at`
- `follow_up_due` if open, not expired, and a planned touch has `due_at <= as_of`
  with `sent_at` null
- `silent` if open, not expired, and the shop has no chase record past the first
  touch day (especially under `memory_only`, which never schedules touches)
- `ok_pending` if the next touch is still in the future

Two policies:

- `memory_only` (control): never schedules touches. Once `as_of` reaches day 3
  after send, an open non-expired estimate is `silent`.
- `quotepulse`: schedules the touch plan, then classifies. Day-3 due today becomes
  `follow_up_due`.

The claim `bash demo.sh` proves. On SAMPLE Bay Heat Co fixtures with
`as_of=2026-10-10`, `memory_only` leaves E1 ($4800) silent and E2 ($6200)
expired_open for $11000 at risk with no chase. `quotepulse` flags E1
`follow_up_due` (day-3 touch due today) and still marks E2 `expired_open`.
Chase recovers visibility on E1.

All fixture data is SAMPLE / fictional. Customers and jobs are made up.

## Status: real vs stubbed

Real:

- Estimate load from JSON (`load_estimates`).
- Touch plan at offsets `[3, 7, 14]` (`schedule_touches`).
- Policies `quotepulse` and `memory_only` with the six classifications above.
- Text render, JSON run output, optional HTML report via `src/cli.py`.
- Self-checking `demo.sh` with five checks and `demo.sh --break`.

Stubbed or not built:

- No live SMS or email send. Touches stay `sent_at: null` in the demo.
- No CRM or Jobber/ServiceTitan connector. Estimates are a static JSON file.
- No reply tracking. There is no "customer replied" state yet.
- No Hivemind OS, Workflow Core, or dbl-entry integration.

## Data shape (with paths)

Frozen dataclasses live at the top of `src/quotepulse.py`.

| Type | Fields | Notes |
|------|--------|-------|
| `Estimate` | `id`, `customer`, `job`, `amount_cents`, `sent_at`, `expires_at`, `status` | `status` in `open` / `won` / `lost`. Dates are ISO `YYYY-MM-DD`. |
| `Touch` | `estimate_id`, `due_at`, `channel`, `sent_at` | `channel` in `sms` / `email`. `sent_at` is null until sent. |
| `Classified` | `estimate_id`, `amount_cents`, `classification`, `reasons` | One row per estimate. |
| `Run` | `policy`, `as_of`, `shop`, `classified`, `touches` | Helpers: `ids_for`, `cents_for`, `to_dict`. |

Touch plan: default offsets days `[3, 7, 14]` after `sent_at`. Channels cycle
`sms`, `email`, `sms`.

Classification order (deterministic):

1. `won` / `lost` from status
2. `expired_open` if open and `as_of > expires_at`
3. Under `memory_only`: `silent` if `as_of >= sent_at + 3 days`, else `ok_pending`
4. Under `quotepulse`: `follow_up_due` if any touch due and unsent; else
   `ok_pending` if a future touch exists; else `silent`

Fixtures:

- `fixtures/bay_heat_estimates.json` (SAMPLE Bay Heat Co)
- `fixtures/expected.json` (expected classes for `as_of=2026-10-10`)

## Repo map

```
quotepulse/
  AGENTS.md
  README.md
  LICENSE
  requirements.txt   # empty on purpose; stdlib only
  sources.md
  demo.sh
  .gitignore
  src/
    quotepulse.py    # types, schedule, classify, render, HTML
    cli.py           # check / compare entrypoints
  fixtures/          # SAMPLE estimates + expected classes
  data/              # gitignored run output from demo.sh
```

## Verified run steps

Fresh clone:

```bash
cd /path/to/quotepulse
bash demo.sh
```

Expect five PASS lines, then `SUMMARY: 5 passed, 0 failed` and `ALL CLAIMS PASSED`,
exit 0.

Break check (must fail, then restore by running without `--break`):

```bash
bash demo.sh --break
# expect non-zero exit; CHECK BREAK: FAIL; SUMMARY includes 1 failed
bash demo.sh
# expect exit 0 again
```

Manual one-shot:

```bash
PYTHONPATH=src python3 src/cli.py check \
  --estimates fixtures/bay_heat_estimates.json \
  --as-of 2026-10-10 \
  --policy quotepulse \
  --out data/quotepulse.json
```

## Design decisions

1. Amounts in integer cents. No floats for money.
2. `memory_only` is the control. It shows the silent/expired pile when nobody
   schedules chase touches.
3. Classification is pure and date-driven. No clock side effects beyond the
   caller-supplied `as_of`.
4. Stdlib only. No pip install step for the demo.

## Limits

- Touches are planned, not sent. There is no Twilio/SendGrid call.
- No inbound reply or "customer opened email" signal.
- One shop fixture. Multi-tenant and auth are out of scope.
- Expired-open estimates still get touch rows under `quotepulse` scheduling, but
  classification prefers `expired_open` over `follow_up_due`.

## Prioritized next steps

1. Mark a touch `sent_at` and re-classify so the next offset becomes due.
   Done when: a unit of demo data with E1 touch1 sent moves E1 from
   `follow_up_due` to `ok_pending` until day 7.
2. Add a `replied` signal that closes chase for an estimate.
   Done when: fixture with reply on E1 classifies `ok_pending` or a new
   `awaiting_decision` class, and demo check covers it.
3. Import CSV from a Jobber/ServiceTitan export.
   Done when: `cli.py import-csv` writes estimates JSON and demo still passes
   on the SAMPLE file.

## Working rules

- Keep prose short. No em-dashes. Label SAMPLE data clearly.
- Prove changes with `bash demo.sh`. Run `--break` once when changing checks.
- Do not add pip dependencies unless the claim needs them.
- Commit as `danielgerlag <daniel@gerlag.ca>`.

## Sources

See `sources.md`. Only those three real URLs are cited.
