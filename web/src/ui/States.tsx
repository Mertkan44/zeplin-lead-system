// Screen states every view needs: loading, empty, failed, and the banner that
// says shown data may be out of date.
import type { ReactNode } from 'react';

import { Button } from './Button';
import styles from './States.module.css';

export function LoadingState({ label = 'Yükleniyor…' }: { label?: string }) {
  return (
    <div className={styles.screen}>
      <div className={styles.loading} role="status">
        <span className={styles.spinner} aria-hidden="true" />
        {label}
      </div>
    </div>
  );
}

export interface EmptyStateProps {
  title?: ReactNode;
  /** Why it is empty and what can be done. */
  children: ReactNode;
  action?: ReactNode;
  className?: string;
}

/** Inline "nothing here" box inside a list or section. */
export function EmptyState({ title, children, action, className }: EmptyStateProps) {
  return (
    <div className={[styles.empty, className].filter(Boolean).join(' ')}>
      {title && <div className={styles.emptyTitle}>{title}</div>}
      <div>{children}</div>
      {action && <div className={styles.emptyAction}>{action}</div>}
    </div>
  );
}

export interface ErrorStateProps {
  eyebrow?: ReactNode;
  title: ReactNode;
  message: ReactNode;
  /** Technical detail such as an error code; shown small. */
  detail?: ReactNode;
  onRetry?: () => void;
  retrying?: boolean;
  retryLabel?: string;
  action?: ReactNode;
}

/** Full-screen message card: a failed load, a missing record, no access. */
export function ErrorState({ eyebrow, title, message, detail, onRetry, retrying = false, retryLabel = 'Tekrar dene', action }: ErrorStateProps) {
  return (
    <div className={styles.screen}>
      <div className={styles.card}>
        {eyebrow && <div className={styles.eyebrow}>{eyebrow}</div>}
        <h1 className={styles.title}>{title}</h1>
        <p className={styles.text}>{message}</p>
        {detail && <p className={styles.detail}>{detail}</p>}
        {onRetry && (
          <Button variant="primary" size="lg" block busy={retrying} busyLabel="Yükleniyor…" onClick={onRetry}>{retryLabel}</Button>
        )}
        {action}
      </div>
    </div>
  );
}

export interface BannerProps {
  tone?: 'warning' | 'danger';
  /** role=alert interrupts the screen reader; status waits its turn. */
  urgent?: boolean;
  children: ReactNode;
  actionLabel?: string;
  onAction?: () => void;
  actionBusy?: boolean;
}

/** Full-width notice under the top bar. */
export function Banner({ tone = 'warning', urgent = false, children, actionLabel, onAction, actionBusy = false }: BannerProps) {
  return (
    <div role={urgent ? 'alert' : 'status'} className={[styles.banner, tone === 'danger' ? styles.bannerDanger : ''].filter(Boolean).join(' ')}>
      <span>{children}</span>
      {onAction && (
        <button type="button" className={styles.bannerButton} disabled={actionBusy} onClick={onAction}>{actionLabel}</button>
      )}
    </div>
  );
}
