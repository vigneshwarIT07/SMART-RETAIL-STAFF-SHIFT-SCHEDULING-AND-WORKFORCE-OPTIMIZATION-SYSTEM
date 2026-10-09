import client, { envelopeData } from './client';

export async function listNotifications({ unread_only = false, limit = 50 } = {}) {
  const res = await client.get('/notifications', { params: { unread_only, limit } });
  return envelopeData(res);
}

export async function markRead(id) {
  const res = await client.post(`/notifications/${id}/read`);
  return envelopeData(res);
}

export async function markAllRead() {
  const res = await client.post('/notifications/read-all');
  return envelopeData(res);
}
