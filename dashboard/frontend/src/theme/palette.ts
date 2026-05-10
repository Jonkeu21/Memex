import type { PaletteOptions } from '@mui/material/styles';

// Primary green = Minimal UI Kit's "Integrate" preset (≈ #00A76F).
// Other colour roles are used sparingly — the kit's chrome is monochrome with
// soft greys and the primary green as the only accent.
export const lightPalette: PaletteOptions = {
  mode: 'light',
  primary: {
    lighter: '#C8FAD6',
    light: '#5BE49B',
    main: '#00A76F',
    dark: '#007867',
    darker: '#004B50',
    contrastText: '#FFFFFF',
  } as never,
  secondary: {
    lighter: '#EFD6FF',
    light: '#C684FF',
    main: '#8E33FF',
    dark: '#5119B7',
    darker: '#27097A',
    contrastText: '#FFFFFF',
  } as never,
  info: {
    main: '#00B8D9',
    contrastText: '#FFFFFF',
  },
  success: {
    main: '#22C55E',
    contrastText: '#FFFFFF',
  },
  warning: {
    main: '#FFAB00',
    contrastText: '#1C252E',
  },
  error: {
    main: '#FF5630',
    contrastText: '#FFFFFF',
  },
  grey: {
    50: '#FCFDFD',
    100: '#F9FAFB',
    200: '#F4F6F8',
    300: '#DFE3E8',
    400: '#C4CDD5',
    500: '#919EAB',
    600: '#637381',
    700: '#454F5B',
    800: '#1C252E',
    900: '#141A21',
  },
  background: {
    default: '#F9FAFB',
    paper: '#FFFFFF',
  },
  text: {
    primary: '#1C252E',
    secondary: '#637381',
    disabled: '#919EAB',
  },
  divider: 'rgba(145, 158, 171, 0.16)',
};

export const darkPalette: PaletteOptions = {
  mode: 'dark',
  primary: lightPalette.primary,
  secondary: lightPalette.secondary,
  info: { main: '#00B8D9', contrastText: '#FFFFFF' },
  success: { main: '#22C55E', contrastText: '#FFFFFF' },
  warning: { main: '#FFAB00', contrastText: '#FFFFFF' },
  error: { main: '#FF5630', contrastText: '#FFFFFF' },
  grey: lightPalette.grey,
  background: {
    default: '#141A21',
    paper: '#1C252E',
  },
  text: {
    primary: '#FFFFFF',
    secondary: '#919EAB',
    disabled: '#637381',
  },
  divider: 'rgba(145, 158, 171, 0.2)',
};
