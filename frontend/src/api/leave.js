import client, { envelopeData } from './client';

export async function listLeave({ employee_id, status } = {}) {
  const res = await client.get('/leave', { params: { employee_id, status } });
  return envelopeData(res);
}

export async function fileLeave(payload, employee_id) {
  const res = await client.post('/leave', payload, { params: { employee_id } });
  return envelopeData(res);
}

export async function decideLeave(id, decision, review_note) {
  const res = await client.post(`/leave/${id}/decide`, { decision, review_note });
  return envelopeData(res);
}

export async function cancelLeave(id) {
  const res = await client.post(`/leave/${id}/cancel`);
  return envelopeData(res);
}
