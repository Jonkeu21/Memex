import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  Checkbox,
  CircularProgress,
  Divider,
  FormControlLabel,
  IconButton,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import AddIcon from '@mui/icons-material/AddOutlined';
import DeleteIcon from '@mui/icons-material/DeleteOutlineOutlined';
import ArrowUpIcon from '@mui/icons-material/ArrowUpwardOutlined';
import ArrowDownIcon from '@mui/icons-material/ArrowDownwardOutlined';
import { useEffect, useState } from 'react';
import { ApiHttpError } from '../api/client';
import { taxonomyApi } from '../api/endpoints';
import { useToken } from '../hooks/useToken';
import type { TaxonomyDocument, TaxonomyFolder } from '../types/api';

const blankFolder = (): TaxonomyFolder => ({
  path: '',
  description: '',
  keywords: [],
  confidence_override: null,
});

export function TaxonomyPage(): JSX.Element {
  const { hasToken } = useToken();
  const [doc, setDoc] = useState<TaxonomyDocument | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    void taxonomyApi
      .get()
      .then((r) => setDoc(r.document))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'Failed to load'))
      .finally(() => setLoading(false));
  }, []);

  if (loading || !doc) {
    return (
      <Stack alignItems="center" sx={{ py: 6 }}>
        <CircularProgress size={28} />
      </Stack>
    );
  }

  const updateFolder = (i: number, patch: Partial<TaxonomyFolder>) => {
    const folders = [...doc.folders];
    folders[i] = { ...folders[i], ...patch };
    setDoc({ ...doc, folders });
  };

  const moveFolder = (i: number, dir: -1 | 1) => {
    const j = i + dir;
    if (j < 0 || j >= doc.folders.length) return;
    const folders = [...doc.folders];
    [folders[i], folders[j]] = [folders[j], folders[i]];
    setDoc({ ...doc, folders });
  };

  const removeFolder = (i: number) => {
    const folders = doc.folders.filter((_, idx) => idx !== i);
    setDoc({ ...doc, folders });
  };

  const addFolder = () => setDoc({ ...doc, folders: [...doc.folders, blankFolder()] });

  const handleSave = async () => {
    setError(null);
    setSuccess(null);
    setSaving(true);
    try {
      const res = await taxonomyApi.put(doc);
      setDoc(res.document);
      setSuccess('Saved. The worker reloads on its next batch tick.');
    } catch (e) {
      setError(e instanceof ApiHttpError ? e.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Stack spacing={3}>
      <Card>
        <CardHeader
          title="Taxonomy"
          subheader={`Edits to vault/_meta/taxonomy.yml. The worker reloads on every batch tick.`}
        />
        <CardContent sx={{ pt: 0 }}>
          {error && (
            <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
              {error}
            </Alert>
          )}
          {success && (
            <Alert severity="success" sx={{ mb: 2 }} onClose={() => setSuccess(null)}>
              {success}
            </Alert>
          )}
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField
              label="Default route"
              value={doc.default_route}
              onChange={(e) => setDoc({ ...doc, default_route: e.target.value })}
              sx={{ minWidth: 200 }}
            />
            <TextField
              type="number"
              label="Autonomous threshold"
              value={doc.confidence.autonomous_threshold}
              inputProps={{ step: 0.05, min: 0, max: 1 }}
              onChange={(e) =>
                setDoc({
                  ...doc,
                  confidence: { ...doc.confidence, autonomous_threshold: Number(e.target.value) },
                })
              }
              sx={{ minWidth: 200 }}
            />
            <TextField
              type="number"
              label="Review threshold"
              value={doc.confidence.review_threshold}
              inputProps={{ step: 0.05, min: 0, max: 1 }}
              onChange={(e) =>
                setDoc({
                  ...doc,
                  confidence: { ...doc.confidence, review_threshold: Number(e.target.value) },
                })
              }
              sx={{ minWidth: 200 }}
            />
          </Stack>
        </CardContent>
      </Card>

      <Card>
        <CardHeader
          title="Folders"
          action={
            <Button variant="outlined" startIcon={<AddIcon />} onClick={addFolder}>
              Add folder
            </Button>
          }
        />
        <CardContent sx={{ pt: 0 }}>
          {doc.folders.length === 0 && (
            <Typography color="text.secondary" sx={{ py: 4, textAlign: 'center' }}>
              No folders. Add one to start filing.
            </Typography>
          )}
          <Stack spacing={2}>
            {doc.folders.map((folder, i) => (
              <Box
                key={i}
                sx={{
                  borderRadius: 2,
                  border: (t) => `1px solid ${t.palette.divider}`,
                  p: 2,
                }}
              >
                <Stack direction="row" spacing={1} alignItems="center">
                  <TextField
                    size="small"
                    label="Path"
                    value={folder.path}
                    placeholder="resources/ml-papers"
                    onChange={(e) => updateFolder(i, { path: e.target.value })}
                    sx={{ flexGrow: 1 }}
                  />
                  <Tooltip title="Move up">
                    <IconButton onClick={() => moveFolder(i, -1)} aria-label="move up">
                      <ArrowUpIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Move down">
                    <IconButton onClick={() => moveFolder(i, 1)} aria-label="move down">
                      <ArrowDownIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Remove folder">
                    <IconButton onClick={() => removeFolder(i)} aria-label="remove folder" color="error">
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Stack>
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ mt: 1 }}>
                  <TextField
                    size="small"
                    label="Description"
                    value={folder.description}
                    onChange={(e) => updateFolder(i, { description: e.target.value })}
                    sx={{ flexGrow: 1 }}
                  />
                  <TextField
                    size="small"
                    label="Keywords (comma-separated)"
                    value={folder.keywords.join(', ')}
                    onChange={(e) =>
                      updateFolder(i, {
                        keywords: e.target.value
                          .split(',')
                          .map((s) => s.trim())
                          .filter(Boolean),
                      })
                    }
                    sx={{ flexGrow: 1 }}
                  />
                </Stack>
                <FormControlLabel
                  sx={{ mt: 1 }}
                  control={
                    <Checkbox
                      checked={!!folder.confidence_override}
                      onChange={(_, checked) =>
                        updateFolder(i, {
                          confidence_override: checked
                            ? {
                                autonomous_threshold: doc.confidence.autonomous_threshold,
                                review_threshold: doc.confidence.review_threshold,
                              }
                            : null,
                        })
                      }
                    />
                  }
                  label="Override thresholds for this folder"
                />
                {folder.confidence_override && (
                  <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                    <TextField
                      type="number"
                      size="small"
                      label="Override autonomous"
                      value={folder.confidence_override.autonomous_threshold ?? ''}
                      inputProps={{ step: 0.05 }}
                      onChange={(e) =>
                        updateFolder(i, {
                          confidence_override: {
                            ...(folder.confidence_override ?? {
                              autonomous_threshold: null,
                              review_threshold: null,
                            }),
                            autonomous_threshold: Number(e.target.value),
                          },
                        })
                      }
                    />
                    <TextField
                      type="number"
                      size="small"
                      label="Override review"
                      value={folder.confidence_override.review_threshold ?? ''}
                      inputProps={{ step: 0.05 }}
                      onChange={(e) =>
                        updateFolder(i, {
                          confidence_override: {
                            ...(folder.confidence_override ?? {
                              autonomous_threshold: null,
                              review_threshold: null,
                            }),
                            review_threshold: Number(e.target.value),
                          },
                        })
                      }
                    />
                  </Stack>
                )}
              </Box>
            ))}
          </Stack>
          <Divider sx={{ my: 2 }} />
          <Stack direction="row" spacing={1} alignItems="center">
            <Tooltip title={hasToken ? '' : 'Set bearer token in Settings to save'}>
              <span>
                <Button
                  variant="contained"
                  disabled={!hasToken || saving}
                  onClick={() => void handleSave()}
                >
                  {saving ? 'Saving…' : 'Save taxonomy'}
                </Button>
              </span>
            </Tooltip>
            <Typography variant="caption" color="text.secondary">
              The worker re-reads taxonomy.yml on every poll tick (5–60 s).
            </Typography>
          </Stack>
        </CardContent>
      </Card>
    </Stack>
  );
}
