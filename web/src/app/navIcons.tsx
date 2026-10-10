// Outline icons for the navigation; they take the text color.
import type { View } from '../lib/router';

const paths: Record<View | 'menu' | 'search' | 'sun' | 'moon' | 'logout', string> = {
  today: 'M8 3v3M16 3v3M4 9h16M5 5h14a1 1 0 011 1v13a1 1 0 01-1 1H5a1 1 0 01-1-1V6a1 1 0 011-1zM9 14l2 2 4-4',
  cockpit: 'M4 4h7v7H4zM13 4h7v4h-7zM13 10h7v10h-7zM4 13h7v7H4z',
  raporlar: 'M9 6h11M9 12h11M9 18h11M4.5 6h.01M4.5 12h.01M4.5 18h.01',
  pipeline: 'M4 5h4v14H4zM10 5h4v9h-4zM16 5h4v6h-4z',
  analytics: 'M4 20V10M10 20V4M16 20v-7M21 20H3',
  hizmetler: 'M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3zM12 12l8-4.5M12 12v9M12 12L4 7.5',
  admin: 'M11 4a7 7 0 100 14 7 7 0 000-14zM21 21l-4.5-4.5M11 8v6M8 11h6',
  profile: 'M12 12a4 4 0 100-8 4 4 0 000 8zM4 21a8 8 0 0116 0',
  menu: 'M4 7h16M4 12h16M4 17h16',
  search: 'M11 4a7 7 0 100 14 7 7 0 000-14zM21 21l-4.3-4.3',
  sun: 'M12 7.5a4.5 4.5 0 100 9 4.5 4.5 0 000-9zM12 2v2.5M12 19.5V22M4.2 4.2L6 6M18 18l1.8 1.8M2 12h2.5M19.5 12H22M4.2 19.8L6 18M18 6l1.8-1.8',
  moon: 'M21 12.8A9 9 0 1111.2 3 7 7 0 0021 12.8z',
  logout: 'M15 4h3a2 2 0 012 2v12a2 2 0 01-2 2h-3M10 17l5-5-5-5M15 12H4',
};

export type IconName = keyof typeof paths;

export function NavIcon({ name, size = 18 }: { name: IconName; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={paths[name]} />
    </svg>
  );
}
