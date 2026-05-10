import { AppBar, IconButton, InputAdornment, Stack, TextField, Toolbar, Tooltip } from '@mui/material';
import SearchIcon from '@mui/icons-material/SearchOutlined';
import SettingsIcon from '@mui/icons-material/SettingsOutlined';
import LightModeIcon from '@mui/icons-material/LightModeOutlined';
import DarkModeIcon from '@mui/icons-material/DarkModeOutlined';
import { SIDEBAR_WIDTH } from './Sidebar';
import type { ThemeMode } from '../../theme';

interface TopBarProps {
  mode: ThemeMode;
  onToggleMode: () => void;
  onOpenSettings: () => void;
}

export function TopBar({ mode, onToggleMode, onOpenSettings }: TopBarProps): JSX.Element {
  return (
    <AppBar
      position="fixed"
      sx={{
        width: { md: `calc(100% - ${SIDEBAR_WIDTH}px)` },
        ml: { md: `${SIDEBAR_WIDTH}px` },
      }}
    >
      <Toolbar sx={{ minHeight: { xs: 64, sm: 72 }, gap: 2 }}>
        <TextField
          size="small"
          placeholder="Search the vault…"
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon fontSize="small" />
              </InputAdornment>
            ),
          }}
          sx={{
            width: { xs: 200, md: 360 },
            '& .MuiOutlinedInput-root': {
              backgroundColor: (t) => t.palette.background.paper,
            },
          }}
        />
        <Stack direction="row" spacing={1} sx={{ ml: 'auto' }}>
          <Tooltip title={mode === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}>
            <IconButton onClick={onToggleMode} aria-label="toggle theme">
              {mode === 'light' ? <DarkModeIcon /> : <LightModeIcon />}
            </IconButton>
          </Tooltip>
          <Tooltip title="Settings">
            <IconButton onClick={onOpenSettings} aria-label="open settings">
              <SettingsIcon />
            </IconButton>
          </Tooltip>
        </Stack>
      </Toolbar>
    </AppBar>
  );
}
