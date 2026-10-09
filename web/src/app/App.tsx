// Root: theme, the auth gate and the logout confirmation. Every change of
// session (login, logout, expiry) resets the query cache first.
import { useEffect, useMemo, useState } from 'react';

import { apiRequest, SESSION_EXPIRED_EVENT } from '../lib/api';
import { resetSession } from '../lib/queryClient';
import { SessionContext } from '../data/workspace';
import type { Role, User } from '../data/types';
import { ConfirmDialog, LoadingState } from '../ui';
import { Dashboard } from './Dashboard';
import { LoginView } from './LoginView';
import { useTheme } from './theme';

type AuthState =
  | { status: 'loading' }
  | { status: 'signed-out' }
  | { status: 'signed-in'; user: User };

interface AuthResponse {
  authenticated?: boolean;
  user?: User | null;
}

export function App() {
  const [theme, toggleTheme] = useTheme();
  const [auth, setAuth] = useState<AuthState>({ status: 'loading' });
  const [loginNotice, setLoginNotice] = useState('');
  const [logoutOpen, setLogoutOpen] = useState(false);
  const [logoutBusy, setLogoutBusy] = useState(false);
  const [logoutError, setLogoutError] = useState('');

  function endSession(notice = '') {
    resetSession();
    setLogoutOpen(false);
    setLoginNotice(notice);
    setAuth({ status: 'signed-out' });
  }

  useEffect(() => {
    const onExpired = () => endSession('Oturumun sona erdi. Devam etmek için tekrar giriş yap.');
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  }, []);

  useEffect(() => {
    apiRequest<AuthResponse>('/api/auth')
      .then(data => setAuth(data.authenticated ? { status: 'signed-in', user: data.user || { email: '' } } : { status: 'signed-out' }))
      .catch(() => setAuth({ status: 'signed-out' }));
  }, []);

  function login(email: string, password: string, role: Role): Promise<void> {
    return apiRequest<AuthResponse>('/api/auth', { method: 'POST', body: { email, password, role } }).then(data => {
      resetSession();
      setLoginNotice('');
      setAuth({ status: 'signed-in', user: data.user || { email } });
    });
  }

  function logout() {
    setLogoutBusy(true);
    setLogoutError('');
    apiRequest('/api/auth', { method: 'DELETE' })
      .then(() => endSession())
      .catch(() => setLogoutError('Çıkış yapılamadı. Bağlantını kontrol edip tekrar dene.'))
      .finally(() => setLogoutBusy(false));
  }

  const user = auth.status === 'signed-in' ? auth.user : null;
  const session = useMemo(() => (user ? { user, requestLogout: () => setLogoutOpen(true) } : null), [user]);

  if (auth.status === 'loading') return <LoadingState />;
  if (!session) return <LoginView onSubmit={login} notice={loginNotice} />;

  return (
    <SessionContext.Provider value={session}>
      <Dashboard key={session.user.email} theme={theme} onToggleTheme={toggleTheme} />
      {logoutOpen && (
        <ConfirmDialog
          title="Oturumu kapat"
          text={logoutError || 'Bu cihazdaki Zeplin oturumun kapatılacak.'}
          confirmLabel="Çıkış yap"
          busyLabel="Çıkış yapılıyor…"
          busy={logoutBusy}
          onCancel={() => { setLogoutOpen(false); setLogoutError(''); }}
          onConfirm={logout}
        />
      )}
    </SessionContext.Provider>
  );
}
