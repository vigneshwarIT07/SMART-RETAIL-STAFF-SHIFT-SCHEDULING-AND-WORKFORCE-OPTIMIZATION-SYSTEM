import { useEffect, useState } from 'react';
import { getHealth, getOwnStore, updateOwnStore } from '../api/stores';
import { changePassword } from '../api/auth';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../components/Toast';
import { ErrorAlert, Field, Loading, StatusBadge } from '../components/ui';

export default function StoreSettings() {
  const { isManager } = useAuth();
  const { push } = useToast();
  const [store, setStore] = useState(null);
  const [health, setHealth] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [edit, setEdit] = useState({ name: '', address: '', phone: '', timezone: '' });
  const [pw, setPw] = useState({ current_password: '', new_password: '' });

  async function load() {
    setLoading(true);
    setError('');
    try {
      const [s, h] = await Promise.all([getOwnStore(), getHealth().catch(() => null)]);
      setStore(s);
      setHealth(h);
      setEdit({ name: s.name || '', address: s.address || '', phone: s.phone || '', timezone: s.timezone || '' });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleStore(e) {
    e.preventDefault();
    try {
      const updated = await updateOwnStore(edit);
      setStore(updated);
      push('Store updated', 'success');
    } catch (err) {
      push(err.message, 'danger');
    }
  }

  async function handlePassword(e) {
    e.preventDefault();
    try {
      await changePassword(pw.current_password, pw.new_password);
      push('Password changed', 'success');
      setPw({ current_password: '', new_password: '' });
    } catch (err) {
      push(err.message, 'danger');
    }
  }

  return (
    <div className="page">
      <h1 className="page-title">{isManager ? 'Store settings' : 'Store'}</h1>
      <p className="page-sub">Your store profile and account security.</p>
      <ErrorAlert error={error} onRetry={load} />
      {loading && <Loading />}
      {store && (
        <>
          <div className="panel">
            <h2>Store profile</h2>
            {isManager ? (
              <form onSubmit={handleStore}>
                <Field label="Store name">
                  <input className="form-control" required value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} />
                </Field>
                <Field label="Address">
                  <input className="form-control" value={edit.address} onChange={(e) => setEdit({ ...edit, address: e.target.value })} />
                </Field>
                <div className="row">
                  <div className="col-md-6">
                    <Field label="Phone">
                      <input className="form-control" value={edit.phone} onChange={(e) => setEdit({ ...edit, phone: e.target.value })} />
                    </Field>
                  </div>
                  <div className="col-md-6">
                    <Field label="Timezone">
                      <input className="form-control" value={edit.timezone} onChange={(e) => setEdit({ ...edit, timezone: e.target.value })} placeholder="UTC" />
                    </Field>
                  </div>
                </div>
                <button type="submit" className="btn btn-primary btn-sm">Save store</button>
              </form>
            ) : (
              <dl className="row mb-0 small">
                <dt className="col-sm-3">Name</dt><dd className="col-sm-9">{store.name}</dd>
                <dt className="col-sm-3">Address</dt><dd className="col-sm-9">{store.address || 'â€”'}</dd>
                <dt className="col-sm-3">Phone</dt><dd className="col-sm-9">{store.phone || 'â€”'}</dd>
                <dt className="col-sm-3">Timezone</dt><dd className="col-sm-9">{store.timezone || 'UTC'}</dd>
              </dl>
            )}
          </div>

          <div className="panel">
            <h2>Change password</h2>
            <form onSubmit={handlePassword}>
              <Field label="Current password">
                <input type="password" className="form-control" required autoComplete="current-password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} />
              </Field>
              <Field label="New password" hint="At least 8 characters.">
                <input type="password" className="form-control" required minLength={8} autoComplete="new-password" value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} />
              </Field>
              <button type="submit" className="btn btn-outline-primary btn-sm">Change password</button>
            </form>
          </div>

          <div className="panel">
            <h2>Service status</h2>
            {health ? (
              <p className="mb-0 small">
                API <StatusBadge value={health.database === 'up' ? 'present' : 'absent'} /> database {health.database} ·
                email <StatusBadge value={health.email_enabled ? 'sent' : 'disabled'} />{' '}
                {health.email_enabled ? 'configured' : 'not configured â€” notifications stay in-app'}
              </p>
            ) : (
              <p className="mb-0 small text-muted">Status unavailable.</p>
            )}
          </div>
        </>
      )}
    </div>
  );
}
