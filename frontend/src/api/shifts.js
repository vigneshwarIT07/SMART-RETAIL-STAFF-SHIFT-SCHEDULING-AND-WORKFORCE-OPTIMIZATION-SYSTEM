import client, { envelopeData } from './client';

export async function listShifts({ start_date, end_date, status, role } = {}) {
  const res = await client.get('/shifts', { params: { start_date, end_date, status, role } });
  return envelopeData(res);
}

export async function createShift(payload) {
  const res = await client.post('/shifts', payload);
  return envelopeData(res);
}

export async function getShift(id) {
  const res = await client.get(`/shifts/${id}`);
  return envelopeData(res);
}

export async function updateShift(id, payload) {
  const res = await client.patch(`/shifts/${id}`, payload);
  return envelopeData(res);
}

export async function cancelShift(id, reason) {
  const res = await client.post(`/shifts/${id}/cancel`, null, { params: { reason } });
  return envelopeData(res);
}

export async function deleteShift(id) {
  const res = await client.delete(`/shifts/${id}`);
  return envelopeData(res);
}

export async function publishShifts(shift_ids) {
  const res = await client.post('/shifts/publish', shift_ids);
  return envelopeData(res);
}

export async function validateAssignment(payload) {
  const res = await client.post('/shifts/assignments/validate', payload);
  return envelopeData(res);
}

export async function assignEmployee(payload) {
  const res = await client.post('/shifts/assignments', payload);
  return envelopeData(res);
}

export async function unassignEmployee(assignmentId, reason) {
  const res = await client.delete(`/shifts/assignments/${assignmentId}`, { params: { reason } });
  return envelopeData(res);
}

export async function confirmAssignment(assignmentId) {
  const res = await client.post(`/shifts/assignments/${assignmentId}/confirm`);
  return envelopeData(res);
}

export async function eligibleEmployees(shiftId) {
  const res = await client.get(`/shifts/${shiftId}/eligible`);
  return envelopeData(res);
}
