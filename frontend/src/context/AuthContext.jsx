import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import client, { envelopeData } from '../api/client';

const AuthContext = createContext(null);

function readStoredUser() {
  try {
    const raw = localStorage.getItem('rss_user');
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(readStoredUser);
  const [token, setToken] = useState(() => localStorage.getItem('rss_token'));
  const [loading, setLoading] = useState(true);

  // Revalidate the stored session against the server on first load.
  useEffect(() => {
    let cancelled = false;
    async function revalidate() {
      const stored = localStorage.getItem('rss_token');
      if (!stored) {
        setLoading(false);
        return;
      }
      try {
        const res = await client.get('/auth/me');
        if (!cancelled) {
          const fresh = envelopeData(res);
          setUser(fresh);
          localStorage.setItem('rss_user', JSON.stringify(fresh));
        }
      } catch {
        if (!cancelled) {
          setUser(null);
          setToken(null);
          localStorage.removeItem('rss_token');
          localStorage.removeItem('rss_user');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    revalidate();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email, password) => {
    const res = await client.post('/auth/login', { email, password });
    const data = envelopeData(res);
    localStorage.setItem('rss_token', data.access_token);
    localStorage.setItem('rss_user', JSON.stringify(data.user));
    setToken(data.access_token);
    setUser(data.user);
    return data.user;
  }, []);

  const logout = useCallback(async () => {
    try {
      await client.post('/auth/logout');
    } catch {
      // Stateless tokens: the client discards them either way.
    }
    localStorage.removeItem('rss_token');
    localStorage.removeItem('rss_user');
    setToken(null);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({
      user,
      token,
      loading,
      isAuthenticated: Boolean(token && user),
      isManager: user?.role === 'manager',
      employeeId: user?.employee?.id || user?.id || null,
      login,
      logout,
    }),
    [user, token, loading, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
