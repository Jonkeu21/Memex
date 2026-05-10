import { Box, Toolbar } from '@mui/material';
import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import { useThemeMode } from '../../hooks/useThemeMode';
import { Sidebar, SIDEBAR_WIDTH } from './Sidebar';
import { TopBar } from './TopBar';
import { SettingsDrawer } from '../SettingsDrawer';

export function AppShell(): JSX.Element {
  const { mode, setMode, density, setDensity } = useThemeMode();
  const [settingsOpen, setSettingsOpen] = useState(false);

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh', backgroundColor: (t) => t.palette.background.default }}>
      <Sidebar />
      <Box sx={{ flexGrow: 1, ml: { md: 0 } }}>
        <TopBar
          mode={mode}
          onToggleMode={() => setMode(mode === 'light' ? 'dark' : 'light')}
          onOpenSettings={() => setSettingsOpen(true)}
        />
        <Toolbar sx={{ minHeight: { xs: 64, sm: 72 } }} />
        <Box sx={{ p: { xs: 2, md: 3 }, maxWidth: 1400, mx: 'auto' }}>
          <Outlet />
        </Box>
      </Box>
      <SettingsDrawer
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        mode={mode}
        onModeChange={setMode}
        density={density}
        onDensityChange={setDensity}
      />
    </Box>
  );
}

export { SIDEBAR_WIDTH };
