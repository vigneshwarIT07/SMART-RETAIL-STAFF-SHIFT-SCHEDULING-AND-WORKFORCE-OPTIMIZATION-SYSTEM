# Enhancement Proposal — Intelligent Shift Scheduling Assistant (Day-60 Milestone)

## Status

Proposed. Not implemented yet — this document is the plan for the Day-60 enhancement, to be built on a feature branch after the Day-41 complete product is accepted.

## Goal

Layer an **Intelligent Shift Scheduling Assistant** on top of the existing deterministic proposal engine (`backend/app/services/auto_schedule_service.py`) that suggests *who should work when* using store demand signals (past footfall/sales per hour, past attendance reliability, stated availability), while keeping the deterministic rule engine as the offline-capable core that always works without any paid AI service.

## Non-negotiable constraints

1. The core product keeps working with zero external services. The assistant is additive: if its inputs are missing, the deterministic engine's output is used unchanged.
2. No auto-publishing, ever. Assistant suggestions flow through the same explicit manager-confirmation step (`POST /api/scheduling/apply`) as today.
3. Hours remain configurable business rules (`MAX_WEEKLY_HOURS`, `OVERTIME_WARNING_HOURS`, …). Nothing here claims legal labour-law compliance.
4. No paid AI service is required. Any model/scoring must run locally or be a transparent heuristic with unit tests.

## Proposed design

- New service module `backend/app/services/demand_service.py`: hourly demand profiles per weekday built from historical attendance + shift data already in the database (no new external data required for v1).
- Extend `generate_proposal` output with a `score_breakdown` per suggestion (demand fit, reliability, cost/hours balance) and surface it in the Schedule → Auto-schedule tab as plain rows with reasons — no decorative charts.
- New endpoint `GET /api/scheduling/demand?start_date&end_date` returning the demand profile used, so every suggestion stays explainable and auditable.
- Dedicated unit tests: scoring determinism (same input → same output), graceful fallback when history is empty, and revalidation of every assistant suggestion through the existing 10 assignment rules before apply.

## Acceptance criteria

- Built on a feature branch, merged only after the existing 23 tests plus new assistant tests all pass.
- Core scheduling works with the assistant disabled (feature flag / missing data path covered by a test).
- `docs/diagrams/` and `README.md` updated to describe the assistant; 2–4 minute demo video recorded.

## Risks

- Thin history for new stores → cold-start fallback to the deterministic engine (documented, tested).
- Over-trust in suggestions → UI keeps the proposal/confirm separation and shows unfillable shifts with reasons.
