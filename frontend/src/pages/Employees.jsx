import { useEffect, useState } from 'react';
import { createEmployee, deactivateEmployee, listEmployees, updateEmployee } from '../api/employees';
import { useToast } from '../components/Toast';
import { ConfirmDialog, EmptyState, ErrorAlert, Field, Loading, Modal, Pagination, StatusBadge } from '../components/ui';

const EMPTY_FORM = {
  email: '',
  full_name: '',
  password: '',
  phone: '',
  skill_level: 'junior',
  skills: '',
  contract_weekly_hours: 40,
  hourly_rate: '',
  is_keyholder: false,
};

function skillsToString(skills) {
  return Array.isArray(skills) ? skills.join(', ') : '';
}

export default function Employees() {
  const { push } = useToast();
  const [rows, setRows] = useState([]);
  const [meta, setMeta] = useState({ page: 1, pages: 1, total: 0 });
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [editing, setEditing] = useState(null);
  const [deactivating, setDeactivating] = useState(null);
  const [busy, setBusy] = useState(false);

  async function load(nextPage = page) {
    setLoading(true);
    setError('');
    try {
      const data = await listEmployees({
        search: search || undefined,
        status: status || undefined,
        page: nextPage,
        page_size: 20,
      });
      setRows(data.items || []);
      setMeta(data.meta || { page: nextPage, pages: 1, total: 0 });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load(1);
  }, []);

  function applySearch(e) {
    e.preventDefault();
    setPage(1);
    load(1);
  }

  function set(key, value) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function handleCreate(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await createEmployee({
        email: form.email.trim(),
        full_name: form.full_name.trim(),
        password: form.password,
        phone: form.phone || null,
        skill_level: form.skill_level,
        skills: form.skills.split(',').map((s) => s.trim()).filter(Boolean),
        contract_weekly_hours: Number(form.contract_weekly_hours) || 40,
        hourly_rate: form.hourly_rate === '' ? null : Number(form.hourly_rate),
        is_keyholder: Boolean(form.is_keyholder),
      });
      push('Employee account created', 'success');
      setShowCreate(false);
      setForm(EMPTY_FORM);
      load(page);
    } catch (err) {
      push(err.message, 'danger');
    } finally {
      setBusy(false);
    }
  }

  async function handleUpdate(e) {
    e.preventDefault();
    if (!editing) return;
    setBusy(true);
    try {
      await updateEmployee(editing.id, {
        full_name: editing.full_name,
        phone: editing.phone || null,
        skill_level: editing.skill_level,
        skills: String(editing.skills || '').split(',').map((s) => s.trim()).filter(Boolean),
        contract_weekly_hours: Number(editing.contract_weekly_hours) || 40,
        is_keyholder: Boolean(editing.is_keyholder),
        status: editing.status,
      });
      push('Employee updated', 'success');
      setEditing(null);
      load(page);
    } catch (err) {
      push(err.message, 'danger');
    } finally {
      setBusy(false);
    }
  }

  async function handleDeactivate() {
    if (!deactivating) return;
    setBusy(true);
    try {
      await deactivateEmployee(deactivating.id);
      push('Employee deactivated', 'info');
      setDeactivating(null);
      load(page);
    } catch (err) {
      push(err.message, 'danger');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <div className="d-flex align-items-center gap-2">
        <div>
          <h1 className="page-title">Employees</h1>
          <p className="page-sub">Manager-provisioned accounts. Creating one here also creates its login.</p>
        </div>
        <span className="ms-auto" />
        <button type="button" className="btn btn-primary btn-sm" onClick={() => setShowCreate(true)}>
          Add employee
        </button>
      </div>

      <div className="panel mt-3">
        <form className="row g-2" onSubmit={applySearch}>
          <div className="col-md-5">
            <label className="form-label" htmlFor="emp-search">Search</label>
            <input
              id="emp-search"
              className="form-control"
              placeholder="Name, email or employee number"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div className="col-md-3">
            <label className="form-label" htmlFor="emp-status">Status</label>
            <select id="emp-status" className="form-select" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
              <option value="on_leave">On leave</option>
            </select>
          </div>
          <div className="col-md-2 d-flex align-items-end">
            <button type="submit" className="btn btn-outline-primary">Search</button>
          </div>
        </form>
      </div>

      <ErrorAlert error={error} onRetry={() => load(page)} />
      {loading ? (
        <Loading />
      ) : rows.length === 0 ? (
        <div className="panel"><EmptyState text="No employees found." /></div>
      ) : (
        <div className="panel">
          <div className="table-responsive">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Number</th>
                  <th scope="col">Name</th>
                  <th scope="col">Email</th>
                  <th scope="col">Skill</th>
                  <th scope="col">Contract h/wk</th>
                  <th scope="col">Status</th>
                  <th scope="col"><span className="visually-hidden">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td>{r.employee_number}</td>
                    <td>{r.full_name}{r.is_keyholder ? ' (keyholder)' : ''}</td>
                    <td>{r.email}</td>
                    <td className="text-capitalize">{r.skill_level}</td>
                    <td>{r.contract_weekly_hours}</td>
                    <td><StatusBadge value={r.status} /></td>
                    <td className="text-end text-nowrap">
                      <button
                        type="button"
                        className="btn btn-sm btn-outline-secondary me-1"
                        onClick={() => setEditing({ ...r, skills: skillsToString(r.skills) })}
                      >
                        Edit
                      </button>
                      {r.status === 'active' && (
                        <button
                          type="button"
                          className="btn btn-sm btn-outline-danger"
                          onClick={() => setDeactivating(r)}
                        >
                          Deactivate
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={meta.page} pages={meta.pages} total={meta.total} onPage={(p) => { setPage(p); load(p); }} />
        </div>
      )}

      {showCreate && (
        <Modal title="Add employee" onClose={() => setShowCreate(false)}>
          <form onSubmit={handleCreate}>
            <Field label="Full name">
              <input className="form-control" required value={form.full_name} onChange={(e) => set('full_name', e.target.value)} />
            </Field>
            <Field label="Work email">
              <input className="form-control" type="email" required value={form.email} onChange={(e) => set('email', e.target.value)} />
            </Field>
            <Field label="Temporary password" hint="At least 8 characters. The employee should change it after first sign-in.">
              <input className="form-control" type="password" required minLength={8} value={form.password} onChange={(e) => set('password', e.target.value)} />
            </Field>
            <div className="row">
              <div className="col-md-6">
                <Field label="Skill level">
                  <select className="form-select" value={form.skill_level} onChange={(e) => set('skill_level', e.target.value)}>
                    <option value="junior">Junior</option>
                    <option value="mid">Mid</option>
                    <option value="senior">Senior</option>
                  </select>
                </Field>
              </div>
              <div className="col-md-6">
                <Field label="Contract hours / week">
                  <input className="form-control" type="number" min={0} max={80} value={form.contract_weekly_hours} onChange={(e) => set('contract_weekly_hours', e.target.value)} />
                </Field>
              </div>
            </div>
            <Field label="Skills (comma separated)">
              <input className="form-control" placeholder="till, stockroom" value={form.skills} onChange={(e) => set('skills', e.target.value)} />
            </Field>
            <Field label="Phone">
              <input className="form-control" value={form.phone} onChange={(e) => set('phone', e.target.value)} />
            </Field>
            <Field label="Hourly rate (optional)">
              <input className="form-control" type="number" min={0} step="0.01" value={form.hourly_rate} onChange={(e) => set('hourly_rate', e.target.value)} />
            </Field>
            <div className="form-check mb-3">
              <input id="emp-keyholder" className="form-check-input" type="checkbox" checked={form.is_keyholder} onChange={(e) => set('is_keyholder', e.target.checked)} />
              <label className="form-check-label" htmlFor="emp-keyholder">Keyholder</label>
            </div>
            <div className="d-flex justify-content-end gap-2">
              <button type="button" className="btn btn-outline-secondary" onClick={() => setShowCreate(false)}>Cancel</button>
              <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? 'Saving…' : 'Create account'}</button>
            </div>
          </form>
        </Modal>
      )}

      {editing && (
        <Modal title={`Edit ${editing.full_name}`} onClose={() => setEditing(null)}>
          <form onSubmit={handleUpdate}>
            <Field label="Full name">
              <input className="form-control" required minLength={2} value={editing.full_name} onChange={(e) => setEditing({ ...editing, full_name: e.target.value })} />
            </Field>
            <Field label="Phone">
              <input className="form-control" value={editing.phone || ''} onChange={(e) => setEditing({ ...editing, phone: e.target.value })} />
            </Field>
            <div className="row">
              <div className="col-md-6">
                <Field label="Skill level">
                  <select className="form-select" value={editing.skill_level} onChange={(e) => setEditing({ ...editing, skill_level: e.target.value })}>
                    <option value="junior">Junior</option>
                    <option value="mid">Mid</option>
                    <option value="senior">Senior</option>
                  </select>
                </Field>
              </div>
              <div className="col-md-6">
                <Field label="Status">
                  <select className="form-select" value={editing.status} onChange={(e) => setEditing({ ...editing, status: e.target.value })}>
                    <option value="active">Active</option>
                    <option value="inactive">Inactive</option>
                    <option value="on_leave">On leave</option>
                  </select>
                </Field>
              </div>
            </div>
            <Field label="Skills (comma separated)">
              <input className="form-control" value={editing.skills || ''} onChange={(e) => setEditing({ ...editing, skills: e.target.value })} />
            </Field>
            <Field label="Contract hours / week">
              <input className="form-control" type="number" min={0} max={80} value={editing.contract_weekly_hours} onChange={(e) => setEditing({ ...editing, contract_weekly_hours: e.target.value })} />
            </Field>
            <div className="form-check mb-3">
              <input id="edit-keyholder" className="form-check-input" type="checkbox" checked={Boolean(editing.is_keyholder)} onChange={(e) => setEditing({ ...editing, is_keyholder: e.target.checked })} />
              <label className="form-check-label" htmlFor="edit-keyholder">Keyholder</label>
            </div>
            <div className="d-flex justify-content-end gap-2">
              <button type="button" className="btn btn-outline-secondary" onClick={() => setEditing(null)}>Cancel</button>
              <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? 'Saving…' : 'Save changes'}</button>
            </div>
          </form>
        </Modal>
      )}

      {deactivating && (
        <ConfirmDialog
          title="Deactivate employee"
          body={`${deactivating.full_name} will no longer be able to sign in or receive new assignments. Continue?`}
          confirmLabel="Deactivate"
          busy={busy}
          onCancel={() => setDeactivating(null)}
          onConfirm={handleDeactivate}
        />
      )}
    </div>
  );
}
