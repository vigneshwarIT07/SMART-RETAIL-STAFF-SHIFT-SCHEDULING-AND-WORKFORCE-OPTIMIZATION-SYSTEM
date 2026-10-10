import { Link } from 'react-router-dom';

export function Unauthorized() {
  return (
    <div className="page">
      <h1 className="page-title">Not authorized</h1>
      <p className="page-sub">Your account does not have access to that page.</p>
      <Link to="/" className="btn btn-outline-primary btn-sm mt-2">Back to home</Link>
    </div>
  );
}

export function NotFound() {
  return (
    <div className="page">
      <h1 className="page-title">Page not found</h1>
      <p className="page-sub">The address does not match any page in this app.</p>
      <Link to="/" className="btn btn-outline-primary btn-sm mt-2">Back to home</Link>
    </div>
  );
}

export function StoreInfo() {
  return (
    <div className="login-wrap">
      <div className="login-card">
        <h1 className="fs-5 fw-bold">Shift Scheduler</h1>
        <p className="small text-muted">
          Rota planning, attendance, leave and shift swaps for a single retail store.
          Accounts are provisioned by the store manager — there is no public sign-up.
        </p>
        <Link to="/login" className="btn btn-primary btn-sm">Back to sign in</Link>
      </div>
    </div>
  );
}
