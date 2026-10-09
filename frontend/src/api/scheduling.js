import client, { envelopeData } from './client';

export async function getCalendar(start_date, end_date) {
  const res = await client.get('/scheduling/calendar', { params: { start_date, end_date } });
  return envelopeData(res);
}

export async function getCoverage(start_date, end_date) {
  const res = await client.get('/scheduling/coverage', { params: { start_date, end_date } });
  return envelopeData(res);
}

export async function getSchedulingReport(start_date, end_date) {
  const res = await client.get('/scheduling/report', { params: { start_date, end_date } });
  return envelopeData(res);
}

export async function generateProposal(payload) {
  const res = await client.post('/scheduling/generate', payload);
  return envelopeData(res);
}

export async function applyProposal(payload) {
  const res = await client.post('/scheduling/apply', payload);
  return envelopeData(res);
}
