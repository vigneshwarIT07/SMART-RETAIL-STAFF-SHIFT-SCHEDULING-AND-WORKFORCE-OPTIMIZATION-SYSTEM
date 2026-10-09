# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

### Changed

### Fixed

### Security

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