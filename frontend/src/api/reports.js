import client, { envelopeData } from './client';

export async function getDashboard(today) {
  const res = await client.get('/reports/dashboard', { params: { today } });
  return envelopeData(res);
}

export async function getSummary(start_date, end_date) {
  const res = await client.get('/reports/summary', { params: { start_date, end_date } });
  return envelopeData(res);
}

export async function getWorkingHours(start_date, end_date) {
  const res = await client.get('/reports/working-hours', { params: { start_date, end_date } });
  return envelopeData(res);
}

export async function getWeeklyHours(week_start) {
  const res = await client.get('/reports/weekly-hours', { params: { week_start } });
  return envelopeData(res);
}

export async function getFairness(start_date, end_date) {
  const res = await client.get('/reports/fairness', { params: { start_date, end_date } });
  return envelopeData(res);
}

export async function getConflicts(start_date, end_date) {
  const res = await client.get('/reports/conflicts', { params: { start_date, end_date } });
  return envelopeData(res);
}

export async function getLeaveBreakdown(start_date, end_date) {
  const res = await client.get('/reports/leave', { params: { start_date, end_date } });
  return envelopeData(res);
}

/** Download a CSV export as a real file (auth header included). */
export async function downloadExport(kind, start_date, end_date) {
  const res = await client.get(`/reports/export/${kind}`, {
    params: { start_date, end_date },
    responseType: 'blob',
  });
  const disposition = res.headers['content-disposition'] || '';
  const match = disposition.match(/filename="([^"]+)"/);
  const filename = match ? match[1] : `${kind}-report.csv`;
  const url = window.URL.createObjectURL(new Blob([res.data], { type: 'text/csv' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}
