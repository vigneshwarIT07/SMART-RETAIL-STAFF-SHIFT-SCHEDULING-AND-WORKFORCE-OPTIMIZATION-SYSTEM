import client, { envelopeData } from './client';

export async function listAttendance({ start, end, employee_id, status } = {}) {
  const res = await client.get('/attendance', { params: { start, end, employee_id, status } });
  return envelopeData(res);
}

export async function clockIn(shift_id, employee_id, at) {
  const res = await client.post('/attendance/clock-in', null, { params: { shift_id, employee_id, at } });
  return envelopeData(res);
}

export async function clockOut(shift_id, employee_id, at) {
  const res = await client.post('/attendance/clock-out', null, { params: { shift_id, employee_id, at } });
  return envelopeData(res);
}

export async function markAbsent(shift_id, employee_id, notes) {
  const res = await client.post('/attendance/mark-absent', null, { params: { shift_id, employee_id, notes } });
  return envelopeData(res);
}

export async function missingClockouts() {
  const res = await client.get('/attendance/missing-clockouts');
  return envelopeData(res);
}

export async function attendanceSummary(start, end) {
  const res = await client.get('/attendance/summary', { params: { start, end } });
  return envelopeData(res);
}

export async function correctAttendance(recordId, payload) {
  const res = await client.post(`/attendance/${recordId}/correct`, payload);
  return envelopeData(res);
}
