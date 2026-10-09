# Retail Staff Shift Scheduling Platform

A full-stack staff scheduling and attendance management system for retail
operations, built as a Semester 5 capstone project on the Python track.

## Problem Statement

### Background

Retail organisations operate on rotating shift patterns: morning, afternoon,
evening and overnight shifts, repeated across a seven-day week. In a store with
several dozen employees, keeping that schedule correct by hand is slow and
error-prone. The manager becomes the bottleneck: every leave request, every
sick day, every new hire and every swap has to be reflected in the schedule by
someone working from a spreadsheet.

When a change is missed or entered incorrectly, the consequences are not
abstract:

- An over-booked cashier means a customer waits at an empty till.
- A double-booked shift means an employee is recorded in two places at once
  and is paid for hours they did not work.
- An overnight shift logged as ending the same day it starts makes the worked
  hours negative, which corrupts payroll and overtime reporting.
- An assignment made to somebody who never approved leave creates a dispute
  that has to be resolved manually, often weeks later.

Most small and medium retail businesses still run this on spreadsheets and
paper. Where a system does exist, it is either a generic booking tool that
knows nothing about the constraints that make retail scheduling hard, or a
large enterprise product that is far too expensive and complex for a single
store manager.

### Statement of the Problem

Retail managers lack an affordable, purpose-built tool that:

1. **Validates every scheduling decision before it is made.** An assignment
   should be refused — or at minimum flagged — when it creates an overlapping
   shift, breaks a required rest period, exceeds a weekly hour limit, exceeds
   the consecutive-days limit, conflicts with approved leave, requires a skill
   the employee does not have, falls outside the employee's declared
   availability, or targets somebody who is no longer active.
2. **Handles the awkward cases without corrupting data.** Overnight shifts,
   timezone-aware timestamps, late arrivals inside a grace period, missing
   clock-outs, and clock-outs that happen after midnight all have to be
   computed on the server and stored consistently.
3. **Explains itself.** When a shift cannot be filled, the manager needs to know
   *why* — no available employee, not enough rest, missing skill — instead of
   an unexplained gap.
4. **Keeps employees informed.** Someone who is rostered, someone whose
   request was approved and someone affected by a swap all need to know, and
   nobody needs to be told the same thing twice.
5. **Produces trustworthy reports.** Working hours, fairness across the team,
   overtime warnings and attendance history need to be derivable from the
   database, not from anybody's memory.

Existing tools address at most one of these. Generic calendar or booking
software applies no staffing rules. Enterprise workforce management suites
cover all of them but target multi-site operations with dedicated
administrators, which is not the situation of a single-store retail manager.

### Proposed Solution

The Retail Staff Shift Scheduling Platform is a web application, built on
FastAPI, PostgreSQL, React and Bootstrap, that provides:

- **Rule-enforced scheduling.** All ten assignment rules are evaluated in
  dedicated service functions on the server. The client never supplies an
  employee, a role, or an hours figure that the server then trusts; every
  number the server stores is recomputed from the database.
- **Coverage visibility.** Every shift is classified as fully staffed,
  understaffed, unassigned or cancelled, so gaps are visible on a weekly
  calendar rather than discovered on the trading floor.
- **A deterministic scheduling assistant.** The system can propose who should
  work each unfilled shift, explains the reasoning for each proposal, and
  reports the shifts it could not fill. It never publishes anything by itself:
  a manager must review and explicitly confirm the proposal before it is
  applied.
- **Attendance recorded against real clock events.** Clock-in and clock-out are
  captured with server-side timestamps, lateness is measured against a
  configurable grace period, and worked minutes are computed by the server
  across midnight correctly. A missing clock-out is surfaced to the manager
  for correction rather than being silently overwritten.
- **Leave and shift swaps with revalidation.** Both are validated at
  submission *and* revalidated at approval, so a request cannot be granted
  against state that has since changed. A swap is applied atomically: either
  both employees move or neither does.
- **Store-scoped authorisation.** Managers may only see and change data for
  the store they manage, and this is enforced on the server for every query,
  not merely hidden in the interface.
- **Reporting and CSV export.** Hours worked, fairness spread, overtime
  warnings, attendance history and coverage are computed from live database
  state and exported as CSV.

### Users

- **Store Manager** — provisions employee accounts, builds the weekly
  schedule, reviews and approves leave and swaps, reviews attendance and
  corrects records with a written reason, publishes the schedule and reads
  reports.
- **Employee** — views their own rota, submits availability, requests leave,
  proposes swaps, clocks in and out, and reads their own attendance history.
  Employees cannot create accounts; every account is provisioned by a manager.

### Scope

The system manages a single store at a time in the current release. The data
model carries a store on every operational record, so multi-store support is a
configuration change rather than a redesign, but multi-store consolidation
reporting is explicitly outside the current scope.

### How success is measured

- A manager can build and publish a full week of shifts without a spreadsheet.
- Every attempted assignment that would violate a rule is either rejected with
  a stated reason or accepted with a visible warning.
- Working hours reported for any employee in any week equal the sum of their
  attendance records, including shifts that cross midnight.
- A swap is either applied to both employees or to neither.
- No employee can see or modify data belonging to another store.

---

*This document is the formal problem statement for the capstone project. It
defines the problem, the users, the proposed solution and the boundaries of
the current release.*