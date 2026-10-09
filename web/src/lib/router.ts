// A small history router: the URL says which screen and which lead is open,
// so deep links, back/forward and refresh keep the same lead.
//
//   /                 the role's home screen
//   /today /cockpit /pipeline /hizmetler /raporlar /analytics /profile /admin
//   /leads/:leadId    one lead (database id, not a list position)
import { useSyncExternalStore, type MouseEvent } from 'react';

export const VIEWS = ['today', 'cockpit', 'pipeline', 'hizmetler', 'raporlar', 'analytics', 'profile', 'admin'] as const;
export type View = (typeof VIEWS)[number];

export type Route =
  | { kind: 'home' }
  | { kind: 'view'; view: View }
  | { kind: 'lead'; leadId: number }
  | { kind: 'unknown'; path: string };

export function parseRoute(pathname: string): Route {
  const path = pathname.replace(/\/+$/, '') || '/';
  if (path === '/') return { kind: 'home' };
  const lead = /^\/leads\/(\d+)$/.exec(path);
  if (lead) return { kind: 'lead', leadId: Number(lead[1]) };
  const view = path.slice(1);
  if ((VIEWS as readonly string[]).includes(view)) return { kind: 'view', view: view as View };
  return { kind: 'unknown', path };
}

export function routeFor(target: { view: View } | { leadId: number | string }): string {
  return 'leadId' in target ? `/leads/${target.leadId}` : `/${target.view}`;
}

const listeners = new Set<() => void>();

function emit(): void {
  listeners.forEach(listener => listener());
}

export function navigate(path: string, options: { replace?: boolean } = {}): void {
  if (path === window.location.pathname) return;
  if (options.replace) window.history.replaceState(null, '', path);
  else window.history.pushState(null, '', path);
  emit();
  window.scrollTo(0, 0);
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener('popstate', listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener('popstate', listener);
  };
}

export function useRoute(): Route {
  const pathname = useSyncExternalStore(subscribe, () => window.location.pathname);
  return parseRoute(pathname);
}

/** For <a href> links: plain clicks navigate in place; modified or middle clicks open a new tab. */
export function followLink(event: MouseEvent<HTMLAnchorElement>, path: string): void {
  if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  event.preventDefault();
  navigate(path);
}
