import { useEffect, useRef } from 'react';

import { initialsFor } from '../domain/format';
import type { User } from '../data/types';
import { followLink, routeFor, type View } from '../lib/router';
import type { Theme } from './theme';
import styles from './Topbar.module.css';

interface NavItem {
  view: View;
  label: string;
  count?: number;
}

function navItems(user: User, leadCount: number): NavItem[] {
  const sales = user.role === 'sales';
  const items: Array<NavItem | false> = [
    sales && { view: 'today', label: 'Bugün' },
    !sales && { view: 'cockpit', label: 'Workspace' },
    { view: 'raporlar', label: 'Leadler', count: leadCount },
    { view: 'pipeline', label: 'Pipeline' },
    { view: 'analytics', label: 'Raporlar' },
    { view: 'hizmetler', label: 'Hizmetler' },
    { view: 'profile', label: 'Profil' },
    user.role === 'admin' && { view: 'admin', label: 'Admin' },
  ];
  return items.filter((item): item is NavItem => Boolean(item));
}

export interface TopbarProps {
  /** The screen shown now ("detail" counts as the lead list). */
  view: View | 'detail';
  homeView: View;
  user: User;
  leadCount: number;
  theme: Theme;
  onToggleTheme: () => void;
  onOpenSearch: () => void;
}

export function Topbar({ view, homeView, user, leadCount, theme, onToggleTheme, onOpenSearch }: TopbarProps) {
  const current = view === 'detail' ? 'raporlar' : view;
  const pathFor = (target: View) => (target === homeView ? '/' : routeFor({ view: target }));
  const navRef = useRef<HTMLElement>(null);

  // On narrow screens the menu scrolls sideways; keep the current page in view.
  // (scrollLeft on the menu only: scrollIntoView would also shift the page.)
  useEffect(() => {
    const nav = navRef.current;
    const active = nav?.querySelector<HTMLElement>('[aria-current="page"]');
    if (!nav || !active) return;
    const bounds = nav.getBoundingClientRect();
    const item = active.getBoundingClientRect();
    if (item.left < bounds.left || item.right > bounds.right) nav.scrollLeft += item.left - bounds.left - 8;
  }, [current]);

  return (
    <header className={styles.bar}>
      <div className={styles.brand}>
        <div className={styles.logo}><img src="/logo-mark.png" alt="Zeplin Media" /></div>
        <div className={styles.brandText}>
          <div className={styles.brandName}>Zeplin Media</div>
          <div className={styles.brandSub}>Lead Workspace</div>
        </div>
      </div>

      <nav ref={navRef} className={styles.nav} aria-label="Ana menü">
        {navItems(user, leadCount).map(item => (
          <a
            key={item.view}
            href={pathFor(item.view)}
            className={styles.item}
            aria-current={current === item.view ? 'page' : undefined}
            onClick={event => followLink(event, pathFor(item.view))}
          >
            <span>{item.label}</span>
            {item.count !== undefined && <span className={styles.count}>{item.count}</span>}
          </a>
        ))}
      </nav>

      <div className={styles.spacer} />

      <button type="button" className={styles.search} onClick={onOpenSearch} aria-label="Lead ara">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" /></svg>
        <span className={styles.searchLabel}>Lead, firma veya hizmet ara</span>
      </button>
      <button
        type="button"
        className={styles.iconButton}
        onClick={onToggleTheme}
        aria-label={theme === 'light' ? 'Karanlık moda geç' : 'Aydınlık moda geç'}
        title={theme === 'light' ? 'Karanlık moda geç' : 'Aydınlık moda geç'}
      >
        {theme === 'light'
          ? <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M21 12.8A9 9 0 1111.2 3 7 7 0 0021 12.8z" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
          : <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="4.5" stroke="currentColor" strokeWidth="1.8" /><path d="M12 2v2.5M12 19.5V22M4.2 4.2l1.8 1.8M18 18l1.8 1.8M2 12h2.5M19.5 12H22M4.2 19.8L6 18M18 6l1.8-1.8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" /></svg>}
      </button>
      {user.role === 'admin' && (
        <a
          href={routeFor({ view: 'admin' })}
          className={`${styles.iconButton} ${styles.automation}`}
          aria-label="Yeni tarama (Admin)"
          title="Yeni tarama (Admin)"
          onClick={event => followLink(event, routeFor({ view: 'admin' }))}
        >
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M13 2L5 13h6l-1 9 8-11h-6l1-9z" fill="var(--accent)" stroke="var(--accent)" strokeWidth="1.2" strokeLinejoin="round" /></svg>
        </a>
      )}
      <a
        href={routeFor({ view: 'profile' })}
        className={styles.avatar}
        aria-label={`${user.name || user.email} profilini aç`}
        title={`${user.name || user.email} profilini aç`}
        onClick={event => followLink(event, routeFor({ view: 'profile' }))}
      >
        {user.avatar_url ? <img src={user.avatar_url} alt="" /> : initialsFor(user.name || user.email)}
      </a>
    </header>
  );
}
