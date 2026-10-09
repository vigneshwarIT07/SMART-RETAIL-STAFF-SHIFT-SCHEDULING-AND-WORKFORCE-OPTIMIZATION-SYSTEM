import client, { envelopeData } from './client';

export async function getOwnStore() {
  const res = await client.get('/stores/me');
  return envelopeData(res);
}

export async function updateOwnStore(payload) {
  const res = await client.patch('/stores/me', payload);
  return envelopeData(res);
}

export async function getHealth() {
  const res = await client.get('/health');
  return envelopeData(res);
}
