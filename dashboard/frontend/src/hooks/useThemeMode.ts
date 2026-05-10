import { useCallback, useEffect, useState } from 'react';
import type { ThemeMode } from '../theme';

const KEY = 'memex.dashboard.themeMode';
const DENSITY_KEY = 'memex.dashboard.density';

export function useThemeMode(): {
  mode: ThemeMode;
  setMode: (m: ThemeMode) => void;
  density: 'standard' | 'compact';
  setDensity: (d: 'standard' | 'compact') => void;
} {
  const [mode, setModeState] = useState<ThemeMode>(() => {
    try {
      const stored = localStorage.getItem(KEY);
      return stored === 'dark' ? 'dark' : 'light';
    } catch {
      return 'light';
    }
  });
  const [density, setDensityState] = useState<'standard' | 'compact'>(() => {
    try {
      return (localStorage.getItem(DENSITY_KEY) as 'compact' | null) === 'compact'
        ? 'compact'
        : 'standard';
    } catch {
      return 'standard';
    }
  });

  const setMode = useCallback((m: ThemeMode) => {
    try {
      localStorage.setItem(KEY, m);
    } catch {
      /* ignore */
    }
    setModeState(m);
  }, []);

  const setDensity = useCallback((d: 'standard' | 'compact') => {
    try {
      localStorage.setItem(DENSITY_KEY, d);
    } catch {
      /* ignore */
    }
    setDensityState(d);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = mode;
  }, [mode]);

  return { mode, setMode, density, setDensity };
}
