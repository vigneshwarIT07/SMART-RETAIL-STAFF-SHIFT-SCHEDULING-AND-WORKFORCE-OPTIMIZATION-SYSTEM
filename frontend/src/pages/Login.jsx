import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../components/Toast';

export default function Login() {
  const { login } = useAuth();
  const { push } = useToast();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      const user = await login(email.trim(), password);
      push(`Welcome back, ${user.full_name}`, 'success');
      navigate(user.role === 'manager' ? '/' : '/schedule', { replace: true });
    } catch (err) {
      setError(err.message || 'Sign in failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <div className="login-card">
        <h1 className="fs-5 fw-bold mb-1">Shift Scheduler</h1>
        <p className="text-muted small mb-3">Sign in with your store account.</p>
        {params.get('expired') && (
          <div className="alert alert-warning" role="alert">
            Your session expired. Please sign in again.
          </div>
        )}
        {error && (
          <div className="alert alert-danger" role="alert">
            {error}
          </div>
        )}
        <form onSubmit={handleSubmit}>
          <div className="mb-3">
            <label className="form-label" htmlFor="login-email">
              Work email
            </label>
            <input
              id="login-email"
              className="form-control"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="mb-3">
            <label className="form-label" htmlFor="login-password">
              Password
            </label>
            <input
              id="login-password"
              className="form-control"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <button type="submit" className="btn btn-primary w-100" disabled={busy}>
            {busy ? 'Signing inâ€¦' : 'Sign in'}
          </button>
        </form>
        <p className="text-muted small mt-3 mb-0">
          No account? Accounts are created by your store manager â€” please contact them.
          <br />
          <Link to="/store-info">About this store app</Link>
        </p>
      </div>
    </div>
  );
}
