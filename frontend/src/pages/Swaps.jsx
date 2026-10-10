import { useEffect, useState } from 'react';
import { cancelSwap, checkEligibility, createSwap, decideSwap, listSwaps } from '../api/swaps';
import { listShifts } from '../api/shifts';
import { listEmployees } from '../api/employees';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../components/Toast';
import { ConfirmDialog, EmptyState, ErrorAlert, Field, Loading, StatusBadge } from '../components/ui';

export default function Swaps() {
  const { isManager, employeeId } = useAuth();
  const { push } = useToast();
  const [rows, setRows] = useState([]);
  const [shifts, setShifts] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [form, setForm] = useState({ target_employee_id: '', requester_shift_id: '', target_shift_id: '', reason: '' });
  const [eligibility, setEligibility] = useState(null);
  const [checking, setChecking] = useState(false);
  const [deciding, setDeciding] = useState(null);
  const [decision, setDecision] = useState({ decision: 'approved', review_note: '' });
  const [cancelling, setCancelling] = useState(null);

  async function load() {
    setLoading(true);
    setError('');
    try {
      const [swaps, allShifts] = await Promise.all([
        listSwaps({}),
        listShifts({ status: 'published' }).catch(() => []),
      ]);
      setRows(swaps || []);
      setShifts(allShifts || []);
      const emp = await listEmployees({ page_size: 100 }).catch(() => ({ items: [] }));
      setEmployees((emp.items || []).filter((e) => e.id !== employeeId));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const myShifts = shifts.filter((s) => (s.assignments || []).some((a) => a.employee_id === employeeId && (a.status === 'assigned' || a.status === 'confirmed')));

  async function handleCheck(e) {
    e.preventDefault();
    setChecking(true);
    setEligibility(null);
    try {
      setEligibility(await checkEligibility({
        requester_shift_id: form.requester_shift_id,
        target_shift_id: form.target_shift_id,
        target_employee_id: form.target_employee_id,
      }));
    } catch (err) {
      push(err.message, 'danger');
    } finally {
      setChecking(false);
    }
  }

  async function handleCreate(e) {
    e.preventDefault();
    try {
      await createSwap(form);
      push('Swap requested. The other employee and your manager are notified.', 'success');
      setForm({ target_employee_id: '', requester_shift_id: '', target_shift_id: '', reason: '' });
      setEligibility(null);
      load();
    } catch (err) {
      push(err.message, 'danger');
    }
  }

  async function handleDecide() {
    try {
      await decideSwap(deciding.id, decision.decision, decision.review_note || undefined);
      push(`Swap ${decision.decision}`, 'success');
      setDeciding(null);
      load();
    } catch (err) {
      push(err.message, 'danger');
    }
  }

  async function handleCancel() {
    try {
      await cancelSwap(cancelling.id);
      push('Swap request cancelled', 'info');
      setCancelling(null);
      load();
    } catch (err) {
      push(err.message, 'danger');
    }
  }

  return (
    <div className="page">
      <h1 className="page-title">Shift swaps</h1>
      <p className="page-sub">Eligibility is checked before requesting and revalidated before approval.</p>

      {!isManager && (
        <div className="panel">
          <h2>Request a swap</h2>
          {myShifts.length === 0 ? (
            <EmptyState text="You have no upcoming assigned shifts to swap." />
          ) : (
            <form onSubmit={handleCheck}>
              <div className="row g-2">
                <div className="col-md-4">
                  <label className="form-label" htmlFor="swap-mine">My shift</label>
                  <select id="swap-mine" className="form-select" required value={form.requester_shift_id} onChange={(e) => setForm({ ...form, requester_shift_id: e.target.value })}>
                    <option value="">Select…</option>
                    {myShifts.map((s) => (
                      <option key={s.id} value={s.id}>{s.shift_date} {String(s.start_time).slice(0, 5)}</option>
                    ))}
                  </select>
                </div>
                <div className="col-md-4">
                  <label className="form-label" htmlFor="swap-theirs">Their shift</label>
                  <select id="swap-theirs" className="form-select" required value={form.target_shift_id} onChange={(e) => setForm({ ...form, target_shift_id: e.target.value })}>
                    <option value="">Select…</option>
                    {shifts.filter((s) => s.id !== form.requester_shift_id).map((s) => (
                      <option key={s.id} value={s.id}>{s.shift_date} {String(s.start_time).slice(0, 5)} ({(s.assignments || []).map((a) => a.employee_name).join(', ') || 'unassigned'})</option>
                    ))}
                  </select>
                </div>
                <div className="col-md-4">
                  <label className="form-label" htmlFor="swap-emp">Swap with</label>
                  <select id="swap-emp" className="form-select" required value={form.target_employee_id} onChange={(e) => setForm({ ...form, target_employee_id: e.target.value })}>
                    <option value="">Select…</option>
                    {employees.map((emp) => (
                      <option key={emp.id} value={emp.id}>{emp.full_name}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="mt-2">
                <Field label="Reason">
                  <input className="form-control" required minLength={3} value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} placeholder="Why do you need this swap?" />
                </Field>
              </div>
              <div className="d-flex gap-2">
                <button type="submit" className="btn btn-outline-primary btn-sm" disabled={checking || !form.requester_shift_id || !form.target_shift_id || !form.target_employee_id}>
                  {checking ? 'Checking…' : 'Check eligibility'}
                </button>
                <button type="button" className="btn btn-primary btn-sm" disabled={!eligibility?.eligible} onClick={handleCreate}>
                  Send swap request
                </button>
              </div>
              {eligibility && (
                <div className="mt-2">
                  {(eligibility.reasons || []).map((r, i) => (
                    <div key={i} className={`alert py-1 px-2 mb-1 small ${eligibility.eligible ? 'alert-success' : 'alert-danger'}`} role="status">{r}</div>
                  ))}
                  {(eligibility.warnings || []).map((w, i) => (
                    <div key={i} className="alert alert-warning py-1 px-2 mb-1 small" role="status">{w}</div>
                  ))}
                </div>
              )}
            </form>
          )}
        </div>
      )}

      <ErrorAlert error={error} onRetry={load} />
      {loading ? <Loading /> : rows.length === 0 ? (
        <div className="panel"><EmptyState text="No swap requests." /></div>
      ) : (
        <div className="panel">
          <div className="table-responsive">
            <table className="table">
              <thead><tr><th scope="col">Requester</th><th scope="col">Swap with</th><th scope="col">Reason</th><th scope="col">Status</th><th scope="col"><span className="visually-hidden">Actions</span></th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td>{r.requester_name || r.requester_id.slice(0, 8)}</td>
                    <td>{r.target_employee_name || r.target_employee_id.slice(0, 8)}</td>
                    <td className="small">{r.reason}{r.has_conflict && <span className="d-block text-warning">Conflict flagged — needs resolution</span>}</td>
                    <td><StatusBadge value={r.status} /></td>
                    <td className="text-end text-nowrap">
                      {isManager && r.status === 'pending' && (
                        <button type="button" className="btn btn-sm btn-outline-primary" onClick={() => { setDeciding(r); setDecision({ decision: 'approved', review_note: '' }); }}>
                          Decide
                        </button>
                      )}
                      {r.status === 'pending' && (
                        <button type="button" className="btn btn-sm btn-outline-secondary ms-1" onClick={() => setCancelling(r)}>
                          Cancel
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {deciding && (
        <ConfirmDialog
          title="Decide swap request"
          body="Approving revalidates both halves and applies the exchange atomically. Rejecting leaves both schedules untouched."
          confirmLabel={decision.decision === 'approved' ? 'Approve swap' : 'Reject swap'}
          onCancel={() => setDeciding(null)}
          onConfirm={handleDecide}
        />
      )}
      {deciding && (
        <div className="panel">
          <Field label="Decision">
            <select className="form-select" value={decision.decision} onChange={(e) => setDecision({ ...decision, decision: e.target.value })}>
              <option value="approved">Approve</option>
              <option value="rejected">Reject</option>
            </select>
          </Field>
          <Field label="Review note (optional)">
            <input className="form-control" value={decision.review_note} onChange={(e) => setDecision({ ...decision, review_note: e.target.value })} />
          </Field>
        </div>
      )}
      {cancelling && (
        <ConfirmDialog
          title="Cancel swap request"
          body="The pending swap request will be withdrawn."
          confirmLabel="Cancel request"
          onCancel={() => setCancelling(null)}
          onConfirm={handleCancel}
        />
      )}
    </div>
  );
}
