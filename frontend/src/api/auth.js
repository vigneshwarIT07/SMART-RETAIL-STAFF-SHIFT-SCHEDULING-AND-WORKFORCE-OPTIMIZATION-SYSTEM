import client, { envelopeData } from './client';

export async function login(email, password) {
  const res = await client.post('/auth/login', { email, password });
  return envelopeData(res);
}

export async function changePassword(current_password, new_password) {
  const res = await client.post('/auth/change-password', { current_password, new_password });
  return envelopeData(res);
}
