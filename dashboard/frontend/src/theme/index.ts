import { createTheme } from '@mui/material/styles';
import type { Theme } from '@mui/material/styles';
import { lightPalette, darkPalette } from './palette';
import { typography } from './typography';
import { shadowsArray } from './shadows';
import { buildComponents } from './overrides';

export type ThemeMode = 'light' | 'dark';

export const buildTheme = (mode: ThemeMode, density: 'standard' | 'compact' = 'standard'): Theme =>
  createTheme({
    palette: mode === 'light' ? lightPalette : darkPalette,
    typography,
    shape: { borderRadius: 12 },
    shadows: shadowsArray as never,
    spacing: density === 'compact' ? 6 : 8,
    components: buildComponents(mode),
    direction: 'ltr',
  });
