import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getDashboard } from '../api/reports';
import { ErrorAlert, Loading } from '../components/ui';

const METRICS = [
  { key: 'today_shifts', label: "Today's shifts" },
  { key: 'today_unassigned', label: 'Unassigned today' },
  { key: 'week_understaffed', label: 'Understaffed this week' },
  { key: 'active_employees', label: 'Active employees' },
  { key: 'pending_leave', label: 'Pending leave requests' },
  { key: 'pending_swaps', label: 'Pending swap requests' },
  { key: 'missing_clockouts', label: 'Missing clock-outs' },
  { key: 'week_overtime_flags', label: 'Overtime warnings' },
];

const METRIC_LINKS = {
  today_shifts: '/schedule',
  today_unassigned: '/schedule',
  week_understaffed: '/schedule',
  active_employees: '/employees',
  pending_leave: '/leave',
  pending_swaps: '/swaps',
  missing_clockouts: '/attendance',
  week_overtime_flags: '/reports',
};

export default function Dashboard() {
  const [metrics, setMetrics] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    setError('');
    try {
      setMetrics(await getDashboard());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="page">
      <h1 className="page-title">Dashboard</h1>
      <p className="page-sub">Live figures from the store database â€” nothing here is sample data.</p>
      <div className="mt-3">
        <ErrorAlert error={error} onRetry={load} />
        {loading && <Loading />}
        {metrics && (
          <>
            <div className="metric-grid mb-3">
              {METRICS.map((m) => (
                <div className="metric" key={m.key}>
                  <div className="label">{m.label}</div>
                  <div className="value">{metrics[m.key] ?? 0}</div>
                  <Link to={METRIC_LINKS[m.key]} className="small">
                    View
                  </Link>
                </div>
              ))}
            </div>
            <div className="panel">
              <h2>Week in view</h2>
              <p className="mb-0 small text-muted">
                Rota week {metrics.week_start} to {metrics.week_end}. Publish draft shifts from the
                Schedule page once staffing looks right.
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
