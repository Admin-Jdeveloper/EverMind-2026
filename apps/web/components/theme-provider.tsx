'use client';

import * as React from 'react';

export type Theme = 'dark' | 'light' | 'system';

interface ThemeContextType {
  theme: Theme;
  resolvedTheme: 'dark' | 'light';
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

const ThemeContext = React.createContext<ThemeContextType>({
  theme: 'dark',
  resolvedTheme: 'dark',
  setTheme: () => {},
  toggleTheme: () => {},
});

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = React.useState<Theme>('dark');
  const [resolvedTheme, setResolvedTheme] = React.useState<'dark' | 'light'>('dark');
  const [mounted, setMounted] = React.useState(false);

  const applyTheme = React.useCallback((t: Theme) => {
    const root = document.documentElement;
    let effective: 'dark' | 'light' = 'dark';

    if (t === 'system') {
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      effective = prefersDark ? 'dark' : 'light';
    } else {
      effective = t;
    }

    setResolvedTheme(effective);

    if (effective === 'dark') {
      root.classList.add('dark');
      root.classList.remove('light');
    } else {
      root.classList.add('light');
      root.classList.remove('dark');
    }
  }, []);

  React.useEffect(() => {
    setMounted(true);
    const stored = localStorage.getItem('mc_theme') as Theme | null;
    if (stored === 'light' || stored === 'dark' || stored === 'system') {
      setThemeState(stored);
      applyTheme(stored);
    } else {
      setThemeState('dark');
      applyTheme('dark');
    }

    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handleMediaChange = () => {
      const current = localStorage.getItem('mc_theme') as Theme | null;
      if (current === 'system' || !current) {
        applyTheme('system');
      }
    };

    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === 'mc_theme' && (e.newValue === 'light' || e.newValue === 'dark' || e.newValue === 'system')) {
        setThemeState(e.newValue);
        applyTheme(e.newValue);
      }
    };

    mediaQuery.addEventListener('change', handleMediaChange);
    window.addEventListener('storage', handleStorageChange);

    return () => {
      mediaQuery.removeEventListener('change', handleMediaChange);
      window.removeEventListener('storage', handleStorageChange);
    };
  }, [applyTheme]);

  const setTheme = (t: Theme) => {
    setThemeState(t);
    localStorage.setItem('mc_theme', t);
    applyTheme(t);
  };

  const toggleTheme = () => {
    const next = resolvedTheme === 'dark' ? 'light' : 'dark';
    setTheme(next);
  };

  return (
    <ThemeContext.Provider value={{ theme, resolvedTheme, setTheme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return React.useContext(ThemeContext);
}
