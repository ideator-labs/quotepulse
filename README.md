# QuotePulse

Estimate-chase ledger for small trades (HVAC and similar).

Open estimates get scheduled follow-up touches on day 3, 7, and 14 after send.
Each run classifies estimates: `follow_up_due`, `silent`, `expired_open`,
`ok_pending`, `won`, `lost`. Control policy `memory_only` never schedules
touches and leaves dollars silent or expired. QuotePulse proves the chase
recovers visibility on dollars at risk.

All demo data is SAMPLE / fictional (Bay Heat Co).

```bash
bash demo.sh
```

Full handoff for a coding agent: [AGENTS.md](./AGENTS.md).

Sources: [sources.md](./sources.md).
