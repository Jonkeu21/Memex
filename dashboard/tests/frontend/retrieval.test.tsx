import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ThemeProvider } from '@mui/material/styles';
import { CssBaseline } from '@mui/material';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { buildTheme } from '../../frontend/src/theme';
import { RetrievalPage } from '../../frontend/src/pages/Retrieval';
import { tokenStorage } from '../../frontend/src/api/client';

const theme = buildTheme('light');

const renderRetrieval = () =>
  render(
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <MemoryRouter>
        <Routes>
          <Route path="*" element={<RetrievalPage />} />
        </Routes>
      </MemoryRouter>
    </ThemeProvider>,
  );

describe('Retrieval page', () => {
  beforeEach(() => {
    tokenStorage.set('test-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it('disables Ask when there is no token', async () => {
    tokenStorage.set('');
    global.fetch = vi.fn(async () =>
      new Response(
        JSON.stringify({
          available: true,
          total_24h: 0,
          error_rate_5m: 0,
          last_call_ts: null,
          by_hour: [],
          recent_calls: [],
          services_breakdown_24h: {},
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    ) as unknown as typeof global.fetch;
    renderRetrieval();
    const button = await screen.findByRole('button', { name: /ask/i });
    expect(button).toBeDisabled();
  });

  it('runs the input → loading → answer flow', async () => {
    let resolveQuery!: () => void;
    const queryDone = new Promise<void>((res) => {
      resolveQuery = res;
    });
    global.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString();
      if (url.includes('/api/v1/rate-limit')) {
        return new Response(
          JSON.stringify({
            available: true,
            total_24h: 0,
            error_rate_5m: 0,
            last_call_ts: null,
            by_hour: [],
            recent_calls: [],
            services_breakdown_24h: {},
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      if (url.includes('/api/v1/retrieval') && init?.method === 'POST') {
        await queryDone;
        return new Response(
          JSON.stringify({
            answer: 'The vault has notes on RoPE scaling.',
            sources: [
              { path: 'resources/ml-papers/rope.md', title: 'RoPE', exists: true },
            ],
            quotes: [
              { source_index: 0, text: 'Position interpolation degrades smoothly past 4× context.' },
            ],
            confidence: 0.74,
            duration_ms: 1234,
            session_id: 'sess',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      return new Response('{}', { status: 404 });
    }) as unknown as typeof global.fetch;

    renderRetrieval();
    const input = await screen.findByLabelText('retrieval question');
    await userEvent.type(input, 'How does RoPE scale?');
    const askButton = screen.getByRole('button', { name: /ask/i });
    await userEvent.click(askButton);

    // Loading skeleton appears.
    await waitFor(() =>
      expect(screen.getByTestId('retrieval-loading')).toBeInTheDocument(),
    );

    // Resolve the query and the answer card renders.
    resolveQuery();
    const turn = await screen.findByTestId('retrieval-turn');
    await waitFor(() =>
      expect(within(turn).getByTestId('retrieval-answer')).toBeInTheDocument(),
    );
    expect(within(turn).getByTestId('retrieval-sources')).toBeInTheDocument();
    expect(within(turn).getByTestId('retrieval-quotes')).toBeInTheDocument();
    expect(within(turn).getByText(/filed at 0\.74 confidence/)).toBeInTheDocument();
  });
});
