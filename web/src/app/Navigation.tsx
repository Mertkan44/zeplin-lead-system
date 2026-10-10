// App navigation. Desktop: a sidebar with every section (icons only below
// 1280 px) and a utility bar with search. Phones: a compact top bar, a
// bottom bar with the three main sections and a menu drawer with the rest.
import type { User } from '../data/types';
import { roleLabel } from '../domain/catalog';
import { initialsFor } from '../domain/format';
import { routeFor, type View } from '../lib/router';
import { Dialog, Link } from '../ui';
import { NavIcon } from './navIcons';
import type { Theme } from './theme';
import styles from './Navigation.module.css';

interface NavItem {
  view: View;
  label: string;
  count?: number;
}

function navItems(user: User, leadCount: number): NavItem[] {
  const sales = user.role === 'sales';
  const items: Array<NavItem | false> = [
    sales && { view: 'today', label: 'Bugün' },
    !sales && { view: 'cockpit', label: 'Genel bakış' },
    { view: 'raporlar', label: 'Leadler', count: leadCount },
    { view: 'pipeline', label: 'Pipeline' },
    { view: 'analytics', label: 'Raporlar' },
    { view: 'hizmetler', label: 'Hizmetler' },
    user.role === 'admin' && { view: 'admin', label: 'Admin' },
  ];
  return items.filter((item): item is NavItem => Boolean(item));
}

export interface NavigationProps {
  /** The screen shown now ("detail" belongs to the lead list). */
  view: View | 'detail';
  homeView: View;
  user: User;
  leadCount: number;
  theme: Theme;
  onToggleTheme: () => void;
  onOpenSearch: () => void;
}

function useNav({ view, homeView, user, leadCount }: NavigationProps) {
  const current = view === 'detail' ? 'raporlar' : view;
  const pathFor = (target: View) => (target === homeView ? '/' : routeFor({ view: target }));
  return { current, pathFor, items: navItems(user, leadCount) };
}

function Brand() {
  return (
    <>
      <span className={styles.logo}><img src="/logo-mark.png" alt="" /></span>
      <span className={styles.brandText}>
        <span className={styles.brandName}>Zeplin Media</span>
        <br />
        <span className={styles.brandSub}>Lead Workspace</span>
      </span>
    </>
  );
}

function Account({ user, current, onNavigate }: { user: User; current: View; onNavigate?: () => void }) {
  return (
    <Link
      to={routeFor({ view: 'profile' })}
      onClick={onNavigate}
      className={styles.account}
      aria-current={current === 'profile' ? 'page' : undefined}
      title={`${user.name || user.email} · Profil`}
    >
      <span className={styles.avatar}>{user.avatar_url ? <img src={user.avatar_url} alt="" /> : initialsFor(user.name || user.email)}</span>
      <span className={styles.accountText}>
        <span className={styles.accountName}>Profil</span>
        <span className={styles.accountRole}>{user.name || user.email} · {roleLabel(user.role)}</span>
      </span>
    </Link>
  );
}

function ThemeButton({ theme, onToggleTheme, className, withLabel }: { theme: Theme; onToggleTheme: () => void; className: string; withLabel?: boolean }) {
  const label = theme === 'light' ? 'Karanlık moda geç' : 'Aydınlık moda geç';
  return (
    <button type="button" className={className} onClick={onToggleTheme} aria-label={label} title={label}>
      <NavIcon name={theme === 'light' ? 'moon' : 'sun'} />
      {withLabel && <span className={styles.footLabel}>{theme === 'light' ? 'Karanlık tema' : 'Aydınlık tema'}</span>}
    </button>
  );
}

export function Sidebar(props: NavigationProps) {
  const { current, pathFor, items } = useNav(props);
  return (
    <aside className={styles.sidebar}>
      <Link to="/" className={styles.brand} aria-label="Zeplin Media ana sayfa"><Brand /></Link>
      <nav aria-label="Ana menü">
        <ul className={styles.navList}>
          {items.map(item => (
            <li key={item.view}>
              <Link to={pathFor(item.view)} className={styles.navItem} aria-current={current === item.view ? 'page' : undefined} title={item.label}>
                <NavIcon name={item.view} />
                <span className={styles.navLabel}>{item.label}</span>
                {item.count !== undefined && <span className={styles.navCount}>{item.count}</span>}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      <div className={styles.sidebarFoot}>
        <ThemeButton theme={props.theme} onToggleTheme={props.onToggleTheme} className={styles.footButton} withLabel />
        <Account user={props.user} current={current} />
      </div>
    </aside>
  );
}

export function TopBar(props: NavigationProps) {
  return (
    <header className={styles.topbar}>
      <Link to="/" className={styles.mobileBrand} aria-label="Zeplin Media ana sayfa">
        <span className={styles.logo}><img src="/logo-mark.png" alt="" /></span>
        Zeplin
      </Link>
      <button type="button" className={styles.search} onClick={props.onOpenSearch} aria-label="Lead ara" aria-keyshortcuts="/">
        <NavIcon name="search" size={16} />
        <span className={styles.searchText}>Lead, firma veya hizmet ara</span>
        <kbd className={styles.kbd} aria-hidden="true">/</kbd>
      </button>
      <div className={styles.spacer} />
      <button type="button" className={`${styles.iconButton} ${styles.mobileOnly}`} onClick={props.onOpenSearch} aria-label="Lead ara">
        <NavIcon name="search" />
      </button>
      <span className={styles.mobileOnly}>
        <ThemeButton theme={props.theme} onToggleTheme={props.onToggleTheme} className={styles.iconButton} />
      </span>
    </header>
  );
}

/** Phones: the three main sections and the menu. */
export function BottomNav(props: NavigationProps & { onOpenMenu: () => void }) {
  const { current, pathFor, items } = useNav(props);
  const main = items.filter(item => ['today', 'cockpit', 'raporlar', 'pipeline'].includes(item.view)).slice(0, 3);
  return (
    <nav className={styles.bottomNav} aria-label="Hızlı menü">
      {main.map(item => (
        <Link key={item.view} to={pathFor(item.view)} className={styles.bottomItem} aria-current={current === item.view ? 'page' : undefined}>
          <NavIcon name={item.view} size={20} />
          {item.label}
        </Link>
      ))}
      <button type="button" className={styles.bottomItem} onClick={props.onOpenMenu} aria-haspopup="dialog">
        <NavIcon name="menu" size={20} />
        Menü
      </button>
    </nav>
  );
}

/** Phones: every section, the theme and the account, in a drawer. */
export function MenuDrawer(props: NavigationProps & { onClose: () => void }) {
  const { current, pathFor, items } = useNav(props);
  return (
    <Dialog title="Menü" placement="left" size="sm" onClose={props.onClose}>
      <div className={styles.drawerNav}>
        <nav aria-label="Tüm bölümler">
          <ul className={styles.navList}>
            {items.map(item => (
              <li key={item.view}>
                <Link to={pathFor(item.view)} className={styles.navItem} aria-current={current === item.view ? 'page' : undefined} onClick={props.onClose}>
                  <NavIcon name={item.view} />
                  <span>{item.label}</span>
                  {item.count !== undefined && <span className={styles.navCount}>{item.count}</span>}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
        <div className={styles.sidebarFoot}>
          <ThemeButton theme={props.theme} onToggleTheme={props.onToggleTheme} className={styles.footButton} withLabel />
          <Account user={props.user} current={current} onNavigate={props.onClose} />
        </div>
      </div>
    </Dialog>
  );
}
