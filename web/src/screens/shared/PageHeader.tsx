import type { ReactNode } from 'react';

import styles from './shared.module.css';

export interface PageHeaderProps {
  eyebrow: ReactNode;
  title: ReactNode;
  subtitle?: ReactNode;
  /** Right side: the screen's main action(s). */
  actions?: ReactNode;
}

export function PageHeader({ eyebrow, title, subtitle, actions }: PageHeaderProps) {
  return (
    <div className={styles.pageHeader}>
      <div>
        <div className={styles.pageEyebrow}>{eyebrow}</div>
        <h1 className={styles.pageTitle}>{title}</h1>
        {subtitle && <p className={styles.pageSub}>{subtitle}</p>}
      </div>
      {actions}
    </div>
  );
}
