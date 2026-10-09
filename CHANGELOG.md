# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Full backend: 12-table PostgreSQL schema with Alembic migration, 13 business
  services, 12 routers under `/api` with the `{success, data, message}` envelope.
- Assignment validation with 10 rules (5 blocking, 5 overridable warnings) plus
  a deterministic auto-schedule proposal engine requiring explicit confirmation.
- Attendance with grace-period lateness and server-computed worked minutes;
  leave with conflict flagging; atomic shift swaps with revalidation on approval.
- Full React frontend (Vite + Bootstrap 5): login, dashboard, weekly calendar,
  employees, attendance, leave, swaps, availability, reports with CSV export,
  notifications and store settings.
- Pytest suite (32 tests, 69% total coverage), GitHub Actions CI for backend
  and frontend, Render + Vercel deploy blueprints, architecture/ER/module
  diagrams with DBML and draw.io sources.

### Changed

- None yet (first release line).

### Fixed

- `cancel_shift`/`delete_shift` now read assignments from a fresh query instead
  of the potentially stale in-memory relationship collection.
- Draft shifts are hidden from employee shift and calendar listings.
- Reports overtime flag now renders its own "overtime" badge.

### Security

- bcrypt-direct password hashing (passlib 1.7.4 is broken against bcrypt 5.x),
  JWT with expiry, store-scoped RBAC returning 404 for out-of-scope objects,
  login rate limiting, append-only audit log, no public manager self-signup.

---

## Milestone notes

This project follows a three-milestone plan. Entries are added to the sections
above as each milestone is completed.

### Day 11 - MVP

Target scope: two end-to-end workflows that run against the real database.

1. A manager provisions an employee, creates a shift and assigns the employee
   to it.
2. An employee logs in, views their assigned shift, and records clock-in and
   clock-out.

### Day 41 - Complete live product

Target scope: all modules implemented, tested and integrated, with the React
frontend wired to the real API and CI running on every push.

### Day 60 - Intelligent Shift Scheduling Assistant

Target scope: a deterministic scheduling proposal engine delivered on a feature
branch, with dedicated unit tests, updated diagrams and README, and a recorded
demonstration video. The core product must remain fully functional when the
assistant is disabled or unavailable.

## Conventions

Commits follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>
```

Types in use: `feat`, `fix`, `docs`, `refactor`, `test`, `perf`, `chore`,
`build`, `ci`, `style`.