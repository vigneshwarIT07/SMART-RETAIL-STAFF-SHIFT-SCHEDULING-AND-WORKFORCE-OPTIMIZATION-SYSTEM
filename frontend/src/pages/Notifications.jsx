import { useEffect, useState } from 'react';
import { listNotifications, markAllRead, markRead } from '../api/notifications';
import { useToast } from '../components/Toast';
import { EmptyState, ErrorAlert, Loading } from '../components/ui';
import { fmtDateTime } from '../utils/format';

export default function Notifications() {
  const { push } = useToast();
  const [rows, setRows] = useState([]);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  async function load() {
    setLoading(true);
    setError('');
    try {
      setRows((await listNotifications({ unread_only: unreadOnly })) || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [unreadOnly]);

  async function handleRead(id) {
    try {
      await markRead(id);
      setRows((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)));
    } catch (err) {
      push(err.message, 'danger');
    }
  }

  async function handleReadAll() {
    try {
      await markAllRead();
      setRows((prev) => prev.map((n) => ({ ...n, is_read: true })));
      push('All notifications marked read', 'info');
    } catch (err) {
      push(err.message, 'danger');
    }
  }

  return (
    <div className="page">
      <div className="d-flex align-items-center gap-2">
        <div>
          <h1 className="page-title">Notifications</h1>
          <p className="page-sub">Assignments, approvals and schedule updates.</p>
        </div>
        <span className="ms-auto" />
        <div className="form-check">
          <input id="notif-unread" type="checkbox" className="form-check-input" checked={unreadOnly} onChange={(e) => setUnreadOnly(e.target.checked)} />
          <label className="form-check-label small" htmlFor="notif-unread">Unread only</label>
        </div>
        <button type="button" className="btn btn-sm btn-outline-secondary" onClick={handleReadAll}>Mark all read</button>
      </div>

      <ErrorAlert error={error} onRetry={load} />
      {loading ? <Loading /> : rows.length === 0 ? (
        <div className="panel"><EmptyState text="No notifications." /></div>
      ) : (
        <div className="panel">
          <ul className="list-group">
            {rows.map((n) => (
              <li key={n.id} className={`list-group-item${n.is_read ? '' : ' list-group-item-primary'}`}>
                <div className="d-flex gap-2 align-items-start">
                  <div>
                    <strong>{n.title}</strong>
                    {!n.is_read && <span className="badge text-bg-primary ms-2">New</span>}
                    {n.body && <p className="mb-1 small">{n.body}</p>}
                    <small className="text-muted">{fmtDateTime(n.created_at)} Â· {String(n.notification_type || '').replace(/_/g, ' ')}</small>
                  </div>
                  <span className="ms-auto" />
                  {!n.is_read && (
                    <button type="button" className="btn btn-sm btn-outline-secondary" onClick={() => handleRead(n.id)}>
                      Mark read
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
