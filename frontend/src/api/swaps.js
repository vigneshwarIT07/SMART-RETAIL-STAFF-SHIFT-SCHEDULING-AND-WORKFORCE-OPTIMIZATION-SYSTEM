import client, { envelopeData } from './client';

export async function listSwaps({ employee_id, status } = {}) {
  const res = await client.get('/swaps', { params: { employee_id, status } });
  return envelopeData(res);
}

export async function checkEligibility({ requester_shift_id, target_shift_id, target_employee_id }) {
  const res = await client.post('/swaps/check-eligibility', null, {
    params: { requester_shift_id, target_shift_id, target_employee_id },
  });
  return envelopeData(res);
}

export async function createSwap(payload) {
  const res = await client.post('/swaps', payload);
  return envelopeData(res);
}

export async function decideSwap(id, decision, review_note) {
  const res = await client.post(`/swaps/${id}/decide`, { decision, review_note });
  return envelopeData(res);
}

export async function cancelSwap(id) {
  const res = await client.post(`/swaps/${id}/cancel`);
  return envelopeData(res);
}
