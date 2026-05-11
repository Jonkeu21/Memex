import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  Chip,
  Divider,
  Drawer,
  IconButton,
  Skeleton,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import SendIcon from '@mui/icons-material/SendOutlined';
import OpenInNewIcon from '@mui/icons-material/OpenInNewOutlined';
import CloseIcon from '@mui/icons-material/CloseOutlined';
import RefreshIcon from '@mui/icons-material/RefreshOutlined';
import { useEffect, useRef, useState } from 'react';
import { ApiHttpError } from '../api/client';
import { capturesApi, rateLimitApi, retrievalApi } from '../api/endpoints';
import { MarkdownViewer } from '../components/MarkdownViewer';
import { useToken } from '../hooks/useToken';
import type { CaptureFileBody, RetrievalResponse } from '../types/api';

interface ChatTurn {
  id: number;
  question: string;
  loading: boolean;
  response: RetrievalResponse | null;
  errorMessage: string | null;
}

export function RetrievalPage(): JSX.Element {
  const { hasToken } = useToken();
  const [draft, setDraft] = useState('');
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [recentRateLimitHit, setRecentRateLimitHit] = useState<boolean>(false);
  const [selectedSourcePath, setSelectedSourcePath] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<CaptureFileBody | null>(null);
  const idRef = useRef(0);

  useEffect(() => {
    rateLimitApi
      .snapshot()
      .then((s) => {
        if (s.available && s.error_rate_5m > 0) setRecentRateLimitHit(true);
      })
      .catch(() => {
        /* non-blocking */
      });
  }, []);

  useEffect(() => {
    if (!selectedSourcePath) {
      setSelectedFile(null);
      return;
    }
    setSelectedFile(null);
    capturesApi.get(selectedSourcePath).then(setSelectedFile).catch(() => setSelectedFile(null));
  }, [selectedSourcePath]);

  const send = async (question?: string) => {
    const q = (question ?? draft).trim();
    if (!q) return;
    if (!hasToken) return;
    setDraft('');
    const id = ++idRef.current;
    setTurns((t) => [...t, { id, question: q, loading: true, response: null, errorMessage: null }]);
    try {
      const resp = await retrievalApi.ask(q);
      setTurns((ts) =>
        ts.map((t) => (t.id === id ? { ...t, loading: false, response: resp } : t)),
      );
    } catch (e) {
      setTurns((ts) =>
        ts.map((t) =>
          t.id === id
            ? { ...t, loading: false, errorMessage: e instanceof ApiHttpError ? e.message : 'Request failed' }
            : t,
        ),
      );
    }
  };

  const retry = (turnId: number) => {
    const turn = turns.find((t) => t.id === turnId);
    if (!turn) return;
    setTurns((ts) => ts.filter((t) => t.id !== turnId));
    void send(turn.question);
  };

  return (
    <Stack spacing={3}>
      {recentRateLimitHit && (
        <Alert severity="warning" sx={{ borderRadius: 2 }}>
          A recent <code>claude -p</code> call exited with a non-zero code (rate-limit
          or transient error). New retrievals may be slow or fail until things recover.
        </Alert>
      )}
      <Card>
        <CardHeader
          title="Retrieval chat"
          subheader="Ask the vault. Answers cite source notes verbatim."
        />
        <CardContent>
          <Stack spacing={3}>
            {turns.length === 0 ? (
              <Typography color="text.secondary" sx={{ py: 6, textAlign: 'center' }}>
                Ask a question — the assistant will read your vault and reply with sources.
              </Typography>
            ) : (
              turns.map((turn) => (
                <ChatBubble
                  key={turn.id}
                  turn={turn}
                  onRetry={() => retry(turn.id)}
                  onOpenSource={(path) => setSelectedSourcePath(path)}
                />
              ))
            )}
          </Stack>
          <Divider sx={{ my: 3 }} />
          <Stack direction="row" spacing={1.5} alignItems="flex-end">
            <TextField
              multiline
              maxRows={4}
              fullWidth
              size="small"
              placeholder={
                hasToken
                  ? 'What did I say about RoPE scaling?'
                  : 'Set the bearer token in Settings to send retrieval requests.'
              }
              value={draft}
              disabled={!hasToken}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault();
                  void send();
                }
              }}
              inputProps={{ 'aria-label': 'retrieval question' }}
              sx={{ '& .MuiOutlinedInput-root': { minHeight: 44 } }}
            />
            <Tooltip title={hasToken ? 'Send (⌘/Ctrl + Enter)' : 'Set bearer token in Settings'}>
              <span>
                <Button
                  variant="contained"
                  endIcon={<SendIcon />}
                  disabled={!hasToken || !draft.trim()}
                  onClick={() => void send()}
                  size="large"
                  sx={{ height: 44, flexShrink: 0 }}
                >
                  Ask
                </Button>
              </span>
            </Tooltip>
          </Stack>
        </CardContent>
      </Card>

      <Drawer
        anchor="right"
        open={!!selectedSourcePath}
        onClose={() => setSelectedSourcePath(null)}
        PaperProps={{ sx: { width: { xs: '100%', md: 720 } } }}
      >
        {selectedSourcePath && (
          <Box sx={{ p: 3, height: '100%', display: 'flex', flexDirection: 'column' }}>
            <Stack direction="row" justifyContent="space-between" alignItems="center">
              <Typography variant="h6" sx={{ wordBreak: 'break-word' }}>
                {selectedSourcePath}
              </Typography>
              <Stack direction="row">
                <Tooltip title="Open in Obsidian">
                  <IconButton
                    href={`obsidian://open?path=${encodeURIComponent(selectedSourcePath)}`}
                    target="_blank"
                    rel="noopener"
                    aria-label="open in obsidian"
                  >
                    <OpenInNewIcon />
                  </IconButton>
                </Tooltip>
                <IconButton onClick={() => setSelectedSourcePath(null)} aria-label="close">
                  <CloseIcon />
                </IconButton>
              </Stack>
            </Stack>
            <Divider sx={{ my: 2 }} />
            <Box sx={{ flexGrow: 1, overflowY: 'auto', pr: 1 }}>
              {selectedFile ? (
                <MarkdownViewer body={selectedFile.body} />
              ) : (
                <Skeleton variant="rectangular" height={200} />
              )}
            </Box>
          </Box>
        )}
      </Drawer>
    </Stack>
  );
}

interface ChatBubbleProps {
  turn: ChatTurn;
  onRetry: () => void;
  onOpenSource: (path: string) => void;
}

function ChatBubble({ turn, onRetry, onOpenSource }: ChatBubbleProps): JSX.Element {
  return (
    <Box
      data-testid="retrieval-turn"
      sx={{
        borderRadius: 2,
        backgroundColor: (t) => t.palette.background.paper,
        p: 3,
        boxShadow: (t) => t.shadows[2],
      }}
    >
      <Typography variant="subtitle2" color="text.secondary">
        Question
      </Typography>
      <Typography variant="subtitle1" sx={{ mb: 2 }}>
        {turn.question}
      </Typography>
      <Divider sx={{ my: 2 }} />
      {turn.loading ? (
        <Stack spacing={1.5} data-testid="retrieval-loading">
          <Skeleton variant="text" width="80%" height={24} />
          <Skeleton variant="text" width="95%" height={24} />
          <Skeleton variant="text" width="70%" height={24} />
        </Stack>
      ) : turn.errorMessage ? (
        <Stack direction="row" spacing={1} alignItems="center">
          <Alert severity="error" sx={{ flexGrow: 1 }}>
            {turn.errorMessage}
          </Alert>
          <Tooltip title="Retry">
            <IconButton onClick={onRetry} aria-label="retry retrieval">
              <RefreshIcon />
            </IconButton>
          </Tooltip>
        </Stack>
      ) : turn.response ? (
        <RenderedAnswer response={turn.response} onOpenSource={onOpenSource} />
      ) : null}
    </Box>
  );
}

interface RenderedAnswerProps {
  response: RetrievalResponse;
  onOpenSource: (path: string) => void;
}

function RenderedAnswer({ response, onOpenSource }: RenderedAnswerProps): JSX.Element {
  const { answer, sources, quotes, confidence } = response;
  return (
    <Stack spacing={2}>
      <Box data-testid="retrieval-answer">
        {answer ? (
          <MarkdownViewer body={answer} />
        ) : (
          <Typography color="text.secondary" fontStyle="italic">
            No sources found in vault.
          </Typography>
        )}
      </Box>
      {confidence < 0.5 && (
        <Alert severity="warning" sx={{ borderRadius: 2 }}>
          Low confidence ({(confidence * 100).toFixed(0)}%) — the vault didn't have
          much directly relevant material.
        </Alert>
      )}
      {sources.length > 0 && (
        <Box>
          <Typography variant="subtitle2" gutterBottom>
            Sources
          </Typography>
          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" data-testid="retrieval-sources">
            {sources.map((s, i) => (
              <Stack key={s.path} direction="row" spacing={0.5} alignItems="center">
                <Tooltip title={s.exists ? 'Open in side panel' : 'File not found on disk'}>
                  <Chip
                    icon={<Box sx={{ width: 18, height: 18, fontSize: 12, lineHeight: '18px', textAlign: 'center', fontWeight: 700 }}>{i + 1}</Box>}
                    label={s.title || s.path}
                    color={s.exists ? 'primary' : 'default'}
                    variant={s.exists ? 'outlined' : 'filled'}
                    onClick={() => s.exists && onOpenSource(s.path)}
                    sx={{ cursor: s.exists ? 'pointer' : 'not-allowed' }}
                  />
                </Tooltip>
                <Tooltip title="Open in Obsidian">
                  <IconButton
                    size="small"
                    href={`obsidian://open?path=${encodeURIComponent(s.path)}`}
                    target="_blank"
                    rel="noopener"
                    aria-label={`open ${s.title} in Obsidian`}
                  >
                    <OpenInNewIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              </Stack>
            ))}
          </Stack>
        </Box>
      )}
      {quotes.length > 0 && (
        <Box>
          <Typography variant="subtitle2" gutterBottom>
            Excerpts
          </Typography>
          <Stack spacing={1.5} data-testid="retrieval-quotes">
            {quotes.map((q, i) => (
              <Box
                key={`${q.source_index}-${i}`}
                sx={{
                  borderLeft: (t) => `3px solid ${t.palette.primary.main}`,
                  pl: 2,
                  py: 0.5,
                }}
              >
                <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700 }}>
                  Source {q.source_index + 1}
                  {sources[q.source_index] ? ` · ${sources[q.source_index].title}` : ''}
                </Typography>
                <Typography variant="body2">{q.text}</Typography>
              </Box>
            ))}
          </Stack>
        </Box>
      )}
      <Typography variant="caption" color="text.secondary">
        filed at {confidence.toFixed(2)} confidence
        {response.duration_ms != null && ` · ${response.duration_ms} ms`}
      </Typography>
    </Stack>
  );
}
