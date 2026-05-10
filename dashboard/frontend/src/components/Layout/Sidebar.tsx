import { Box, Drawer, List, ListItemButton, ListItemIcon, ListItemText, Stack, Toolbar, Typography } from '@mui/material';
import InboxIcon from '@mui/icons-material/InboxOutlined';
import AccountTreeIcon from '@mui/icons-material/AccountTreeOutlined';
import FolderIcon from '@mui/icons-material/FolderOpenOutlined';
import SpeedIcon from '@mui/icons-material/SpeedOutlined';
import ChatIcon from '@mui/icons-material/ChatBubbleOutlineOutlined';
import QueueIcon from '@mui/icons-material/PlaylistPlayOutlined';
import { NavLink } from 'react-router-dom';

const NAV_WIDTH = 280;

const NAV_ITEMS = [
  { to: '/queue', label: 'Queue', icon: <QueueIcon /> },
  { to: '/inbox', label: 'Inbox triage', icon: <InboxIcon /> },
  { to: '/taxonomy', label: 'Taxonomy', icon: <AccountTreeIcon /> },
  { to: '/captures', label: 'Captures', icon: <FolderIcon /> },
  { to: '/rate-limit', label: 'Rate limit', icon: <SpeedIcon /> },
  { to: '/retrieval', label: 'Retrieval chat', icon: <ChatIcon /> },
];

export function Sidebar(): JSX.Element {
  return (
    <Drawer
      variant="permanent"
      sx={{
        width: NAV_WIDTH,
        flexShrink: 0,
        '& .MuiDrawer-paper': {
          width: NAV_WIDTH,
          boxSizing: 'border-box',
          backgroundColor: (t) => t.palette.background.default,
          borderRight: (t) => `1px solid ${t.palette.divider}`,
        },
      }}
    >
      <Toolbar sx={{ minHeight: { xs: 64, sm: 72 } }}>
        <Stack direction="row" spacing={1.5} alignItems="center">
          <Box
            sx={{
              width: 32,
              height: 32,
              borderRadius: 1.5,
              background: (t) =>
                `linear-gradient(135deg, ${t.palette.primary.light}, ${t.palette.primary.main})`,
            }}
          />
          <Box>
            <Typography variant="subtitle1" sx={{ fontWeight: 800, lineHeight: 1.1 }}>
              Memex
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Dashboard
            </Typography>
          </Box>
        </Stack>
      </Toolbar>
      <Box sx={{ px: 2, pt: 1, pb: 0 }}>
        <Typography
          variant="overline"
          color="text.secondary"
          sx={{ pl: 2, display: 'block' }}
        >
          Workspace
        </Typography>
      </Box>
      <List sx={{ px: 2 }}>
        {NAV_ITEMS.map((item) => (
          <ListItemButton
            key={item.to}
            component={NavLink}
            to={item.to}
            sx={{
              borderRadius: 1.5,
              mb: 0.5,
              color: 'text.secondary',
              '& .MuiListItemIcon-root': { color: 'text.secondary', minWidth: 36 },
              '&.active': {
                color: 'primary.dark',
                backgroundColor: (t) =>
                  t.palette.mode === 'light'
                    ? 'rgba(0, 167, 111, 0.08)'
                    : 'rgba(91, 228, 155, 0.16)',
                fontWeight: 700,
                '& .MuiListItemIcon-root': { color: 'primary.main' },
                '& .MuiListItemText-primary': { fontWeight: 700 },
              },
              '&:hover': {
                backgroundColor: (t) =>
                  t.palette.mode === 'light'
                    ? 'rgba(145, 158, 171, 0.08)'
                    : 'rgba(145, 158, 171, 0.16)',
              },
            }}
          >
            <ListItemIcon>{item.icon}</ListItemIcon>
            <ListItemText primary={item.label} primaryTypographyProps={{ fontSize: '0.9rem' }} />
            <Box
              className="active-dot"
              sx={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                backgroundColor: 'primary.main',
                opacity: 0,
                transition: 'opacity 0.15s',
                '.active &': { opacity: 1 },
              }}
            />
          </ListItemButton>
        ))}
      </List>
    </Drawer>
  );
}

export const SIDEBAR_WIDTH = NAV_WIDTH;
