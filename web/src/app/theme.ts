// Light/dark theme: a UI preference, the only thing kept in localStorage.
// index.html applies the saved theme before first paint.
import { useEffect, useState } from 'react';

export type Theme = 'light' | 'dark';

const KEY = 'zeplin_theme';

export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(() => (document.documentElement.dataset.theme === 'light' ? 'light' : 'dark'));
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem(KEY, theme); } catch { /* private mode: the theme just isn't remembered */ }
  }, [theme]);
  return [theme, () => setTheme(current => (current === 'light' ? 'dark' : 'light'))];
}
