import type { TypographyOptions } from '@mui/material/styles/createTypography';

// Public Sans, generous line-height, the kit's heading scale.
export const typography: TypographyOptions = {
  fontFamily:
    '"Public Sans", -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif',
  fontWeightLight: 400,
  fontWeightRegular: 400,
  fontWeightMedium: 500,
  fontWeightBold: 700,
  h1: { fontWeight: 800, fontSize: '2.5rem', lineHeight: 1.25, letterSpacing: '-0.01em' },
  h2: { fontWeight: 800, fontSize: '2rem', lineHeight: 1.3, letterSpacing: '-0.005em' },
  h3: { fontWeight: 700, fontSize: '1.5rem', lineHeight: 1.4 },
  h4: { fontWeight: 700, fontSize: '1.25rem', lineHeight: 1.5 },
  h5: { fontWeight: 700, fontSize: '1.125rem', lineHeight: 1.5 },
  h6: { fontWeight: 700, fontSize: '1rem', lineHeight: 1.55 },
  subtitle1: { fontWeight: 600, fontSize: '1rem', lineHeight: 1.5 },
  subtitle2: { fontWeight: 600, fontSize: '0.875rem', lineHeight: 1.6 },
  body1: { fontSize: '0.9375rem', lineHeight: 1.6 },
  body2: { fontSize: '0.875rem', lineHeight: 1.55 },
  caption: { fontSize: '0.75rem', lineHeight: 1.5, color: '#637381' },
  overline: {
    fontSize: '0.75rem',
    fontWeight: 700,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
  },
  button: {
    fontWeight: 700,
    fontSize: '0.875rem',
    textTransform: 'none',
  },
};
