import {
  Alert,
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
  MenuItem,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/RefreshOutlined';
import CloseIcon from '@mui/icons-material/CloseOutlined';
import ReplayIcon from '@mui/icons-material/ReplayOutlined';
import CancelIcon from '@mui/icons-material/CancelOutlined';
import { useEffect, useMemo, useState } from 'react';
import { ApiHttpError } from '../api/client';
import { queueApi } from '../api/endpoints';
import { StatusChip } from '../components/StatusChip';
import { useToken } from '../hooks/useToken';
import type { QueueItem, QueueStatus } from '../types/api';

const STATUSES: (QueueStatus | 'all')[] = ['all', 'queued', 'processing', 'filed', 'needs_review', 'failed'];

export function QueuePage(): JSX.Element {
  const { hasToken } = useToken();
  const [items, setItems] = useState<QueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<QueueStatus | 'all'>('all');
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const params = filter === 'all' ? undefined : { status: filter };
      const resp = await queueApi.list(params);
      setItems(resp.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load queue');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter]);

  const selected = useMemo(
    () => items.find((i) => i.id === selectedId) ?? null,
    [items, selectedId],
  );

  const handleRetry = async (id: number) => {
    setActionMessage(null);
    try {
      await queueApi.retry(id);
      setActionMessage(`Item #${id} re-queued.`);
    } catch (e) {
      // 409 commonly means the row's status changed since the page was last
      // loaded (e.g. the worker filed it after the user opened the queue).
      // Reload either way so the badge re-syncs with the backend's truth.
      setActionMessage(e instanceof ApiHttpError ? e.message : 'Retry failed');
    } finally {
      void load();
    }
  };

  const handleCancel = async (id: number) => {
    setActionMessage(null);
    try {
      await queueApi.cancel(id);
      setActionMessage(`Item #${id} cancelled.`);
    } catch (e) {
      setActionMessage(e instanceof ApiHttpError ? e.message : 'Cancel failed');
    } finally {
      void load();
    }
  };

  return (
    <Stack spacing={3}>
      <Card>
        <CardHeader
          title="Queue"
          subheader="Captures moving through the worker. Newest first."
          action={
            <Stack direction="row" spacing={1}>
              <TextField
                select
                size="small"
                label="Status"
                value={filter}
                onChange={(e) => setFilter(e.target.value as QueueStatus | 'all')}
                sx={{ minWidth: 160 }}
              >
                {STATUSES.map((s) => (
                  <MenuItem key={s} value={s}>
                    {s === 'all' ? 'All statuses' : s}
                  </MenuItem>
                ))}
              </TextField>
              <Tooltip title="Refresh">
                <IconButton onClick={() => void load()} aria-label="refresh queue">
                  <RefreshIcon />
                </IconButton>
              </Tooltip>
            </Stack>
          }
        />
        <CardContent sx={{ pt: 0 }}>
          {actionMessage && (
            <Alert severity="info" onClose={() => setActionMessage(null)} sx={{ mb: 2 }}>
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
              No items match the current filter.
            </Typography>
          ) : (
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>ID</TableCell>
                    <TableCell>Source</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Submitter</TableCell>
                    <TableCell>Created</TableCell>
                    <TableCell>Confidence</TableCell>
                    <TableCell align="right">Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {items.map((item) => (
                    <TableRow
                      hover
                      key={item.id}
                      onClick={() => setSelectedId(item.id)}
                      sx={{ cursor: 'pointer' }}
                    >
                      <TableCell>#{item.id}</TableCell>
                      <TableCell>
                        <Chip size="small" label={item.source_type} variant="outlined" />
                      </TableCell>
                      <TableCell>
                        <StatusChip status={item.status} />
                      </TableCell>
                      <TableCell>
                        <Typography variant="caption">{item.submitter}</Typography>
                      </TableCell>
                      <TableCell>{item.created_at.replace('T', ' ').replace('Z', '')}</TableCell>
                      <TableCell>{item.confidence?.toFixed(2) ?? '—'}</TableCell>
                      <TableCell align="right" onClick={(e) => e.stopPropagation()}>
                        <Stack direction="row" spacing={0.5} justifyContent="flex-end">
                          <Tooltip
                            title={
                              hasToken
                                ? 'Re-queue this item'
                                : 'Set bearer token in Settings to retry'
                            }
                          >
                            <span>
                              <IconButton
                                size="small"
                                disabled={
                                  !hasToken ||
                                  !(item.status === 'failed' || item.status === 'needs_review')
                                }
                                onClick={() => void handleRetry(item.id)}
                                aria-label={`retry item ${item.id}`}
                              >
                                <ReplayIcon fontSize="small" />
                              </IconButton>
                            </span>
                          </Tooltip>
                          <Tooltip
                            title={
                              hasToken
                                ? 'Cancel this item'
                                : 'Set bearer token in Settings to cancel'
                            }
                          >
                            <span>
                              <IconButton
                                size="small"
                                disabled={
                                  !hasToken ||
                                  !(item.status === 'queued' || item.status === 'needs_review')
                                }
                                onClick={() => void handleCancel(item.id)}
                                aria-label={`cancel item ${item.id}`}
                              >
                                <CancelIcon fontSize="small" />
                              </IconButton>
                            </span>
                          </Tooltip>
                        </Stack>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </CardContent>
      </Card>

      <Drawer
        anchor="right"
        open={!!selected}
        onClose={() => setSelectedId(null)}
        PaperProps={{ sx: { width: { xs: '100%', sm: 480 }, p: 0 } }}
      >
        {selected && (
          <Box sx={{ p: 3 }}>
            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
              <Typography variant="h6">Queue item #{selected.id}</Typography>
              <IconButton onClick={() => setSelectedId(null)} aria-label="close detail">
                <CloseIcon />
              </IconButton>
            </Stack>
            <StatusChip status={selected.status} />
            <Divider sx={{ my: 2 }} />
            <Stack spacing={1.5}>
              <Detail label="Source type" value={selected.source_type} />
              <Detail label="Submitter" value={selected.submitter} />
              <Detail label="Created" value={selected.created_at} />
              <Detail label="Updated" value={selected.updated_at} />
              {selected.processed_at && (
                <Detail label="Processed" value={selected.processed_at} />
              )}
              <Detail label="Attempts" value={String(selected.attempts)} />
              {selected.confidence != null && (
                <Detail label="Confidence" value={selected.confidence.toFixed(2)} />
              )}
              {selected.vault_path && (
                <Detail label="Vault path" value={selected.vault_path} />
              )}
              {selected.last_error && (
                <Box>
                  <Typography variant="subtitle2">Last error</Typography>
                  <Typography
                    variant="caption"
                    component="pre"
                    sx={{
                      whiteSpace: 'pre-wrap',
                      fontFamily: 'monospace',
                      backgroundColor: (t) => t.palette.background.default,
                      p: 1.5,
                      borderRadius: 1,
                    }}
                  >
                    {selected.last_error}
                  </Typography>
                </Box>
              )}
              <Box>
                <Typography variant="subtitle2">Source payload</Typography>
                <Typography
                  component="pre"
                  variant="caption"
                  sx={{
                    whiteSpace: 'pre-wrap',
                    fontFamily: 'monospace',
                    backgroundColor: (t) => t.palette.background.default,
                    p: 1.5,
                    borderRadius: 1,
                  }}
                >
                  {JSON.stringify(selected.source_payload, null, 2)}
                </Typography>
              </Box>
              {selected.claude_session_id && (
                <Box>
                  <Typography variant="subtitle2">Claude telemetry</Typography>
                  <Typography variant="caption" component="div">
                    session: {selected.claude_session_id}
                  </Typography>
                  <Typography variant="caption" component="div">
                    tokens in/out: {selected.claude_input_tokens ?? '—'} / {selected.claude_output_tokens ?? '—'}
                  </Typography>
                  <Typography variant="caption" component="div">
                    duration: {selected.claude_duration_ms ?? '—'} ms
                  </Typography>
                </Box>
              )}
            </Stack>
            <Divider sx={{ my: 2 }} />
            <Stack direction="row" spacing={1}>
              {(selected.status === 'failed' || selected.status === 'needs_review') && (
                <Button
                  startIcon={<ReplayIcon />}
                  variant="contained"
                  disabled={!hasToken}
                  onClick={() => void handleRetry(selected.id)}
                >
                  Retry
                </Button>
              )}
              {(selected.status === 'queued' || selected.status === 'needs_review') && (
                <Button
                  startIcon={<CancelIcon />}
                  variant="outlined"
                  color="error"
                  disabled={!hasToken}
                  onClick={() => void handleCancel(selected.id)}
                >
                  Cancel
                </Button>
              )}
            </Stack>
          </Box>
        )}
      </Drawer>
    </Stack>
  );
}

function Detail({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="body2">{value}</Typography>
    </Box>
  );
}
