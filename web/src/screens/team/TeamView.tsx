import { useRef, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import type { User } from "../../data/types";
import { apiRequest, ApiError, SESSION_EXPIRED_EVENT } from "../../lib/api";
import { newRequestId } from "../../lib/browser";
import { queryClient } from "../../lib/queryClient";
import { roleLabel } from "../../domain/catalog";
import {
  Button,
  Dialog,
  ConfirmDialog,
  EmptyState,
  ErrorState,
  Field,
  Input,
  Link,
  Select,
} from "../../ui";
import { PageHeader } from "../shared/PageHeader";
import styles from "./TeamView.module.css";

interface Member extends User {
  updated_at: string;
  active_assignments: number;
  overdue_assignments: number;
}
const MESSAGES: Record<string, string> = {
  LAST_ADMIN_REQUIRED:
    "En az bir aktif yönetici kalmalı. Önce başka bir yöneticiyi etkinleştir.",
  USER_VERSION_CONFLICT:
    "Hesap sen formu doldururken değişti. Formunu koruduk; güncel bilgileri alıp tekrar kaydet.",
  USER_ALREADY_EXISTS: "Bu e-posta zaten kayıtlı. Mevcut kişiyi düzenle.",
  TEAM_ADMIN_REQUIRED: "Ekip yönetimi için aktif yönetici hesabı gerekli.",
  IDEMPOTENCY_KEY_REUSED:
    "İşlem kimliği başka bir işlemde kullanıldı. Formu tekrar aç.",
};
function endSession() {
  window.dispatchEvent(
    new CustomEvent(SESSION_EXPIRED_EVENT, {
      detail: {
        notice: "Hesabın güncellendi. Yeni bilgilerle tekrar giriş yap.",
      },
    }),
  );
}

function MemberDialog({
  member,
  onClose,
  onSaved,
  onRefresh,
}: {
  member: Member | null;
  onClose: () => void;
  onSaved: () => void;
  onRefresh: (email: string) => Promise<Member | undefined>;
}) {
  const [snapshot, setSnapshot] = useState(member);
  const [email, setEmail] = useState(member?.email || "");
  const [name, setName] = useState(member?.name || "");
  const [role, setRole] = useState(member?.role || "sales");
  const [active, setActive] = useState(member?.active !== false);
  const [title, setTitle] = useState(member?.title || "");
  const [avatar, setAvatar] = useState(member?.avatar_url || "");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState(false);
  const [discard, setDiscard] = useState(false);
  const request = useRef<{ body: string; key: string } | null>(null);
  const dirty = Boolean(
    email !== (member?.email || "") ||
      name !== (member?.name || "") ||
      role !== (member?.role || "sales") ||
      active !== (member?.active !== false) ||
      title !== (member?.title || "") ||
      avatar !== (member?.avatar_url || "") ||
      password,
  );
  function close() {
    if (!busy) {
      if (dirty) setDiscard(true);
      else onClose();
    }
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    if (!name.trim() || !email.trim()) {
      setError("Ad ve e-posta gerekli.");
      return;
    }
    if ((!member || password) && password.length < 12) {
      setError("Şifre en az 12 karakter olmalı.");
      return;
    }
    const values = {
      email,
      name,
      role,
      active,
      title,
      avatar_url: avatar,
      password: password || null,
      expected_updated_at: snapshot?.updated_at,
    };
    const body = JSON.stringify(values);
    if (request.current?.body !== body)
      request.current = { body, key: newRequestId() };
    setBusy(true);
    setError("");
    setConflict(false);
    try {
      const result = await apiRequest<{ account_changed?: boolean }>(
        "/api/users?view=team",
        {
          method: member ? "PATCH" : "POST",
          body: { ...values, idempotency_key: request.current!.key },
        },
      );
      setPassword("");
      if (result.account_changed) {
        endSession();
        return;
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["team-management"] }),
        queryClient.invalidateQueries({ queryKey: ["users"] }),
        queryClient.invalidateQueries({ queryKey: ["workspace"] }),
      ]);
      onSaved();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? MESSAGES[err.code || ""] || err.message
          : "Kayıt yapılamadı. Formun korunuyor.",
      );
      setConflict(
        err instanceof ApiError && err.code === "USER_VERSION_CONFLICT",
      );
    } finally {
      setBusy(false);
    }
  }
  async function refresh() {
    if (busy) return;
    setBusy(true);
    try {
      const next = await onRefresh(email);
      if (!next) {
        setError("Hesap artık görünmüyor.");
        return;
      }
      setSnapshot(next);
      request.current = null;
      setConflict(false);
      setError("Güncel hesap alındı. Seçimlerini kontrol edip tekrar kaydet.");
    } catch {
      setError("Güncel bilgiler alınamadı. Formun korunuyor.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog
      title={member ? "Ekip üyesini düzenle" : "Ekip üyesi ekle"}
      onClose={close}
      dismissible={!busy}
      placement="right"
    >
      <form className={styles.form} onSubmit={submit}>
        <fieldset disabled={busy} className={styles.fields}>
          <Field label="Ad soyad">
            {(control) => (
              <Input
                {...control}
                value={name}
                maxLength={120}
                required
                onChange={(e) => setName(e.target.value)}
              />
            )}
          </Field>
          <Field label="E-posta">
            {(control) => (
              <Input
                {...control}
                value={email}
                type="email"
                required
                disabled={Boolean(member)}
                onChange={(e) => setEmail(e.target.value)}
              />
            )}
          </Field>
          <Field
            label="Rol"
            hint="Yönetici tüm CRM ve ekip yönetimine erişir. Satış kullanıcısı kendi atamalarını görür."
          >
            {(control) => (
              <Select
                {...control}
                value={role}
                onChange={(e) => setRole(e.target.value)}
              >
                <option value="sales">Satış</option>
                <option value="admin">Yönetici</option>
              </Select>
            )}
          </Field>
          <label className={styles.check}>
            <input
              type="checkbox"
              checked={active}
              onChange={(e) => setActive(e.target.checked)}
            />{" "}
            Aktif hesap
          </label>
          <Field label="Unvan (isteğe bağlı)">
            {(control) => (
              <Input
                {...control}
                value={title}
                maxLength={120}
                onChange={(e) => setTitle(e.target.value)}
              />
            )}
          </Field>
          <Field
            label="Fotoğraf bağlantısı (isteğe bağlı)"
            hint="HTTPS bağlantısı."
          >
            {(control) => (
              <Input
                {...control}
                value={avatar}
                type="url"
                maxLength={500}
                onChange={(e) => setAvatar(e.target.value)}
              />
            )}
          </Field>
          <Field
            label={member ? "Yeni şifre (isteğe bağlı)" : "İlk giriş şifresi"}
            hint="En az 12 karakter. Mevcut şifre gösterilmez."
          >
            {(control) => (
              <Input
                {...control}
                value={password}
                type="password"
                autoComplete="new-password"
                minLength={12}
                maxLength={128}
                required={!member}
                onChange={(e) => setPassword(e.target.value)}
              />
            )}
          </Field>
        </fieldset>
        <p className={styles.note}>
          Rol, aktif durum ve şifre değişiklikleri mevcut oturumları
          sonlandırır. Pasif kişilerin atamaları korunur; işleri ayrıca başka
          bir kişiye devret.
        </p>
        {error && (
          <div role="alert" className={styles.error}>
            {error}
            {conflict && (
              <Button disabled={busy} onClick={() => void refresh()}>
                Güncel bilgileri al
              </Button>
            )}
          </div>
        )}
        <div className={styles.actions}>
          <Button disabled={busy} onClick={close}>
            Vazgeç
          </Button>
          <Button
            type="submit"
            variant="primary"
            busy={busy}
            busyLabel="Kaydediliyor…"
          >
            Kaydet
          </Button>
        </div>
      </form>
      {discard && (
        <ConfirmDialog
          title="Değişiklik kaydedilmedi"
          text="Formdaki değişiklikler silinecek."
          confirmLabel="Kaydetmeden kapat"
          cancelLabel="Forma dön"
          destructive
          onCancel={() => setDiscard(false)}
          onConfirm={onClose}
        />
      )}
    </Dialog>
  );
}

export function TeamView({ user }: { user: User }) {
  const query = useQuery({
    queryKey: ["team-management", user.email],
    enabled: user.role === "admin",
    queryFn: ({ signal }) =>
      apiRequest<{ users: Member[] }>("/api/users?view=team", { signal }).then(
        (data) => data.users,
      ),
  });
  const [edit, setEdit] = useState<Member | null | undefined>(undefined);
  const [filter, setFilter] = useState("");
  if (user.role !== "admin")
    return (
      <ErrorState
        title="Ekip yönetimi"
        message="Bu ekran yalnız yöneticilere açık."
      />
    );
  const members = query.data || [];
  async function refresh(email: string) {
    const result = await query.refetch();
    if (result.isError) throw result.error;
    return result.data?.find((row) => row.email === email);
  }
  return (
    <div className={styles.root}>
      <PageHeader
        eyebrow="YÖNETİM"
        title="Ekip yönetimi"
        subtitle="Hesaplar, yetkiler ve açık görev yükü."
        actions={
          <Button variant="primary" onClick={() => setEdit(null)}>
            Kişi ekle
          </Button>
        }
      />
      <div className={styles.body}>
        <p className={styles.note}>
          En az bir aktif yönetici korunur. Görev yükü aktif atamaları, geciken
          sayı geçmiş takip tarihlerini gösterir.
        </p>
        <Field label="Ekipte ara">
          {(control) => (
            <Input
              {...control}
              type="search"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Ad veya e-posta"
            />
          )}
        </Field>
        {query.isPending && <p role="status">Ekip yükleniyor…</p>}
        {query.isError && (
          <ErrorState
            title="Ekip alınamadı"
            message="Son alınan kayıtlar eski olabilir."
            onRetry={() => void query.refetch()}
          />
        )}
        <ul className={styles.members}>
          {members
            .filter((row) =>
              `${row.name} ${row.email}`
                .toLocaleLowerCase("tr")
                .includes(filter.toLocaleLowerCase("tr")),
            )
            .map((row) => (
              <li key={row.email} className={styles.member}>
                <div>
                  <h2>{row.name || row.email}</h2>
                  <p>{row.email}</p>
                  <p>
                    {row.title ? `${row.title} · ` : ""}
                    {roleLabel(row.role)} ·{" "}
                    {row.active === false ? "Pasif" : "Aktif"}
                  </p>
                </div>
                <dl>
                  <div>
                    <dt>Açık görev</dt>
                    <dd>{row.active_assignments}</dd>
                  </div>
                  <div>
                    <dt>Geciken</dt>
                    <dd>{row.overdue_assignments}</dd>
                  </div>
                </dl>
                <div className={styles.actions}>
                  <Link
                    to={`/raporlar?sorumlu=${encodeURIComponent(row.email)}`}
                  >
                    Atamaları gör
                  </Link>
                  <Button disabled={query.isError} onClick={() => setEdit(row)}>
                    Düzenle
                  </Button>
                </div>
              </li>
            ))}
        </ul>
        {!query.isPending &&
          !query.isError &&
          !members.some((row) =>
            `${row.name} ${row.email}`
              .toLocaleLowerCase("tr")
              .includes(filter.toLocaleLowerCase("tr")),
          ) && (
            <EmptyState title="Eşleşen kişi yok">
              Aramayı temizle veya yeni kişi ekle.
            </EmptyState>
          )}
      </div>
      {edit !== undefined && (
        <MemberDialog
          key={edit?.email || "new"}
          member={edit}
          onClose={() => setEdit(undefined)}
          onSaved={() => setEdit(undefined)}
          onRefresh={refresh}
        />
      )}
    </div>
  );
}
