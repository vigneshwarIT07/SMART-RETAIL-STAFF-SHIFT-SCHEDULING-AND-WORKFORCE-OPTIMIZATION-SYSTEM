import { useEffect, useState } from 'react';
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useToast } from './Toast';
import client, { envelopeData } from '../api/client';

const MANAGER_LINKS = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/schedule', label: 'Schedule' },
  { to: '/employees', label: 'Employees' },
  { to: '/attendance', label: 'Attendance' },
  { to: '/leave', label: 'Leave requests' },
  { to: '/swaps', label: 'Swap requests' },
  { to: '/availability', label: 'Availability' },
  { to: '/reports', label: 'Reports' },
  { to: '/notifications', label: 'Notifications' },
  { to: '/store', label: 'Store settings' },
];

const EMPLOYEE_LINKS = [
  { to: '/schedule', label: 'My schedule' },
  { to: '/attendance', label: 'Attendance' },
  { to: '/leave', label: 'Leave' },
  { to: '/swaps', label: 'Swaps' },
  { to: '/availability', label: 'Availability' },
  { to: '/notifications', label: 'Notifications' },
  { to: '/store', label: 'Store' },
];

export default function Layout() {
  const { user, isManager, logout } = useAuth();
  const { push } = useToast();
  const navigate = useNavigate();
  const location = useLocation();
  const [storeName, setStoreName] = useState('');
  const [unread, setUnread] = useState(0);
  const [navOpen, setNavOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [storeRes, unreadRes] = await Promise.all([
          client.get('/stores/me'),
          client.get('/notifications/unread-count'),
        ]);
        if (!cancelled) {
          setStoreName(envelopeData(storeRes)?.name || '');
          setUnread(envelopeData(unreadRes)?.unread ?? 0);
        }
      } catch {
        // Non-fatal: layout still renders without store name / badge.
      }
    }
    load();
    const timer = setInterval(load, 60000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [location.pathname]);

  async function handleLogout() {
    await logout();
    navigate('/login');
  }

  const links = isManager ? MANAGER_LINKS : EMPLOYEE_LINKS;

  return (
    <div className="app-shell">
      <aside className={`sidebar${navOpen ? ' open' : ''}`} aria-label="Primary">
        <div className="sidebar-brand">
          Shift Scheduler
          <small>{storeName || 'Retail store'}</small>
        </div>
        <nav>
          {links.map((link) => (
            <Link
              key={link.to}
              to={link.to}
              end={link.end}
              className="nav-link"
              onClick={() => setNavOpen(false)}
            >
              {link.label}
              {link.to === '/notifications' && unread > 0 && (
                <span className="badge text-bg-primary ms-2">{unread} new</span>
              )}
            </Link>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div>{user?.full_name}</div>
          <div className="text-capitalize">{user?.role}</div>
        </div>
      </aside>
      <div className="content">
        <div className="topbar">
          <button
            type="button"
            className="btn btn-outline-secondary btn-sm d-lg-none"
            onClick={() => setNavOpen((v) => !v)}
            aria-label="Toggle navigation"
          >
            Menu
          </button>
          <span className="fw-semibold">{storeName}</span>
          <span className="ms-auto" />
          <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => navigate('/notifications')}>
            Notifications{unread > 0 ? ` (${unread} unread)` : ''}
          </button>
          <button
            type="button"
            className="btn btn-outline-secondary btn-sm"
            onClick={() => {
              handleLogout().then(() => push('Signed out', 'info'));
            }}
          >
            Sign out
          </button>
        </div>
        <Outlet />
      </div>
    </div>
  );
}
