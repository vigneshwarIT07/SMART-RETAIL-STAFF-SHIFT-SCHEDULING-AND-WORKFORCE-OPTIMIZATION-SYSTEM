import { useEffect, useState } from 'react';
import { createAvailability, deleteAvailability, listAvailability, reviewAvailability } from '../api/availability';
import { listEmployees } from '../api/employees';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../components/Toast';
import { ConfirmDialog, EmptyState, ErrorAlert, Field, Loading, StatusBadge } from '../components/ui';
import { shortTime, weekdayName } from '../utils/format';

export default function Availability() {
  const { isManager, employeeId } = useAuth();
  const { push } = useToast();
  const [rows, setRows] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [selected, setSelected] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [form, setForm] = useState({ weekday: 0, start_time: '09:00', end_time: '17:00', availability_type: 'available', note: '' });
  const [deleting, setDeleting] = useState(null);

  const activeId = isManager ? selected : employeeId;

  async function load(empId = activeId) {
    if (!empId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError('');
    try {
      setRows((await listAvailability(empId)) || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (isManager) {
      listEmployees({ page_size: 100 }).then((d) => {
        const items = d.items || [];
        setEmployees(items);
        if (items.length > 0) setSelected(items[0].id);
      }).catch(() => setLoading(false));
    } else {
      setSelected(employeeId || '');
    }
  }, []);

  useEffect(() => {
    if (activeId) load(activeId);
  }, [activeId]);

  async function handleCreate(e) {
    e.preventDefault();
    try {
      await createAvailability(activeId, {
        weekday: Number(form.weekday),
        start_time: form.start_time,
        end_time: form.end_time,
        availability_type: form.availability_type,
        note: form.note || null,
      });
      push('Availability saved', 'success');
      load(activeId);
    } catch (err) {
      push(err.message, 'danger');
    }
  }

  async function handleDelete() {
    try {
      await deleteAvailability(deleting.id);
      push('Availability removed', 'info');
      setDeleting(null);
      load(activeId);
    } catch (err) {
      push(err.message, 'danger');
    }
  }

  async function loadReview() {
    try {
      const all = await reviewAvailability();
      setRows(all || []);
    } catch (err) {
      push(err.message, 'danger');
    }
  }

  return (
    <div className="page">
      <h1 className="page-title">Availability</h1>
      <p className="page-sub">Weekly windows the scheduler respects when proposing assignments.</p>

      {isManager && (
        <div className="panel">
          <div className="row g-2 align-items-end">
            <div className="col-md-4">
              <label className="form-label" htmlFor="avail-emp">Employee</label>
              <select id="avail-emp" className="form-select" value={selected} onChange={(e) => setSelected(e.target.value)}>
                {employees.map((emp) => (
                  <option key={emp.id} value={emp.id}>{emp.full_name}</option>
                ))}
              </select>
            </div>
            <div className="col-md-4">
              <button type="button" className="btn btn-outline-secondary btn-sm" onClick={loadReview}>
                Review whole store
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="panel">
        <h2>Add window</h2>
        <form className="row g-2" onSubmit={handleCreate}>
          <div className="col-md-2">
            <label className="form-label" htmlFor="avail-day">Day</label>
            <select id="avail-day" className="form-select" value={form.weekday} onChange={(e) => setForm({ ...form, weekday: e.target.value })}>
              {[0, 1, 2, 3, 4, 5, 6].map((d) => (
                <option key={d} value={d}>{weekdayName(d)}</option>
              ))}
            </select>
          </div>
          <div className="col-md-2">
            <label className="form-label" htmlFor="avail-from">From</label>
            <input id="avail-from" type="time" className="form-control" required value={form.start_time} onChange={(e) => setForm({ ...form, start_time: e.target.value })} />
          </div>
          <div className="col-md-2">
            <label className="form-label" htmlFor="avail-to">To</label>
            <input id="avail-to" type="time" className="form-control" required value={form.end_time} onChange={(e) => setForm({ ...form, end_time: e.target.value })} />
          </div>
          <div className="col-md-2">
            <label className="form-label" htmlFor="avail-type">Type</label>
            <select id="avail-type" className="form-select" value={form.availability_type} onChange={(e) => setForm({ ...form, availability_type: e.target.value })}>
              <option value="available">Available</option>
              <option value="unavailable">Unavailable</option>
            </select>
          </div>
          <div className="col-md-3">
            <label className="form-label" htmlFor="avail-note">Note</label>
            <input id="avail-note" className="form-control" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} placeholder="e.g. university mornings" />
          </div>
          <div className="col-md-1 d-flex align-items-end">
            <button type="submit" className="btn btn-primary btn-sm">Add</button>
          </div>
        </form>
      </div>

      <ErrorAlert error={error} onRetry={() => load(activeId)} />
      {loading ? <Loading /> : rows.length === 0 ? (
        <div className="panel"><EmptyState text="No availability windows yet." /></div>
      ) : (
        <div className="panel">
          <Field label=" ">
            <div className="table-responsive">
              <table className="table">
                <thead><tr><th scope="col">Day</th><th scope="col">Window</th><th scope="col">Type</th><th scope="col">Note</th><th scope="col"><span className="visually-hidden">Actions</span></th></tr></thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.id}>
                      <td>{weekdayName(r.weekday)}</td>
                      <td>{shortTime(r.start_time)}â€“{shortTime(r.end_time)}</td>
                      <td><StatusBadge value={r.availability_type} /></td>
                      <td className="small">{r.note || 'â€”'}{r.employee_name ? ` (${r.employee_name})` : ''}</td>
                      <td className="text-end">
                        <button type="button" className="btn btn-sm btn-outline-danger" onClick={() => setDeleting(r)}>Remove</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Field>
        </div>
      )}

      {deleting && (
        <ConfirmDialog
          title="Remove availability window"
          body="This window will no longer constrain scheduling."
          confirmLabel="Remove"
          onCancel={() => setDeleting(null)}
          onConfirm={handleDelete}
        />
      )}
    </div>
  );
}
