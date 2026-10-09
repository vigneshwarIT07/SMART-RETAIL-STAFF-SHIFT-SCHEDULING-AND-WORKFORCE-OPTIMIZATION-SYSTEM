export function isoDate(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

export function mondayOf(d) {
  const copy = new Date(d);
  const dow = (copy.getDay() + 6) % 7; // Monday = 0
  copy.setDate(copy.getDate() - dow);
  copy.setHours(0, 0, 0, 0);
  return copy;
}

export function addDays(d, n) {
  const copy = new Date(d);
  copy.setDate(copy.getDate() + n);
  return copy;
}

export function parseISODate(s) {
  const [y, m, day] = s.split('-').map(Number);
  return new Date(y, m - 1, day);
}

const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

export function weekdayName(index) {
  return WEEKDAYS[index] ?? `Day ${index}`;
}

export function shortTime(t) {
  if (!t) return '—';
  return String(t).slice(0, 5);
}

export function fmtDateTime(dt) {
  if (!dt) return '—';
  const d = new Date(dt);
  if (Number.isNaN(d.getTime())) return String(dt);
  return d.toLocaleString();
}

export function fmtDate(d) {
  if (!d) return '—';
  const dt = d instanceof Date ? d : new Date(`${d}T00:00:00`);
  return dt.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
}

export function hoursText(minutes) {
  if (minutes == null) return '—';
  return `${(minutes / 60).toFixed(1)} h`;
}
