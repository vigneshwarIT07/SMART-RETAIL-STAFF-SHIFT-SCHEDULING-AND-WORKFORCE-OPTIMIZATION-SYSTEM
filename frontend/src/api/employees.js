import client, { envelopeData } from './client';

export async function listEmployees({ search, status, page = 1, page_size = 20 } = {}) {
  const res = await client.get('/employees', { params: { search, status, page, page_size } });
  return envelopeData(res);
}

export async function createEmployee(payload) {
  const res = await client.post('/employees', payload);
  return envelopeData(res);
}

export async function getEmployee(id) {
  const res = await client.get(`/employees/${id}`);
  return envelopeData(res);
}

export async function getOwnProfile() {
  const res = await client.get('/employees/me');
  return envelopeData(res);
}

export async function updateEmployee(id, payload) {
  const res = await client.patch(`/employees/${id}`, payload);
  return envelopeData(res);
}

export async function deactivateEmployee(id) {
  const res = await client.post(`/employees/${id}/deactivate`);
  return envelopeData(res);
}
