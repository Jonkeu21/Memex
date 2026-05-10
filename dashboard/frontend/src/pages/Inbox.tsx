import {
  Alert,
  Avatar,
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  Chip,
  CircularProgress,
  Divider,
  Drawer,
  IconButton,
  List,
  ListItem,
  ListItemAvatar,
  ListItemButton,
  ListItemText,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material';
import ArticleIcon from '@mui/icons-material/ArticleOutlined';
import OpenInNewIcon from '@mui/icons-material/OpenInNewOutlined';
import DeleteIcon from '@mui/icons-material/DeleteOutlineOutlined';
import RefreshIcon from '@mui/icons-material/RefreshOutlined';
import CloseIcon from '@mui/icons-material/CloseOutlined';
import { useEffect, useMemo, useState } from 'react';
import { ApiHttpError } from '../api/client';
import { inboxApi, taxonomyApi } from '../api/endpoints';
import { MarkdownViewer } from '../components/MarkdownViewer';
import { useToken } from '../hooks/useToken';
import type { InboxFile, InboxItem, TaxonomyDocument } from '../types/api';

export function InboxPage(): JSX.Element {
  const { hasToken } = useToken();
  const [items, setItems] = useState<InboxItem[]>([]);
  const [taxonomy, setTaxonomy] = useState<TaxonomyDocument | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<InboxFile | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [list, tax] = await Promise.all([inboxApi.list(), taxonomyApi.get()]);
      setItems(list.items);
      setTaxonomy(tax.document);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load inbox');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    if (!selectedPath) {
      setSelectedFile(null);
      return;
    }
    setSelectedFile(null);
    inboxApi
      .get(selectedPath)
      .then(setSelectedFile)
      .catch((e: unknown) =>
        setActionError(e instanceof Error ? e.message : 'Could not open file'),
      );
  }, [selectedPath]);

  const handleRoute = async (path: string, target: string) => {
    setActionMessage(null);
    setActionError(null);
    try {
      const res = await inboxApi.route(path, target);
      setActionMessage(`Routed to ${res.new_path}`);
      setSelectedPath(null);
      void load();
    } catch (e) {
      setActionError(e instanceof ApiHttpError ? e.message : 'Routing failed');
    }
  };

  const handleTrash = async (path: string) => {
    setActionMessage(null);
    setActionError(null);
    try {
      const res = await inboxApi.trash(path);
      setActionMessage(`Moved to ${res.trashed_path}`);
      setSelectedPath(null);
      void load();
    } catch (e) {
      setActionError(e instanceof ApiHttpError ? e.message : 'Trash failed');
    }
  };

  const folders = taxonomy?.folders ?? [];

  return (
    <Stack spacing={3}>
      <Card>
        <CardHeader
          title="Inbox triage"
          subheader="Captures the worker couldn't file confidently. Review, route, or trash."
          action={
            <Tooltip title="Refresh">
              <IconButton onClick={() => void load()} aria-label="refresh inbox">
                <RefreshIcon />
              </IconButton>
            </Tooltip>
          }
        />
        <CardContent sx={{ pt: 0 }}>
          {actionMessage && (
            <Alert severity="success" onClose={() => setActionMessage(null)} sx={{ mb: 2 }}>
              {actionMessage}
            </Alert>
          )}
          {error && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {error}
            </Alert>
          )}
          {loading ? (
            <Stack alignItems="center" sx={{ py: 6 }}>
              <CircularProgress size={28} />
            </Stack>
          ) : items.length === 0 ? (
            <Typography color="text.secondary" sx={{ py: 6, textAlign: 'center' }}>
              Inbox is clear.
            </Typography>
          ) : (
            <List disablePadding>
              {items.map((item) => (
                <ListItem
                  key={item.path}
                  disablePadding
                  secondaryAction={
                    <Stack direction="row" spacing={2} alignItems="center">
                      {item.confidence != null && (
                        <Chip
                          size="small"
                          label={`conf ${item.confidence.toFixed(2)}`}
                          variant="outlined"
                        />
                      )}
                      {item.suggested_taxonomy && (
                        <Chip
                          size="small"
                          color="primary"
                          variant="outlined"
                          label={item.suggested_taxonomy}
                        />
                      )}
                    </Stack>
                  }
                  sx={{
                    mb: 1,
                    borderRadius: 2,
                    backgroundColor: (t) => t.palette.background.paper,
                    boxShadow: (t) => t.shadows[1],
                    overflow: 'hidden',
                  }}
                >
                  <ListItemButton onClick={() => setSelectedPath(item.path)}>
                    <ListItemAvatar>
                      <Avatar sx={{ bgcolor: 'primary.lighter', color: 'primary.dark' }}>
                        <ArticleIcon />
                      </Avatar>
                    </ListItemAvatar>
                    <ListItemText
                      primary={
                        <Stack direction="row" spacing={1} alignItems="center">
                          <Typography variant="subtitle2">{item.title}</Typography>
                          {item.reason_for_inbox && (
                            <Chip size="small" color="warning" label={item.reason_for_inbox} />
                          )}
                        </Stack>
                      }
                      secondary={
                        <Typography variant="caption" color="text.secondary">
                          {item.path} · captured {item.captured_at?.slice(0, 10) ?? '—'}
                        </Typography>
                      }
                    />
                  </ListItemButton>
                </ListItem>
              ))}
            </List>
          )}
        </CardContent>
      </Card>

      <Drawer
        anchor="right"
        open={!!selectedPath}
        onClose={() => setSelectedPath(null)}
        PaperProps={{ sx: { width: { xs: '100%', md: 720 } } }}
      >
        {selectedPath && (
          <Box sx={{ p: 3, height: '100%', display: 'flex', flexDirection: 'column' }}>
            <Stack direction="row" justifyContent="space-between" alignItems="center">
              <Typography variant="h6" sx={{ wordBreak: 'break-word' }}>
                {selectedPath}
              </Typography>
              <IconButton onClick={() => setSelectedPath(null)} aria-label="close panel">
                <CloseIcon />
              </IconButton>
            </Stack>
            {actionError && (
              <Alert severity="error" sx={{ my: 1 }} onClose={() => setActionError(null)}>
                {actionError}
              </Alert>
            )}
            <Divider sx={{ my: 2 }} />
            <Box sx={{ flexGrow: 1, overflowY: 'auto', pr: 1 }}>
              {selectedFile ? (
                <MarkdownViewer body={selectedFile.body} />
              ) : (
                <Stack alignItems="center" sx={{ py: 4 }}>
                  <CircularProgress size={20} />
                </Stack>
              )}
            </Box>
            <Divider sx={{ mt: 2 }} />
            <Box sx={{ pt: 2 }}>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                Route to taxonomy folder
              </Typography>
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                {folders.length === 0 && (
                  <Typography variant="caption" color="text.secondary">
                    No folders declared in taxonomy.yml — open the Taxonomy page to add some.
                  </Typography>
                )}
                {folders.map((f) => (
                  <Tooltip
                    key={f.path}
                    title={hasToken ? f.description || f.path : 'Set bearer token in Settings'}
                  >
                    <span>
                      <Button
                        size="small"
                        variant="outlined"
                        disabled={!hasToken}
                        onClick={() => void handleRoute(selectedPath, f.path)}
                      >
                        {f.path}
                      </Button>
                    </span>
                  </Tooltip>
                ))}
              </Stack>
              <Stack direction="row" spacing={1} sx={{ mt: 2 }}>
                <Tooltip
                  title={
                    hasToken
                      ? 'Move to _trash/ — does NOT permanently delete'
                      : 'Set bearer token in Settings to delete'
                  }
                >
                  <span>
                    <Button
                      color="error"
                      variant="outlined"
                      startIcon={<DeleteIcon />}
                      disabled={!hasToken}
                      onClick={() => void handleTrash(selectedPath)}
                    >
                      Move to trash
                    </Button>
                  </span>
                </Tooltip>
                <Button
                  variant="outlined"
                  startIcon={<OpenInNewIcon />}
                  href={`obsidian://open?path=${encodeURIComponent(selectedPath)}`}
                  target="_blank"
                  rel="noopener"
                >
                  Open in Obsidian
                </Button>
              </Stack>
              <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
                The trash button moves the file to <code>_trash/&lt;YYYY-MM&gt;/</code>; it does
                not permanently delete.
              </Typography>
            </Box>
          </Box>
        )}
      </Drawer>
    </Stack>
  );
}
