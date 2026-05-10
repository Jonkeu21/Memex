import { Box } from '@mui/material';
import { lazy, Suspense } from 'react';

// Lazy-load react-markdown so it doesn't bloat the initial paint.
const ReactMarkdown = lazy(() => import('react-markdown'));
const remarkGfmModule = () => import('remark-gfm');

interface MarkdownViewerProps {
  body: string;
}

export function MarkdownViewer({ body }: MarkdownViewerProps): JSX.Element {
  return (
    <Box
      sx={{
        '& h1, & h2, & h3, & h4': { mt: 3, mb: 1, fontWeight: 700 },
        '& h1': { fontSize: '1.5rem' },
        '& h2': { fontSize: '1.25rem' },
        '& h3': { fontSize: '1.125rem' },
        '& p': { mb: 1.5, lineHeight: 1.6 },
        '& code': {
          backgroundColor: (t) =>
            t.palette.mode === 'light' ? '#F4F6F8' : 'rgba(255,255,255,0.06)',
          padding: '2px 6px',
          borderRadius: 1,
          fontSize: '0.85em',
        },
        '& pre': {
          backgroundColor: (t) =>
            t.palette.mode === 'light' ? '#F4F6F8' : 'rgba(255,255,255,0.06)',
          padding: 2,
          borderRadius: 2,
          overflowX: 'auto',
          fontSize: '0.85em',
        },
        '& pre code': { background: 'none', padding: 0 },
        '& blockquote': {
          borderLeft: (t) => `4px solid ${t.palette.primary.main}`,
          ml: 0,
          pl: 2,
          color: 'text.secondary',
        },
        '& a': { color: 'primary.dark', textDecoration: 'underline' },
        '& ul, & ol': { pl: 3, mb: 1.5 },
      }}
    >
      <Suspense fallback={<Box sx={{ color: 'text.secondary' }}>Loading…</Box>}>
        <DeferredMarkdown body={body} />
      </Suspense>
    </Box>
  );
}

function DeferredMarkdown({ body }: { body: string }): JSX.Element {
  // Resolve remark-gfm lazily too so it stays in the same chunk.
  const PluginThunk = lazy(async () => {
    const gfm = (await remarkGfmModule()).default;
    return {
      default: ({ children }: { children: string }) => (
        <ReactMarkdown remarkPlugins={[gfm]}>{children}</ReactMarkdown>
      ),
    };
  });
  return (
    <Suspense fallback={<Box sx={{ color: 'text.secondary' }}>Loading…</Box>}>
      <PluginThunk>{body}</PluginThunk>
    </Suspense>
  );
}
