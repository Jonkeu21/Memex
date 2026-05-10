import { CssBaseline, ThemeProvider } from '@mui/material';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useMemo } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AppShell } from './components/Layout/AppShell';
import { useThemeMode } from './hooks/useThemeMode';
import { CapturesPage } from './pages/Captures';
import { InboxPage } from './pages/Inbox';
import { QueuePage } from './pages/Queue';
import { RateLimitPage } from './pages/RateLimit';
import { RetrievalPage } from './pages/Retrieval';
import { TaxonomyPage } from './pages/Taxonomy';
import { buildTheme } from './theme';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      refetchOnWindowFocus: false,
    },
  },
});

export function App(): JSX.Element {
  const { mode, density } = useThemeMode();
  const theme = useMemo(() => buildTheme(mode, density), [mode, density]);

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Routes>
            <Route element={<AppShell />}>
              <Route index element={<Navigate to="/queue" replace />} />
              <Route path="/queue" element={<QueuePage />} />
              <Route path="/inbox" element={<InboxPage />} />
              <Route path="/taxonomy" element={<TaxonomyPage />} />
              <Route path="/captures" element={<CapturesPage />} />
              <Route path="/rate-limit" element={<RateLimitPage />} />
              <Route path="/retrieval" element={<RetrievalPage />} />
              <Route path="*" element={<Navigate to="/queue" replace />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
