import { useEffect, useState } from 'react';
import {
  downloadExport,
  getConflicts,
  getFairness,
  getLeaveBreakdown,
  getSummary,
  getWeeklyHours,
  getWorkingHours,
} from '../api/reports';
import { useToast } from '../components/Toast';
import { EmptyState, ErrorAlert, Loading, StatusBadge } from '../components/ui';
import { addDays, isoDate, mondayOf } from '../utils/format';

const EXPORTS = [
  { kind: 'working-hours', label: 'Working hours' },
  { kind: 'weekly-hours', label: 'Weekly hours' },
  { kind: 'fairness', label: 'Fairness' },
  { kind: 'coverage', label: 'Coverage' },
  { kind: 'leave', label: 'Leave' },
  { kind: 'attendance', label: 'Attendance' },
];

export default function Reports() {
  const { push } = useToast();
  const [week, setWeek] = useState(() => mondayOf(new Date()));
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [exporting, setExporting] = useState('');

  async function load() {
    setLoading(true);
    setError('');
    try {
      const start = isoDate(week);
      const end = isoDate(addDays(week, 6));
      const [summary, working, weekly, fairness, conflicts, leave] = await Promise.all([
        getSummary(start, end),
        getWorkingHours(start, end),
        getWeeklyHours(start),
        getFairness(start, end),
        getConflicts(start, end),
        getLeaveBreakdown(start, end),
      ]);
      setData({ summary, working, weekly, fairness, conflicts, leave, start, end });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [week]);

  async function handleExport(kind) {
    setExporting(kind);
    try {
      await downloadExport(kind, data.start, data.end);
      push(`${kind} CSV downloaded`, 'success');
    } catch (err) {
      push(err.message, 'danger');
    } finally {
      setExporting('');
    }
  }

  return (
    <div className="page">
      <div className="d-flex align-items-center gap-2 flex-wrap">
        <div>
          <h1 className="page-title">Reports</h1>
          <p className="page-sub">Week of {isoDate(week)} â€” every figure is computed from live records.</p>
        </div>
        <span className="ms-auto" />
        <button type="button" className="btn btn-sm btn-outline-secondary" onClick={() => setWeek((w) => addDays(w, -7))}>Previous</button>
        <button type="button" className="btn btn-sm btn-outline-secondary" onClick={() => setWeek(mondayOf(new Date()))}>This week</button>
        <button type="button" className="btn btn-sm btn-outline-secondary" onClick={() => setWeek((w) => addDays(w, 7))}>Next</button>
      </div>

      <ErrorAlert error={error} onRetry={load} />
      {loading && <Loading />}

      {data && (
        <>
          <div className="panel">
            <h2>Store summary</h2>
            <p className="mb-0 small text-muted">
              {data.summary.employee_count} active employees · {data.summary.total_shifts} shifts ·{' '}
              {data.summary.pending_leave} pending leave · {data.summary.pending_swaps} pending swaps ·{' '}
              {data.summary.missing_clockouts} missing clock-outs
            </p>
          </div>

          <div className="panel">
            <h2>Weekly hours &amp; overtime flags</h2>
            {data.weekly.length === 0 ? <EmptyState text="No scheduled hours this week." /> : (
              <div className="table-responsive">
                <table className="table">
                  <thead><tr><th scope="col">Employee</th><th scope="col">Scheduled</th><th scope="col">Contract</th><th scope="col">Flag</th></tr></thead>
                  <tbody>
                    {data.weekly.map((r) => (
                      <tr key={r.employee_id}>
                        <td>{r.employee_name} <small className="text-muted">({r.employee_number})</small></td>
                        <td>{r.scheduled_hours?.toFixed(1)} h</td>
                        <td>{r.contract_hours} h</td>
                        <td>{r.overtime_warning ? <StatusBadge value="overtime" /> : <span className="text-muted small">ok</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="panel">
            <h2>Worked hours</h2>
            {data.working.length === 0 ? <EmptyState text="No worked hours recorded." /> : (
              <div className="table-responsive">
                <table className="table">
                  <thead><tr><th scope="col">Employee</th><th scope="col">Shifts</th><th scope="col">Scheduled</th><th scope="col">Worked</th><th scope="col">Late</th><th scope="col">Absent</th></tr></thead>
                  <tbody>
                    {data.working.map((r) => (
                      <tr key={r.employee_id}>
                        <td>{r.employee_name}</td>
                        <td>{r.shifts_worked}</td>
                        <td>{r.scheduled_hours?.toFixed(1)} h</td>
                        <td>{r.worked_hours?.toFixed(1)} h</td>
                        <td>{r.late_count}</td>
                        <td>{r.absent_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="panel">
            <h2>Fairness spread</h2>
            {data.fairness.length === 0 ? <EmptyState text="No assignments in range." /> : (
              <div className="table-responsive">
                <table className="table">
                  <thead><tr><th scope="col">Employee</th><th scope="col">Shifts</th><th scope="col">Total hours</th></tr></thead>
                  <tbody>
                    {data.fairness.map((r) => (
                      <tr key={r.employee_id}>
                        <td>{r.employee_name}</td>
                        <td>{r.shift_count}</td>
                        <td>{r.total_hours?.toFixed(1)} h</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="panel">
            <h2>Scheduling conflicts ({data.conflicts.length})</h2>
            {data.conflicts.length === 0 ? <EmptyState text="No rule violations. Each conflict needs explicit resolution on the Schedule page." /> : (
              <ul className="mb-0 small">
                {data.conflicts.map((c, i) => (
                  <li key={i}>
                    {c.shift_date} â€” {c.employee_name}: {c.message}
                    {c.blocking ? ' (blocking)' : ' (warning)'}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="panel">
            <h2>Leave breakdown</h2>
            {data.leave.length === 0 ? <EmptyState text="No approved leave in range." /> : (
              <div className="table-responsive">
                <table className="table">
                  <thead><tr><th scope="col">Type</th><th scope="col">Requests</th><th scope="col">Days</th></tr></thead>
                  <tbody>
                    {data.leave.map((r, i) => (
                      <tr key={i}>
                        <td className="text-capitalize">{r.leave_type}</td>
                        <td>{r.request_count}</td>
                        <td>{r.total_days}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="panel">
            <h2>CSV exports</h2>
            <div className="d-flex flex-wrap gap-2">
              {EXPORTS.map((e) => (
                <button
                  key={e.kind}
                  type="button"
                  className="btn btn-sm btn-outline-primary"
                  disabled={exporting === e.kind}
                  onClick={() => handleExport(e.kind)}
                >
                  {exporting === e.kind ? 'Preparingâ€¦' : e.label}
                </button>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
