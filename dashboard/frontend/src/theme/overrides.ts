import type { Components, Theme } from '@mui/material/styles';
import { customShadows } from './shadows';

export const buildComponents = (mode: 'light' | 'dark'): Components<Theme> => ({
  MuiCssBaseline: {
    styleOverrides: {
      body: {
        WebkitFontSmoothing: 'antialiased',
        MozOsxFontSmoothing: 'grayscale',
      },
    },
  },
  MuiCard: {
    styleOverrides: {
      root: {
        borderRadius: 16,
        boxShadow: customShadows.card,
        backgroundImage: 'none',
        position: 'relative',
        zIndex: 0,
      },
    },
  },
  MuiCardHeader: {
    defaultProps: {
      titleTypographyProps: { variant: 'h6' },
      subheaderTypographyProps: { variant: 'body2', color: 'text.secondary' },
    },
    styleOverrides: {
      root: {
        padding: '24px 24px 16px',
      },
    },
  },
  MuiCardContent: {
    styleOverrides: {
      root: { padding: 24 },
    },
  },
  MuiButton: {
    defaultProps: {
      disableElevation: true,
    },
    styleOverrides: {
      root: {
        borderRadius: 8,
        textTransform: 'none',
        fontWeight: 700,
        boxShadow: 'none',
      },
      sizeMedium: {
        padding: '6px 14px',
      },
      sizeLarge: {
        padding: '10px 22px',
      },
      containedPrimary: {
        boxShadow: customShadows.primary,
        '&:hover': {
          boxShadow: customShadows.primary,
        },
      },
    },
  },
  MuiTextField: {
    defaultProps: {
      variant: 'outlined',
      size: 'small',
    },
  },
  MuiOutlinedInput: {
    styleOverrides: {
      root: {
        borderRadius: 8,
      },
    },
  },
  MuiTableCell: {
    styleOverrides: {
      root: {
        borderBottom: `1px dashed rgba(145, 158, 171, 0.16)`,
      },
      head: {
        fontWeight: 700,
        backgroundColor: mode === 'light' ? '#F4F6F8' : '#1C252E',
        color: mode === 'light' ? '#637381' : '#919EAB',
      },
    },
  },
  MuiChip: {
    styleOverrides: {
      root: {
        borderRadius: 8,
        fontWeight: 600,
      },
    },
  },
  MuiAppBar: {
    defaultProps: { elevation: 0 },
    styleOverrides: {
      root: {
        backgroundImage: 'none',
        backgroundColor: mode === 'light' ? 'rgba(255, 255, 255, 0.8)' : 'rgba(28, 37, 46, 0.8)',
        backdropFilter: 'saturate(180%) blur(20px)',
        WebkitBackdropFilter: 'saturate(180%) blur(20px)',
        boxShadow: 'none',
        borderBottom: '1px solid rgba(145, 158, 171, 0.16)',
        color: mode === 'light' ? '#1C252E' : '#FFFFFF',
      },
    },
  },
  MuiDrawer: {
    styleOverrides: {
      paper: {
        borderRight: 'none',
        boxShadow: customShadows.z1,
      },
    },
  },
  MuiPaper: {
    defaultProps: { elevation: 0 },
    styleOverrides: {
      root: {
        backgroundImage: 'none',
      },
    },
  },
  MuiTooltip: {
    styleOverrides: {
      tooltip: {
        backgroundColor: '#1C252E',
        fontSize: '0.75rem',
        fontWeight: 600,
        borderRadius: 8,
      },
    },
  },
});
