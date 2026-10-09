import type { ReactNode } from 'react';

import { normalizeStatus, statusMeta } from '../domain/catalog';
import styles from './Badge.module.css';

export type BadgeTone = 'neutral' | 'accent' | 'success' | 'warning' | 'danger' | 'info';

export interface BadgeProps {
  tone?: BadgeTone;
  /** "tag": square corners and display font, for counts and labels. */
  shape?: 'pill' | 'tag';
  caps?: boolean;
  className?: string;
  children: ReactNode;
}

export function Badge({ tone = 'neutral', shape = 'pill', caps = false, className, children }: BadgeProps) {
  return (
    <span className={[styles.badge, styles[tone], shape === 'tag' ? styles.tag : '', caps ? styles.caps : '', className].filter(Boolean).join(' ')}>
      {children}
    </span>
  );
}

/** A lead's pipeline status: text plus color, from the one status vocabulary. */
export function StatusBadge({ status }: { status: string | null | undefined }) {
  const key = normalizeStatus(status);
  return <span className={[styles.badge, styles.caps, styles[`status-${key}`]].join(' ')}>{statusMeta(key).label}</span>;
}

/** Score grade (A–D); `label` overrides the text (e.g. "Sınıf A", "%40"). */
export function GradeBadge({ grade, label }: { grade: string | null | undefined; label?: ReactNode }) {
  const key = grade && ['A', 'B', 'C', 'D'].includes(grade) ? grade : 'none';
  return <span className={[styles.badge, styles.tag, styles[`grade-${key}`]].join(' ')}>{label ?? grade ?? '—'}</span>;
}
