import { useEffect, useState } from 'react';
import { cancelLeave, decideLeave, fileLeave, listLeave } from '../api/leave';
import { listEmployees } from '../api/employees';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../components/Toast';
import { ConfirmDialog, EmptyState, ErrorAlert, Field, Loading, StatusBadge } from '../components/ui';

export default function Leave() {
  const { isManager, employeeId } = useAuth();
  const { push } = useToast();
  const [rows, setRows] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');
  const [form, setForm] = useState({ leave_type: 'annual', start_date: '', end_date: '', reason: '', employee_id: '' });
  const [deciding, setDeciding] = useState(null);
  const [decision, setDecision] = useState({ decision: 'approved', review_note: '' });
  const [cancelling, setCancelling] = useState(null);

  async function load() {
    setLoading(true);
    setError('');
    try {
      setRows((await listLeave({ status: status || undefined })) || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    if (isManager) listEmployees({ page_size: 100 }).then((d) => setEmployees(d.items || [])).catch(() => {});
  }, []);

  async function handleFile(e) {
    e.preventDefault();
    try {
      await fileLeave(
        { leave_type: form.leave_type, start_date: form.start_date, end_date: form.end_date, reason: form.reason },
        isManager && form.employee_id ? form.employee_id : undefined,
      );
      push('Leave request filed', 'success');
      setForm({ leave_type: 'annual', start_date: '', end_date: '', reason: '', employee_id: '' });
      load();
    } catch (err) {
      push(err.message, 'danger');
    }
  }

  async function handleDecide() {
    try {
      await decideLeave(deciding.id, decision.decision, decision.review_note || undefined);
      push(`Leave ${decision.decision}`, decision.decision === 'approved' ? 'success' : 'info');
      setDeciding(null);
      load();
    } catch (err) {
      push(err.message, 'danger');
    }
  }

  async function handleCancel() {
    try {
      await cancelLeave(cancelling.id);
      push('Leave request cancelled', 'info');
      setCancelling(null);
      load();
    } catch (err) {
      push(err.message, 'danger');
    }
  }

  return (
    <div className="page">
      <h1 className="page-title">Leave requests</h1>
      <p className="page-sub">Approving leave automatically releases any overlapping assignments.</p>

      <div className="panel">
        <h2>New leave request</h2>
        <form className="row g-2" onSubmit={handleFile}>
          {isManager && (
            <div className="col-md-3">
              <label className="form-label" htmlFor="leave-emp">Employee (blank = you)</label>
              <select id="leave-emp" className="form-select" value={form.employee_id} onChange={(e) => setForm({ ...form, employee_id: e.target.value })}>
                <option value="">Me</option>
                {employees.map((emp) => (
                  <option key={emp.id} value={emp.id}>{emp.full_name}</option>
                ))}
              </select>
            </div>
          )}
          <div className="col-md-2">
            <label className="form-label" htmlFor="leave-type">Type</label>
            <select id="leave-type" className="form-select" value={form.leave_type} onChange={(e) => setForm({ ...form, leave_type: e.target.value })}>
              <option value="annual">Annual</option>
              <option value="sick">Sick</option>
              <option value="unpaid">Unpaid</option>
              <option value="other">Other</option>
            </select>
          </div>
          <div className="col-md-2">
            <label className="form-label" htmlFor="leave-start">From</label>
            <input id="leave-start" type="date" className="form-control" required value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} />
          </div>
          <div className="col-md-2">
            <label className="form-label" htmlFor="leave-end">To</label>
            <input id="leave-end" type="date" className="form-control" required value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} />
          </div>
          <div className="col-md-3">
            <label className="form-label" htmlFor="leave-reason">Reason</label>
            <input id="leave-reason" className="form-control" required minLength={3} value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} />
          </div>
          <div className="col-12 mt-2">
            <button type="submit" className="btn btn-primary btn-sm">File request</button>
          </div>
        </form>
      </div>

      <div className="panel">
        <form className="row g-2" onSubmit={(e) => { e.preventDefault(); load(); }}>
          <div className="col-md-3">
            <label className="form-label" htmlFor="leave-filter">Status</label>
            <select id="leave-filter" className="form-select" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All</option>
              <option value="pending">Pending</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
              <option value="cancelled">Cancelled</option>
            </select>
          </div>
          <div className="col-md-2 d-flex align-items-end">
            <button type="submit" className="btn btn-outline-primary">Filter</button>
          </div>
        </form>
      </div>

      <ErrorAlert error={error} onRetry={load} />
      {loading ? <Loading /> : rows.length === 0 ? (
        <div className="panel"><EmptyState text="No leave requests." /></div>
      ) : (
        <div className="panel">
          <div className="table-responsive">
            <table className="table">
              <thead><tr><th scope="col">Employee</th><th scope="col">Type</th><th scope="col">Dates</th><th scope="col">Reason</th><th scope="col">Status</th><th scope="col"><span className="visually-hidden">Actions</span></th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td>{r.employee_name || r.employee_id.slice(0, 8)}</td>
                    <td className="text-capitalize">{r.leave_type}</td>
                    <td>{r.start_date} â†’ {r.end_date}</td>
                    <td className="small">{r.reason}{r.has_conflict && <span className="d-block text-warning">Conflicts with assigned shift(s) â€” needs review</span>}</td>
                    <td><StatusBadge value={r.status} /></td>
                    <td className="text-end text-nowrap">
                      {isManager && r.status === 'pending' && (
                        <button type="button" className="btn btn-sm btn-outline-primary" onClick={() => { setDeciding(r); setDecision({ decision: 'approved', review_note: '' }); }}>
                          Decide
                        </button>
                      )}
                      {(r.status === 'pending') && (isManager || r.employee_id === employeeId) && (
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
          title={`Decide leave (${deciding.start_date} â†’ ${deciding.end_date})`}
          body={deciding.has_conflict ? 'This request overlaps assigned shifts. Approving releases those assignments.' : 'Approve or reject this request?'}
          confirmLabel={decision.decision === 'approved' ? 'Approve' : 'Reject'}
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
          title="Cancel leave request"
          body="The pending request will be withdrawn."
          confirmLabel="Cancel request"
          onCancel={() => setCancelling(null)}
          onConfirm={handleCancel}
        />
      )}
    </div>
  );
}
