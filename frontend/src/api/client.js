import axios from 'axios';

const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api';

const client = axios.create({ baseURL, timeout: 15000 });

function clearSession() {
  localStorage.removeItem('rss_token');
  localStorage.removeItem('rss_user');
}

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('rss_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

client.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status;
    const url = error?.config?.url || '';
    // Expired/invalid token: drop the session and send the user to login.
    // Never auto-retry unsafe requests (POST/PATCH/DELETE) — retrying could
    // duplicate assignments, attendance rows or swap requests.
    if (status === 401 && !url.includes('/auth/login')) {
      clearSession();
      if (window.location.pathname !== '/login') {
        window.location.href = '/login?expired=1';
      }
    }
    const message =
      error?.response?.data?.message ||
      error?.response?.data?.detail ||
      error.message ||
      'Request failed';
    const err = new Error(message);
    err.status = status;
    err.payload = error?.response?.data;
    throw err;
  },
);

/** Unwrap the unified {success, data, message} envelope. */
export function envelopeData(response) {
  return response?.data?.data;
}

export default client;
