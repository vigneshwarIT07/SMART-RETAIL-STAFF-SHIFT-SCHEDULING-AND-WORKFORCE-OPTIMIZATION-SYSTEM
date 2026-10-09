import client, { envelopeData } from './client';

export async function listAvailability(employeeId) {
  const res = await client.get(`/availability/employees/${employeeId}`);
  return envelopeData(res);
}

export async function createAvailability(employeeId, payload) {
  const res = await client.post(`/availability/employees/${employeeId}`, payload);
  return envelopeData(res);
}

export async function updateAvailability(rowId, payload) {
  const res = await client.patch(`/availability/${rowId}`, payload);
  return envelopeData(res);
}

export async function deleteAvailability(rowId) {
  const res = await client.delete(`/availability/${rowId}`);
  return envelopeData(res);
}

export async function reviewAvailability() {
  const res = await client.get('/availability/review');
  return envelopeData(res);
}
