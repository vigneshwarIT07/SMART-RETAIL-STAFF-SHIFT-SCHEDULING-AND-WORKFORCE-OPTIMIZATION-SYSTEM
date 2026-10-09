import { useState } from 'react';

const STATUS_STYLES = {
  // Coverage
  fully_staffed: 'success',
  understaffed: 'warning',
  unassigned: 'secondary',
  cancelled: 'danger',
  // Shifts
  draft: 'secondary',
  published: 'primary',
  completed: 'success',
  // Assignments / attendance
  assigned: 'primary',
  confirmed: 'info',
  present: 'success',
  late: 'warning',
  absent: 'danger',
  incomplete: 'secondary',
  excused: 'info',
  no_show: 'danger',
  // Requests
  pending: 'warning',
  approved: 'success',
  rejected: 'danger',
  // Users
  active: 'success',
  inactive: 'secondary',
  on_leave: 'info',
  manager: 'primary',
  employee: 'secondary',
  // Availability
  available: 'success',
  unavailable: 'secondary',
  // Misc
  overtime: 'warning',
  sent: 'success',
  failed: 'danger',
  disabled: 'secondary',
};

export function StatusBadge({ value }) {
  const key = String(value ?? '').toLowerCase();
  const style = STATUS_STYLES[key] || 'secondary';
  const label = String(value ?? '').replace(/_/g, ' ');
  return <span className={`badge text-bg-${style}`}>{label || 'â€”'}</span>;
}

export function Loading({ text = 'Loadingâ€¦' }) {
  return <p className="text-muted">{text}</p>;
}

export function EmptyState({ text }) {
  return <p className="text-muted mb-0">{text}</p>;
}

export function ErrorAlert({ error, onRetry }) {
  if (!error) return null;
  return (
    <div className="alert alert-danger d-flex justify-content-between align-items-center" role="alert">
      <span>{error}</span>
      {onRetry && (
        <button type="button" className="btn btn-sm btn-outline-danger" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

export function Pagination({ page, pages, total, onPage }) {
  if (!pages || pages <= 1) {
    return total ? <p className="text-muted small mb-0">{total} result(s)</p> : null;
  }
  return (
    <div className="d-flex align-items-center gap-2 mt-3">
      <button type="button" className="btn btn-sm btn-outline-secondary" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        Previous
      </button>
      <span className="small text-muted">
        Page {page} of {pages} ({total} total)
      </span>
      <button
        type="button"
        className="btn btn-sm btn-outline-secondary"
        disabled={page >= pages}
        onClick={() => onPage(page + 1)}
      >
        Next
      </button>
    </div>
  );
}

export function ConfirmDialog({ title, body, confirmLabel = 'Confirm', onConfirm, onCancel, busy }) {
  return (
    <div className="modal d-block" tabIndex="-1" role="dialog" aria-modal="true" aria-label={title}>
      <div className="modal-dialog" role="document">
        <div className="modal-content">
          <div className="modal-header">
            <h2 className="modal-title fs-6">{title}</h2>
            <button type="button" className="btn-close" aria-label="Close" onClick={onCancel} />
          </div>
          <div className="modal-body">
            <p className="mb-0">{body}</p>
          </div>
          <div className="modal-footer">
            <button type="button" className="btn btn-outline-secondary" onClick={onCancel} disabled={busy}>
              Cancel
            </button>
            <button type="button" className="btn btn-primary" onClick={onConfirm} disabled={busy}>
              {busy ? 'Workingâ€¦' : confirmLabel}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export function Modal({ title, children, onClose, wide }) {
  return (
    <div className="modal d-block" tabIndex="-1" role="dialog" aria-modal="true" aria-label={title}>
      <div className={`modal-dialog${wide ? ' modal-lg' : ''}`} role="document">
        <div className="modal-content">
          <div className="modal-header">
            <h2 className="modal-title fs-6">{title}</h2>
            <button type="button" className="btn-close" aria-label="Close" onClick={onClose} />
          </div>
          <div className="modal-body">{children}</div>
        </div>
      </div>
    </div>
  );
}

export function Field({ label, children, hint }) {
  const id = useState(() => `f-${Math.random().toString(36).slice(2)}`)[0];
  return (
    <div className="mb-3">
      <label className="form-label" htmlFor={id}>
        {label}
      </label>
      <div id={id}>{children}</div>
      {hint && <div className="form-text">{hint}</div>}
    </div>
  );
}
