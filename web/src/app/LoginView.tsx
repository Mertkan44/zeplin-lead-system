import { useState, type FormEvent } from 'react';

import type { Role } from '../data/types';
import { Button, Field, Input } from '../ui';
import styles from './LoginView.module.css';

export interface LoginViewProps {
  onSubmit: (email: string, password: string, role: Role) => Promise<void>;
  /** Why the user is here, e.g. the session expired. */
  notice?: string;
}

export function LoginView({ onSubmit, notice }: LoginViewProps) {
  const [role, setRole] = useState<Role>('admin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(false);
    onSubmit(email, password, role).catch(() => setError(true)).finally(() => setBusy(false));
  }

  return (
    <div className={styles.root}>
      <div className={styles.brandPane}>
        <div className={styles.glow} />
        <div className={styles.brand}>
          <div className={styles.brandLogo}><img src="/logo-mark.png" alt="Zeplin Media" /></div>
          <div>
            <div className={styles.brandName}>Zeplin Media</div>
            <div className={styles.brandSub}>Lead Intelligence</div>
          </div>
        </div>
        <div className={styles.pitch}>
          <div className={styles.pitchTitle}>Bugün kimi arayacağını bilerek başla.</div>
          <div className={styles.pitchText}>Yapay zekâ her lead için sıradaki en iyi aksiyonu, gerekçesini ve hazır mesajını hazırlar. Sen sadece ara.</div>
        </div>
      </div>

      <div className={styles.formPane}>
        <form className={styles.form} onSubmit={submit}>
          <h1 className={styles.title}>Panele giriş</h1>
          <div className={styles.subtitle}>Rolünü seç ve devam et</div>

          <div className={styles.roles} role="group" aria-label="Rol">
            <button type="button" className={styles.role} aria-pressed={role === 'admin'} onClick={() => setRole('admin')}>Yönetici</button>
            <button type="button" className={styles.role} aria-pressed={role === 'sales'} onClick={() => setRole('sales')}>Çalışan</button>
          </div>

          <div className={styles.fields}>
            <Field label="E-posta">
              {control => <Input {...control} size="lg" type="email" autoComplete="username" value={email} onChange={e => setEmail(e.target.value)} placeholder="ad@zeplinmedia.com" />}
            </Field>
            <Field label="Şifre">
              {control => <Input {...control} size="lg" type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} placeholder="••••••••" />}
            </Field>
          </div>

          {notice && !error && <div className={styles.notice} role="status">{notice}</div>}
          {error && <div className={styles.error} role="alert">E-posta veya şifre hatalı. Tekrar dene.</div>}

          <Button type="submit" variant="primary" block busy={busy} busyLabel="Giriş yapılıyor…" className={styles.submit}>Giriş yap</Button>
          <div className={styles.hint}>Yönetici ve çalışan girişleri Supabase ekip hesaplarıyla yapılır.</div>
        </form>
      </div>
    </div>
  );
}
