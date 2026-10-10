import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  assignEmployee,
  cancelShift,
  confirmAssignment,
  createShift,
  deleteShift,
  getShift,
  publishShifts,
  unassignEmployee,
  validateAssignment,
} from '../api/shifts';
import { applyProposal, generateProposal, getCalendar, getCoverage } from '../api/scheduling';
import { listEmployees } from '../api/employees';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../components/Toast';
import { ConfirmDialog, EmptyState, ErrorAlert, Field, Loading, Modal, StatusBadge } from '../components/ui';
import { addDays, fmtDate, isoDate, mondayOf, shortTime } from '../utils/format';

function ShiftDetail({ shiftId, onClose, onChanged, employees }) {
  const { isManager, employeeId } = useAuth();
  const { push } = useToast();
  const [shift, setShift] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [assignOpen, setAssignOpen] = useState(false);
  const [candidate, setCandidate] = useState('');
  const [validation, setValidation] = useState(null);
  const [cancelReason, setCancelReason] = useState('');
  const [showCancel, setShowCancel] = useState(false);

  const load = useCallback(async () => {
    try {
      setShift(await getShift(shiftId));
    } catch (err) {
      setError(err.message);
    }
  }, [shiftId]);

  useEffect(() => {
    load();
  }, [load]);

  async function previewAssign(empId) {
    setCandidate(empId);
    setValidation(null);
    if (!empId) return;
    try {
      setValidation(await validateAssignment({ shift_id: shiftId, employee_id: empId }));
    } catch (err) {
      push(err.message, 'danger');
    }
  }

  async function doAssign(force) {
    setBusy(true);
    try {
      await assignEmployee({ shift_id: shiftId, employee_id: candidate, force });
      push('Employee assigned', 'success');
      setAssignOpen(false);
      setCandidate('');
      setValidation(null);
      await load();
      onChanged();
    } catch (err) {
      push(err.message, 'danger');
    } finally {
      setBusy(false);
    }
  }

  async function doUnassign(assignmentId) {
    setBusy(true);
    try {
      await unassignEmployee(assignmentId);
      push('Assignment removed', 'info');
      await load();
      onChanged();
    } catch (err) {
      push(err.message, 'danger');
    } finally {
      setBusy(false);
    }
  }

  async function doConfirm(assignmentId) {
    try {
      await confirmAssignment(assignmentId);
      push('Shift confirmed', 'success');
      await load();
      onChanged();
    } catch (err) {
      push(err.message, 'danger');
    }
  }

  async function doCancel() {
    setBusy(true);
    try {
      await cancelShift(shiftId, cancelReason);
      push('Shift cancelled', 'info');
      setShowCancel(false);
      onChanged();
      onClose();
    } catch (err) {
      push(err.message, 'danger');
    } finally {
      setBusy(false);
    }
  }

  async function doDelete() {
    setBusy(true);
    try {
      await deleteShift(shiftId);
      push('Draft shift deleted', 'info');
      onChanged();
      onClose();
    } catch (err) {
      push(err.message, 'danger');
    } finally {
      setBusy(false);
    }
  }

  if (error) return <Modal title="Shift" onClose={onClose}><ErrorAlert error={error} /></Modal>;
  if (!shift) return <Modal title="Shift" onClose={onClose}><Loading /></Modal>;

  const ownAssignment = shift.assignments?.find((a) => a.employee_id === employeeId && (a.status === 'assigned' || a.status === 'confirmed'));

  return (
    <Modal title={`Shift — ${shift.shift_date} ${shortTime(shift.start_time)}–${shortTime(shift.end_time)}`} onClose={onClose} wide>
      <p className="small text-muted mb-2">
        {shift.role_required || 'General'} · {shift.required_employees} required · {shift.duration_hours} h
        {shift.is_overnight ? ' · overnight' : ''} · <StatusBadge value={shift.status} /> <StatusBadge value={shift.coverage_status} />
      </p>
      {shift.notes && <p className="small">{shift.notes}</p>}
      <h3 className="fs-6 mt-3">Assigned staff ({shift.assigned_count}/{shift.required_employees})</h3>
      {shift.assignments?.length === 0 ? (
        <EmptyState text="Nobody assigned yet." />
      ) : (
        <ul className="list-group mb-3">
          {shift.assignments.map((a) => (
            <li key={a.id} className="list-group-item d-flex align-items-center gap-2">
              <span>{a.employee_name} <small className="text-muted">({a.employee_number})</small></span>
              <StatusBadge value={a.status} />
              {a.is_auto_assigned && <small className="text-muted">auto</small>}
              <span className="ms-auto" />
              {!isManager && a.id === ownAssignment?.id && a.status === 'assigned' && (
                <button type="button" className="btn btn-sm btn-outline-primary" onClick={() => doConfirm(a.id)}>
                  Confirm my shift
                </button>
              )}
              {isManager && (
                <button type="button" className="btn btn-sm btn-outline-danger" onClick={() => doUnassign(a.id)} disabled={busy}>
                  Remove
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {isManager && shift.status !== 'cancelled' && (
        <div className="d-flex flex-wrap gap-2">
          <button type="button" className="btn btn-sm btn-primary" onClick={() => setAssignOpen((v) => !v)}>
            Assign staff
          </button>
          {shift.status === 'draft' && (
            <>
              <button type="button" className="btn btn-sm btn-outline-primary" onClick={async () => { await publishShifts([shiftId]); push('Shift published', 'success'); onChanged(); onClose(); }}>
                Publish
              </button>
              <button type="button" className="btn btn-sm btn-outline-danger" onClick={doDelete} disabled={busy}>
                Delete draft
              </button>
            </>
          )}
          <button type="button" className="btn btn-sm btn-outline-danger" onClick={() => setShowCancel(true)}>
            Cancel shift
          </button>
        </div>
      )}

      {isManager && assignOpen && (
        <div className="border rounded p-3 mt-3">
          <Field label="Employee">
            <select className="form-select" value={candidate} onChange={(e) => previewAssign(e.target.value)}>
              <option value="">Select…</option>
              {(employees || []).map((e) => (
                <option key={e.id} value={e.id}>{e.full_name} ({e.employee_number})</option>
              ))}
            </select>
          </Field>
          {validation && (
            <div className="mb-2">
              {validation.violations?.map((v) => (
                <div key={v.code} className="alert alert-danger py-1 px-2 mb-1 small" role="alert">{v.message} (blocking)</div>
              ))}
              {validation.warnings?.map((w) => (
                <div key={w.code} className="alert alert-warning py-1 px-2 mb-1 small" role="alert">{w.message}</div>
              ))}
              {validation.valid && validation.warnings?.length === 0 && (
                <div className="alert alert-success py-1 px-2 mb-1 small" role="status">No conflicts — safe to assign.</div>
              )}
            </div>
          )}
          <div className="d-flex gap-2">
            <button type="button" className="btn btn-sm btn-primary" disabled={!candidate || !validation?.valid || busy} onClick={() => doAssign(false)}>
              Assign
            </button>
            {validation && !validation.valid && validation.warnings?.length > 0 && (
              <button type="button" className="btn btn-sm btn-outline-warning" disabled={busy} onClick={() => doAssign(true)} title="Proceed despite warnings (blocking violations can never be forced)">
                Assign despite warnings
              </button>
            )}
          </div>
        </div>
      )}

      {showCancel && (
        <ConfirmDialog
          title="Cancel shift"
          body="Cancelling releases all active assignments and notifies staff. Give a reason:"
          confirmLabel="Cancel shift"
          busy={busy}
          onCancel={() => setShowCancel(false)}
          onConfirm={doCancel}
        />
      )}
      {showCancel && (
        <div className="mt-2">
          <Field label="Cancellation reason (min 3 characters)">
            <input className="form-control" value={cancelReason} onChange={(e) => setCancelReason(e.target.value)} placeholder="e.g. Store closed for refit" />
          </Field>
        </div>
      )}
    </Modal>
  );
}

function CreateShiftForm({ date, onDone }) {
  const { push } = useToast();
  const [form, setForm] = useState({ shift_date: date, start_time: '09:00', end_time: '17:00', role_required: '', required_skill: '', required_employees: 1, notes: '', publish: false });
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await createShift({
        shift_date: form.shift_date,
        start_time: form.start_time,
        end_time: form.end_time,
        role_required: form.role_required || null,
        required_skill: form.required_skill || null,
        required_employees: Number(form.required_employees) || 1,
        notes: form.notes || null,
        publish: form.publish,
      });
      push('Shift created', 'success');
      onDone();
    } catch (err) {
      push(err.message, 'danger');
    } finally {
      setBusy(false);
    }
  }

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  return (
    <form onSubmit={submit}>
      <div className="row">
        <div className="col-md-4"><Field label="Date"><input type="date" className="form-control" required value={form.shift_date} onChange={(e) => set('shift_date', e.target.value)} /></Field></div>
        <div className="col-md-4"><Field label="Start"><input type="time" className="form-control" required value={form.start_time} onChange={(e) => set('start_time', e.target.value)} /></Field></div>
        <div className="col-md-4"><Field label="End (earlier than start = overnight)"><input type="time" className="form-control" required value={form.end_time} onChange={(e) => set('end_time', e.target.value)} /></Field></div>
      </div>
      <div className="row">
        <div className="col-md-4"><Field label="Role"><input className="form-control" value={form.role_required} onChange={(e) => set('role_required', e.target.value)} placeholder="till" /></Field></div>
        <div className="col-md-4"><Field label="Required skill"><input className="form-control" value={form.required_skill} onChange={(e) => set('required_skill', e.target.value)} placeholder="till" /></Field></div>
        <div className="col-md-4"><Field label="Staff needed"><input type="number" min={1} max={20} className="form-control" value={form.required_employees} onChange={(e) => set('required_employees', e.target.value)} /></Field></div>
      </div>
      <Field label="Notes"><input className="form-control" value={form.notes} onChange={(e) => set('notes', e.target.value)} /></Field>
      <div className="form-check mb-3">
        <input id="shift-publish" type="checkbox" className="form-check-input" checked={form.publish} onChange={(e) => set('publish', e.target.checked)} />
        <label className="form-check-label" htmlFor="shift-publish">Publish immediately</label>
      </div>
      <div className="d-flex justify-content-end gap-2">
        <button type="button" className="btn btn-outline-secondary" onClick={onDone}>Close</button>
        <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? 'Saving…' : 'Create shift'}</button>
      </div>
    </form>
  );
}

function AutoSchedule({ weekStart, weekEnd, onApplied }) {
  const { push } = useToast();
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [publish, setPublish] = useState(false);

  async function run() {
    setBusy(true);
    try {
      setResult(await generateProposal({ start_date: isoDate(weekStart), end_date: isoDate(weekEnd) }));
    } catch (err) {
      push(err.message, 'danger');
    } finally {
      setBusy(false);
    }
  }

  async function apply() {
    if (!result?.proposals?.length) return;
    setBusy(true);
    try {
      await applyProposal({ start_date: isoDate(weekStart), end_date: isoDate(weekEnd), proposals: result.proposals, publish });
      push(`Applied ${result.proposals.length} assignment(s)${publish ? ' and published' : ''}`, 'success');
      setResult(null);
      onApplied();
    } catch (err) {
      push(err.message, 'danger');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel">
      <h2>Automatic scheduling proposal</h2>
      <p className="small text-muted">Deterministic suggestions for this week. Nothing is applied until you confirm below.</p>
      <button type="button" className="btn btn-outline-primary btn-sm" disabled={busy} onClick={run}>
        {busy ? 'Working…' : 'Generate proposal'}
      </button>
      {result && (
        <div className="mt-3">
          <p className="small">{result.summary}</p>
          {result.proposals?.length > 0 ? (
            <div className="table-responsive">
              <table className="table">
                <thead><tr><th scope="col">Employee</th><th scope="col">Shift</th><th scope="col">Why</th></tr></thead>
                <tbody>
                  {result.proposals.map((p, i) => (
                    <tr key={i}>
                      <td>{p.employee_name}</td>
                      <td className="small">{p.shift_id.slice(0, 8)}…</td>
                      <td className="small">{(p.reasons || []).join('; ')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <EmptyState text="No fillable shifts in this range." />}
          {result.unfillable?.length > 0 && (
            <>
              <h3 className="fs-6 mt-2">Could not fill ({result.unfillable.length})</h3>
              <ul className="small">
                {result.unfillable.map((u) => (
                  <li key={u.shift_id}>{u.shift_date} {shortTime(u.start_time)}–{shortTime(u.end_time)}: {u.reason}</li>
                ))}
              </ul>
            </>
          )}
          {result.proposals?.length > 0 && (
            <div className="d-flex align-items-center gap-2 mt-2">
              <div className="form-check">
                <input id="apply-publish" type="checkbox" className="form-check-input" checked={publish} onChange={(e) => setPublish(e.target.checked)} />
                <label className="form-check-label small" htmlFor="apply-publish">Publish affected shifts too</label>
              </div>
              <button type="button" className="btn btn-primary btn-sm" disabled={busy} onClick={apply}>
                Apply {result.proposals.length} assignment(s)
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function Schedule() {
  const { isManager } = useAuth();
  const { push } = useToast();
  const [weekStart, setWeekStart] = useState(() => mondayOf(new Date()));
  const [calendar, setCalendar] = useState(null);
  const [coverage, setCoverage] = useState(null);
  const [employees, setEmployees] = useState([]);
  const [tab, setTab] = useState('calendar');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedShift, setSelectedShift] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [publishBusy, setPublishBusy] = useState(false);

  const weekEnd = useMemo(() => addDays(weekStart, 6), [weekStart]);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [cal, cov] = await Promise.all([
        getCalendar(isoDate(weekStart), isoDate(weekEnd)),
        getCoverage(isoDate(weekStart), isoDate(weekEnd)),
      ]);
      setCalendar(cal);
      setCoverage(cov);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [weekStart, weekEnd]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (isManager) {
      listEmployees({ page_size: 100 }).then((d) => setEmployees(d.items || [])).catch(() => {});
    }
  }, [isManager]);

  async function publishDrafts() {
    const drafts = (coverage?.rows || []).filter((r) => String(r.shift_status).toLowerCase() === 'draft');
    if (drafts.length === 0) {
      push('No draft shifts to publish', 'info');
      return;
    }
    setPublishBusy(true);
    try {
      await publishShifts(drafts.map((d) => d.shift_id));
      push(`${drafts.length} shift(s) published`, 'success');
      load();
    } catch (err) {
      push(err.message, 'danger');
    } finally {
      setPublishBusy(false);
    }
  }

  return (
    <div className="page">
      <div className="d-flex align-items-center gap-2 flex-wrap">
        <div>
          <h1 className="page-title">Schedule</h1>
          <p className="page-sub">Week of {fmtDate(weekStart)} — {fmtDate(weekEnd)}</p>
        </div>
        <span className="ms-auto" />
        <button type="button" className="btn btn-sm btn-outline-secondary" onClick={() => setWeekStart((w) => addDays(w, -7))}>Previous</button>
        <button type="button" className="btn btn-sm btn-outline-secondary" onClick={() => setWeekStart(mondayOf(new Date()))}>This week</button>
        <button type="button" className="btn btn-sm btn-outline-secondary" onClick={() => setWeekStart((w) => addDays(w, 7))}>Next</button>
        {isManager && (
          <>
            <button type="button" className="btn btn-sm btn-primary" onClick={() => setShowCreate(true)}>New shift</button>
            <button type="button" className="btn btn-sm btn-outline-primary" disabled={publishBusy} onClick={publishDrafts}>
              {publishBusy ? 'Publishing…' : 'Publish drafts'}
            </button>
          </>
        )}
      </div>

      <ul className="nav nav-tabs mt-3" role="tablist">
        <li className="nav-item" role="presentation">
          <button type="button" role="tab" aria-selected={tab === 'calendar'} className={`nav-link${tab === 'calendar' ? ' active' : ''}`} onClick={() => setTab('calendar')}>Calendar</button>
        </li>
        <li className="nav-item" role="presentation">
          <button type="button" role="tab" aria-selected={tab === 'coverage'} className={`nav-link${tab === 'coverage' ? ' active' : ''}`} onClick={() => setTab('coverage')}>Coverage</button>
        </li>
        {isManager && (
          <li className="nav-item" role="presentation">
            <button type="button" role="tab" aria-selected={tab === 'auto'} className={`nav-link${tab === 'auto' ? ' active' : ''}`} onClick={() => setTab('auto')}>Auto-schedule</button>
          </li>
        )}
      </ul>

      <div className="mt-3">
        <ErrorAlert error={error} onRetry={load} />
        {loading && <Loading />}
        {!loading && tab === 'calendar' && (
          <div className="cal-grid">
            {(calendar?.days || []).map((day) => {
              const isToday = isoDate(new Date()) === day.date;
              return (
                <div key={day.date} className={`cal-day${isToday ? ' today' : ''}`}>
                  <div className="cal-day-head"><span>{fmtDate(day.date)}</span></div>
                  {(day.shifts || []).length === 0 && <p className="text-muted small mb-0">No shifts</p>}
                  {(day.shifts || []).map((entry) => {
                    const s = entry.shift;
                    return (
                      <button key={s.id} type="button" className="shift-block" onClick={() => setSelectedShift(s.id)}>
                        <span className="t">{shortTime(s.start_time)}–{shortTime(s.end_time)}</span>
                        <br />
                        {s.role_required || 'General'} · {entry.assigned_count}/{s.required_employees}
                        <br />
                        <StatusBadge value={entry.coverage_status} /> <StatusBadge value={s.status} />
                      </button>
                    );
                  })}
                </div>
              );
            })}
          </div>
        )}
        {!loading && tab === 'coverage' && (
          <div className="panel">
            <h2>Coverage {coverage?.summary ? `(fully staffed ${coverage.summary.fully_staffed}, understaffed ${coverage.summary.understaffed}, unassigned ${coverage.summary.unassigned}, cancelled ${coverage.summary.cancelled})` : ''}</h2>
            {(coverage?.rows || []).length === 0 ? (
              <EmptyState text="No shifts in this week." />
            ) : (
              <div className="table-responsive">
                <table className="table">
                  <thead><tr><th scope="col">Date</th><th scope="col">Time</th><th scope="col">Role</th><th scope="col">Staffing</th><th scope="col">Coverage</th><th scope="col">Shift state</th></tr></thead>
                  <tbody>
                    {coverage.rows.map((r) => (
                      <tr key={r.shift_id}>
                        <td>{r.shift_date}</td>
                        <td>{shortTime(r.start_time)}–{shortTime(r.end_time)}</td>
                        <td>{r.role_required || 'General'}</td>
                        <td>{r.assigned_count}/{r.required_employees}</td>
                        <td><StatusBadge value={r.coverage_status} /></td>
                        <td><StatusBadge value={r.shift_status} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
        {!loading && tab === 'auto' && isManager && (
          <AutoSchedule weekStart={weekStart} weekEnd={weekEnd} onApplied={load} />
        )}
      </div>

      {selectedShift && (
        <ShiftDetail
          shiftId={selectedShift}
          employees={employees}
          onClose={() => setSelectedShift(null)}
          onChanged={load}
        />
      )}
      {showCreate && (
        <Modal title="New shift" onClose={() => setShowCreate(false)}>
          <CreateShiftForm date={isoDate(weekStart)} onDone={() => { setShowCreate(false); load(); }} />
        </Modal>
      )}
    </div>
  );
}
