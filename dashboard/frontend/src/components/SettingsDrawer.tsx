import {
  Box,
  Button,
  Drawer,
  FormControlLabel,
  IconButton,
  Stack,
  Switch,
  TextField,
  Typography,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/CloseOutlined';
import { useState } from 'react';
import { useToken } from '../hooks/useToken';

interface SettingsDrawerProps {
  open: boolean;
  onClose: () => void;
  mode: 'light' | 'dark';
  onModeChange: (m: 'light' | 'dark') => void;
  density: 'standard' | 'compact';
  onDensityChange: (d: 'standard' | 'compact') => void;
}

export function SettingsDrawer({
  open,
  onClose,
  mode,
  onModeChange,
  density,
  onDensityChange,
}: SettingsDrawerProps): JSX.Element {
  const { token, setToken } = useToken();
  const [draft, setDraft] = useState<string>(token);

  const handleSave = () => {
    setToken(draft.trim());
    onClose();
  };

  const handleClear = () => {
    setDraft('');
    setToken('');
  };

  return (
    <Drawer anchor="right" open={open} onClose={onClose} PaperProps={{ sx: { width: { xs: '100%', sm: 400 } } }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ px: 3, py: 2 }}>
        <Typography variant="h6">Settings</Typography>
        <IconButton onClick={onClose} aria-label="close settings">
          <CloseIcon />
        </IconButton>
      </Stack>
      <Box sx={{ px: 3, pb: 3, overflowY: 'auto' }}>
        <Stack spacing={3}>
          <Box>
            <Typography variant="subtitle2" gutterBottom>
              Bearer token
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              Paste the dashboard's bearer token (the value of{' '}
              <code>MEMEX_DASHBOARD_BEARER_TOKEN</code>) to enable mutating actions.
            </Typography>
            <TextField
              fullWidth
              type="password"
              autoComplete="off"
              size="small"
              placeholder="Bearer token"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              inputProps={{ 'aria-label': 'bearer token' }}
            />
            <Stack direction="row" spacing={1} sx={{ mt: 1.5 }}>
              <Button variant="contained" onClick={handleSave} disabled={!draft.trim() && !token}>
                Save
              </Button>
              <Button variant="outlined" color="inherit" onClick={handleClear}>
                Clear
              </Button>
            </Stack>
          </Box>

          <Box>
            <Typography variant="subtitle2" gutterBottom>
              Appearance
            </Typography>
            <FormControlLabel
              control={
                <Switch
                  checked={mode === 'dark'}
                  onChange={(_, checked) => onModeChange(checked ? 'dark' : 'light')}
                />
              }
              label="Dark mode"
            />
            <FormControlLabel
              control={
                <Switch
                  checked={density === 'compact'}
                  onChange={(_, checked) => onDensityChange(checked ? 'compact' : 'standard')}
                />
              }
              label="Compact density"
            />
          </Box>

          <Box>
            <Typography variant="subtitle2" gutterBottom>
              About
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Memex dashboard. Read-only endpoints work without a token; the
              token is required to mutate the queue, edit the taxonomy, route
              inbox items, or run retrieval.
            </Typography>
          </Box>
        </Stack>
      </Box>
    </Drawer>
  );
}
