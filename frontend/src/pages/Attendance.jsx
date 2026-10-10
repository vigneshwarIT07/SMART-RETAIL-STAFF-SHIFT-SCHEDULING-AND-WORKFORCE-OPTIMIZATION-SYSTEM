import { useEffect, useState } from 'react';
import {
  attendanceSummary,
  clockIn,
  clockOut,
  correctAttendance,
  listAttendance,
  markAbsent,
  missingClockouts,
} from '../api/attendance';
import { listShifts } from '../api/shifts';
import { listEmployees } from '../api/employees';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../components/Toast';
import { EmptyState, ErrorAlert, Field, Loading, Modal, StatusBadge } from '../components/ui';
import { fmtDateTime, hoursText, isoDate } from '../utils/format';

function ManagerTools({ onChanged }) {
  const { push } = useToast();
  const [missing, setMissing] = useState([]);
  const [absForm, setAbsForm] = useState({ shift_id: '', employee_id: '', notes: '' });
  const [shifts, setShifts] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [correcting, setCorrecting] = useState(null);
  const [corr, setCorr] = useState({ clock_in: '', clock_out: '', status: '', reason: '' });

  useEffect(() => {
    missingClockouts().then(setMissing).catch(() => {});
    const today = isoDate(new Date());
    listShifts({ start_date: today, end_date: today }).then(setShifts).catch(() => {});
    listEmployees({ page_size: 100 }).then((d) => setEmployees(d.items || [])).catch(() => {});
  }, []);

  async function handleAbsent(e) {
    e.preventDefault();
    try {
      await markAbsent(absForm.shift_id, absForm.employee_id, absForm.notes || undefined);
      push('Marked absent', 'info');
      setAbsForm({ shift_id: '', employee_id: '', notes: '' });
      onChanged();
    } catch (err) {
      push(err.message, 'danger');
    }
  }

  async function handleCorrect(e) {
    e.preventDefault();
    try {
      await correctAttendance(correcting.id, {
        clock_in: corr.clock_in || null,
        clock_out: corr.clock_out || null,
        status: corr.status || null,
        reason: corr.reason,
      });
      push('Attendance corrected', 'success');
      setCorrecting(null);
      onChanged();
    } catch (err) {
      push(err.message, 'danger');
    }
  }

  return (
    <>
      <div className="panel">
        <h2>Missing clock-outs ({missing.length})</h2>
        {missing.length === 0 ? (
          <EmptyState text="Nothing awaiting review." />
        ) : (
          <div className="table-responsive">
            <table className="table">
              <thead><tr><th scope="col">Employee</th><th scope="col">Shift date</th><th scope="col">Clock-in</th><th scope="col">Hours since</th><th scope="col"><span className="visually-hidden">Actions</span></th></tr></thead>
              <tbody>
                {missing.map((m) => (
                  <tr key={m.attendance_id}>
                    <td>{m.employee_name}</td>
                    <td>{m.shift_date}</td>
                    <td>{fmtDateTime(m.clock_in)}</td>
                    <td>{m.hours_since_clock_in?.toFixed(1)}</td>
                    <td className="text-end">
                      <button type="button" className="btn btn-sm btn-outline-secondary" onClick={() => { setCorrecting({ id: m.attendance_id }); setCorr({ clock_in: '', clock_out: '', status: '', reason: '' }); }}>
                        Correct
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <div className="panel">
        <h2>Mark absent (today&apos;s shifts)</h2>
        <form className="row g-2" onSubmit={handleAbsent}>
          <div className="col-md-4">
            <label className="form-label" htmlFor="abs-shift">Shift</label>
            <select id="abs-shift" className="form-select" required value={absForm.shift_id} onChange={(e) => setAbsForm({ ...absForm, shift_id: e.target.value })}>
              <option value="">Select…</option>
              {shifts.map((s) => (
                <option key={s.id} value={s.id}>{s.shift_date} {String(s.start_time).slice(0, 5)} {s.role_required || ''}</option>
              ))}
            </select>
          </div>
          <div className="col-md-4">
            <label className="form-label" htmlFor="abs-emp">Employee</label>
            <select id="abs-emp" className="form-select" required value={absForm.employee_id} onChange={(e) => setAbsForm({ ...absForm, employee_id: e.target.value })}>
              <option value="">Select…</option>
              {employees.map((emp) => (
                <option key={emp.id} value={emp.id}>{emp.full_name}</option>
              ))}
            </select>
          </div>
          <div className="col-md-3">
            <label className="form-label" htmlFor="abs-notes">Note</label>
            <input id="abs-notes" className="form-control" value={absForm.notes} onChange={(e) => setAbsForm({ ...absForm, notes: e.target.value })} />
          </div>
          <div className="col-md-1 d-flex align-items-end">
            <button type="submit" className="btn btn-outline-danger">Mark</button>
          </div>
        </form>
      </div>
      {correcting && (
        <Modal title="Correct attendance record" onClose={() => setCorrecting(null)}>
          <form onSubmit={handleCorrect}>
            <Field label="Clock-in (optional)">
              <input type="datetime-local" className="form-control" value={corr.clock_in} onChange={(e) => setCorr({ ...corr, clock_in: e.target.value })} />
            </Field>
            <Field label="Clock-out (optional)">
              <input type="datetime-local" className="form-control" value={corr.clock_out} onChange={(e) => setCorr({ ...corr, clock_out: e.target.value })} />
            </Field>
            <Field label="Status (optional)">
              <select className="form-select" value={corr.status} onChange={(e) => setCorr({ ...corr, status: e.target.value })}>
                <option value="">No change</option>
                <option value="present">Present</option>
                <option value="late">Late</option>
                <option value="absent">Absent</option>
                <option value="incomplete">Incomplete</option>
                <option value="excused">Excused</option>
              </select>
            </Field>
            <Field label="Reason (required, min 5 characters)" hint="Recorded in the audit log with your identity.">
              <input className="form-control" required minLength={5} value={corr.reason} onChange={(e) => setCorr({ ...corr, reason: e.target.value })} />
            </Field>
            <div className="d-flex justify-content-end gap-2">
              <button type="button" className="btn btn-outline-secondary" onClick={() => setCorrecting(null)}>Cancel</button>
              <button type="submit" className="btn btn-primary">Save correction</button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}

export default function Attendance() {
  const { isManager, employeeId } = useAuth();
  const { push } = useToast();
  const [records, setRecords] = useState([]);
  const [summary, setSummary] = useState(null);
  const [todayShifts, setTodayShifts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState({ start: '', end: '', status: '' });

  const today = isoDate(new Date());

  async function load() {
    setLoading(true);
    setError('');
    try {
      const [rows, sum] = await Promise.all([
        listAttendance({ start: filter.start || undefined, end: filter.end || undefined, status: filter.status || undefined }),
        attendanceSummary(filter.start || today, filter.end || today).catch(() => null),
      ]);
      setRecords(rows || []);
      setSummary(sum);
      if (!isManager) {
        const mine = await listShifts({ start_date: today, end_date: today });
        setTodayShifts((mine || []).filter((s) => (s.assignments || []).some((a) => a.employee_id === employeeId && (a.status === 'assigned' || a.status === 'confirmed'))));
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleClock(action, shiftId) {
    try {
      if (action === 'in') await clockIn(shiftId, employeeId);
      else await clockOut(shiftId, employeeId);
      push(action === 'in' ? 'Clocked in' : 'Clocked out', 'success');
      load();
    } catch (err) {
      push(err.message, 'danger');
    }
  }

  return (
    <div className="page">
      <h1 className="page-title">Attendance</h1>
      <p className="page-sub">{isManager ? 'Review records, missing clock-outs and corrections.' : 'Clock in and out of your shifts, and review your history.'}</p>

      {!isManager && todayShifts.length > 0 && (
        <div className="panel">
          <h2>Today&apos;s shifts</h2>
          <ul className="list-group">
            {todayShifts.map((s) => (
              <li key={s.id} className="list-group-item d-flex align-items-center gap-2">
                <span>{String(s.start_time).slice(0, 5)}–{String(s.end_time).slice(0, 5)} · {s.role_required || 'General'}</span>
                <StatusBadge value={s.status} />
                <span className="ms-auto" />
                <button type="button" className="btn btn-sm btn-primary" onClick={() => handleClock('in', s.id)}>Clock in</button>
                <button type="button" className="btn btn-sm btn-outline-primary" onClick={() => handleClock('out', s.id)}>Clock out</button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="panel">
        <form className="row g-2" onSubmit={(e) => { e.preventDefault(); load(); }}>
          <div className="col-md-3">
            <label className="form-label" htmlFor="att-start">From</label>
            <input id="att-start" type="date" className="form-control" value={filter.start} onChange={(e) => setFilter({ ...filter, start: e.target.value })} />
          </div>
          <div className="col-md-3">
            <label className="form-label" htmlFor="att-end">To</label>
            <input id="att-end" type="date" className="form-control" value={filter.end} onChange={(e) => setFilter({ ...filter, end: e.target.value })} />
          </div>
          <div className="col-md-3">
            <label className="form-label" htmlFor="att-status">Status</label>
            <select id="att-status" className="form-select" value={filter.status} onChange={(e) => setFilter({ ...filter, status: e.target.value })}>
              <option value="">All</option>
              <option value="present">Present</option>
              <option value="late">Late</option>
              <option value="absent">Absent</option>
              <option value="incomplete">Incomplete</option>
              <option value="excused">Excused</option>
            </select>
          </div>
          <div className="col-md-3 d-flex align-items-end">
            <button type="submit" className="btn btn-outline-primary">Filter</button>
          </div>
        </form>
      </div>

      {summary && (
        <div className="panel">
          <h2>Summary</h2>
          <p className="mb-0 small">
            {summary.total_records} records · {summary.present} present · {summary.late} late · {summary.absent} absent ·{' '}
            {summary.incomplete} incomplete · {summary.excused} excused · {summary.total_worked_hours?.toFixed(1)} h worked
          </p>
        </div>
      )}

      <ErrorAlert error={error} onRetry={load} />
      {loading ? <Loading /> : records.length === 0 ? (
        <div className="panel"><EmptyState text="No attendance records in this range." /></div>
      ) : (
        <div className="panel">
          <div className="table-responsive">
            <table className="table">
              <thead><tr><th scope="col">Date</th><th scope="col">Clock-in</th><th scope="col">Clock-out</th><th scope="col">Worked</th><th scope="col">Late</th><th scope="col">Status</th></tr></thead>
              <tbody>
                {records.map((r) => (
                  <tr key={r.id}>
                    <td>{r.attendance_date}</td>
                    <td>{fmtDateTime(r.clock_in)}</td>
                    <td>{fmtDateTime(r.clock_out)}{r.is_missing_clockout ? ' (missing)' : ''}</td>
                    <td>{hoursText(r.worked_minutes)}</td>
                    <td>{r.late_minutes ? `${r.late_minutes} min` : '—'}</td>
                    <td><StatusBadge value={r.status} />{r.was_corrected && <small className="text-muted d-block">corrected</small>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {isManager && <ManagerTools onChanged={load} />}
    </div>
  );
}
