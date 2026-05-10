import {
  Alert,
  Box,
  Card,
  CardContent,
  CardHeader,
  Chip,
  CircularProgress,
  Divider,
  Drawer,
  IconButton,
  InputAdornment,
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
import SearchIcon from '@mui/icons-material/SearchOutlined';
import OpenInNewIcon from '@mui/icons-material/OpenInNewOutlined';
import CloseIcon from '@mui/icons-material/CloseOutlined';
import { useEffect, useMemo, useState } from 'react';
import { capturesApi } from '../api/endpoints';
import { MarkdownViewer } from '../components/MarkdownViewer';
import type { CaptureFile, CaptureFileBody } from '../types/api';

const FOLDERS = ['', 'projects', 'areas', 'resources', 'archive', '_inbox'];

export function CapturesPage(): JSX.Element {
  const [items, setItems] = useState<CaptureFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [folder, setFolder] = useState<string>('');
  const [q, setQ] = useState<string>('');
  const [needsReview, setNeedsReview] = useState<'all' | 'true' | 'false'>('all');
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<CaptureFileBody | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, string | boolean | undefined> = {};
      if (folder) params.folder = folder;
      if (q.trim()) params.q = q.trim();
      if (needsReview === 'true') params.needs_review = true;
      if (needsReview === 'false') params.needs_review = false;
      const resp = await capturesApi.list(params as never);
      setItems(resp.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load captures');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [folder, needsReview]);

  useEffect(() => {
    if (!selectedPath) {
      setSelectedFile(null);
      return;
    }
    setSelectedFile(null);
    capturesApi.get(selectedPath).then(setSelectedFile).catch(() => setSelectedFile(null));
  }, [selectedPath]);

  const handleSearchKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') void load();
  };

  return (
    <Stack spacing={3}>
      <Card>
        <CardHeader
          title="Captures"
          subheader="Browse the vault. Click any row for the markdown viewer."
        />
        <CardContent sx={{ pt: 0 }}>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} sx={{ mb: 2 }}>
            <TextField
              size="small"
              placeholder="Search titles & paths…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={handleSearchKey}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon fontSize="small" />
                  </InputAdornment>
                ),
              }}
              sx={{ flexGrow: 1 }}
            />
            <TextField
              size="small"
              select
              label="Folder"
              value={folder}
              onChange={(e) => setFolder(e.target.value)}
              sx={{ minWidth: 180 }}
            >
              {FOLDERS.map((f) => (
                <MenuItem key={f || 'all'} value={f}>
                  {f || 'All folders'}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              size="small"
              select
              label="Needs review"
              value={needsReview}
              onChange={(e) => setNeedsReview(e.target.value as never)}
              sx={{ minWidth: 160 }}
            >
              <MenuItem value="all">All</MenuItem>
              <MenuItem value="true">Yes</MenuItem>
              <MenuItem value="false">No</MenuItem>
            </TextField>
          </Stack>
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
              No captures match.
            </Typography>
          ) : (
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Title</TableCell>
                    <TableCell>Folder</TableCell>
                    <TableCell>Tags</TableCell>
                    <TableCell>Captured</TableCell>
                    <TableCell>Needs review</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {items.map((row) => (
                    <TableRow
                      hover
                      key={row.path}
                      onClick={() => setSelectedPath(row.path)}
                      sx={{ cursor: 'pointer' }}
                    >
                      <TableCell>
                        <Typography variant="subtitle2">{row.title}</Typography>
                        <Typography variant="caption" color="text.secondary">
                          {row.path}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Chip size="small" label={row.folder} variant="outlined" />
                      </TableCell>
                      <TableCell>
                        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                          {row.tags.slice(0, 3).map((t) => (
                            <Chip key={t} size="small" label={t} />
                          ))}
                          {row.tags.length > 3 && <Chip size="small" label={`+${row.tags.length - 3}`} />}
                        </Stack>
                      </TableCell>
                      <TableCell>{row.captured_at?.slice(0, 10) ?? '—'}</TableCell>
                      <TableCell>
                        {row.needs_review ? (
                          <Chip size="small" color="warning" label="yes" />
                        ) : (
                          <Chip size="small" color="success" variant="outlined" label="no" />
                        )}
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
              <Stack direction="row">
                <Tooltip title="Open in Obsidian">
                  <IconButton
                    href={`obsidian://open?path=${encodeURIComponent(selectedPath)}`}
                    target="_blank"
                    rel="noopener"
                    aria-label="open in obsidian"
                  >
                    <OpenInNewIcon />
                  </IconButton>
                </Tooltip>
                <IconButton onClick={() => setSelectedPath(null)} aria-label="close">
                  <CloseIcon />
                </IconButton>
              </Stack>
            </Stack>
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
          </Box>
        )}
      </Drawer>
    </Stack>
  );
}
