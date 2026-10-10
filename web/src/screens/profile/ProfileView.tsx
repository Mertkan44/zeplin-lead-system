import { useState, type FormEvent } from "react";
import type { User } from "../../data/types";
import { roleLabel } from "../../domain/catalog";
import { apiRequest, ApiError, SESSION_EXPIRED_EVENT } from "../../lib/api";
import type { Density } from "../../app/density";
import type { Theme } from "../../app/theme";
import { Button, Field, Input, Link, Select } from "../../ui";
import { PageHeader } from "../shared/PageHeader";
import styles from "./ProfileView.module.css";

export function ProfileView({
  user,
  theme,
  onToggleTheme,
  onLogout,
  density,
  onDensityChange,
}: {
  user: User;
  theme: Theme;
  onToggleTheme: () => void;
  onLogout: () => void;
  density: Density;
  onDensityChange: (value: Density) => void;
}) {
  const [old, setOld] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setError("");
    if (password !== confirm) {
      setError("Yeni şifreler eşleşmiyor.");
      return;
    }
    if (!user.updated_at) {
      setError("Hesap bilgilerini yenilemek için tekrar giriş yap.");
      return;
    }
    setBusy(true);
    try {
      await apiRequest("/api/users?view=account", {
        method: "PATCH",
        body: {
          current_password: old,
          new_password: password,
          expected_updated_at: user.updated_at,
        },
      });
      setOld("");
      setPassword("");
      setConfirm("");
      window.dispatchEvent(
        new CustomEvent(SESSION_EXPIRED_EVENT, {
          detail: {
            notice: "Şifren değiştirildi. Yeni şifrenle tekrar giriş yap.",
          },
        }),
      );
    } catch (err) {
      setError(
        err instanceof ApiError && err.code === "USER_VERSION_CONFLICT"
          ? "Hesabın bu sırada değişti. Tekrar giriş yapıp şifre değişimini yeniden dene."
          : err instanceof Error
            ? err.message
            : "Şifre değiştirilemedi.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className={styles.root}>
      <PageHeader
        eyebrow="HESAP"
        title="Hesabım ve ayarlar"
        subtitle="Kişisel hesap, görünüm ve oturum."
        actions={<Button onClick={onLogout}>Çıkış yap</Button>}
      />
      <div className={styles.grid}>
        <section className={styles.panel} aria-labelledby="account-info">
          <h2 id="account-info">Hesap bilgileri</h2>
          <dl>
            <div>
              <dt>Ad</dt>
              <dd>{user.name || "Belirtilmedi"}</dd>
            </div>
            <div>
              <dt>E-posta</dt>
              <dd>{user.email}</dd>
            </div>
            <div>
              <dt>Rol</dt>
              <dd>{roleLabel(user.role)}</dd>
            </div>
            <div>
              <dt>Unvan</dt>
              <dd>{user.title || "Belirtilmedi"}</dd>
            </div>
          </dl>
          <p>Hesap bilgilerini ve yetkilerini yönetici düzenler.</p>
          {user.role === "admin" && <Link to="/team">Ekip yönetimini aç</Link>}
        </section>
        <section className={styles.panel} aria-labelledby="appearance">
          <h2 id="appearance">Görünüm</h2>
          <p>
            Bu cihazdaki tema: {theme === "dark" ? "Koyu" : "Açık"}. Tercihin bu
            tarayıcıda hatırlanır.
          </p>
          <Button onClick={onToggleTheme}>
            {theme === "dark" ? "Açık temaya geç" : "Koyu temaya geç"}
          </Button>
          <Field label="Lead listesindeki satır aralığı">
            {(control) => (
              <Select
                {...control}
                value={density}
                onChange={(e) => onDensityChange(e.target.value as Density)}
              >
                <option value="comfortable">Rahat</option>
                <option value="compact">Sıkı</option>
              </Select>
            )}
          </Field>
          <p>
            Hatırlatmalar Bugün ve Takip listelerinde gösterilir. E-posta veya
            tarayıcı bildirimi gönderilmez.
          </p>
        </section>
        <section className={styles.panel} aria-labelledby="account-password">
          <h2 id="account-password">Şifre ve oturum</h2>
          <p>
            Şifreyi değiştirmek mevcut cihazlardaki oturumlarını sonlandırır.
            Ardından yeniden giriş yaparsın.
          </p>
          <form onSubmit={submit} className={styles.form}>
            <fieldset disabled={busy} className={styles.fields}>
              <Field label="Mevcut şifre">
                {(control) => (
                  <Input
                    {...control}
                    type="password"
                    required
                    maxLength={128}
                    autoComplete="current-password"
                    value={old}
                    onChange={(e) => setOld(e.target.value)}
                  />
                )}
              </Field>
              <Field label="Yeni şifre" hint="12–128 karakter.">
                {(control) => (
                  <Input
                    {...control}
                    type="password"
                    required
                    minLength={12}
                    maxLength={128}
                    autoComplete="new-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                )}
              </Field>
              <Field label="Yeni şifre tekrar">
                {(control) => (
                  <Input
                    {...control}
                    type="password"
                    required
                    autoComplete="new-password"
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                  />
                )}
              </Field>
            </fieldset>
            {error && <p role="alert">{error}</p>}
            <Button
              type="submit"
              variant="primary"
              busy={busy}
              busyLabel="Şifre değiştiriliyor…"
            >
              Şifreyi değiştir
            </Button>
          </form>
        </section>
      </div>
    </div>
  );
}
