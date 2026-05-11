import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ThemeProvider } from '@mui/material/styles';
import { CssBaseline } from '@mui/material';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { buildTheme } from '../../frontend/src/theme';
import { QueuePage, QUEUE_POLL_INTERVAL_MS } from '../../frontend/src/pages/Queue';
import { InboxPage } from '../../frontend/src/pages/Inbox';
import { TaxonomyPage } from '../../frontend/src/pages/Taxonomy';
import { CapturesPage } from '../../frontend/src/pages/Captures';
import { RateLimitPage } from '../../frontend/src/pages/RateLimit';
import { tokenStorage } from '../../frontend/src/api/client';

const theme = buildTheme('light');

const renderPage = (ui: React.ReactNode, initial = '/') => {
  return render(
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <MemoryRouter initialEntries={[initial]}>
        <Routes>
          <Route path="*" element={ui} />
        </Routes>
      </MemoryRouter>
    </ThemeProvider>,
  );
};

const mockFetch = (responses: Record<string, unknown>) => {
  global.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString();
    for (const [key, payload] of Object.entries(responses)) {
      if (url.includes(key)) {
        return new Response(JSON.stringify(payload), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
    }
    return new Response('{}', { status: 404 });
  }) as unknown as typeof global.fetch;
};

describe('Queue page', () => {
  beforeEach(() => {
    mockFetch({
      '/api/v1/queue': {
        items: [
          {
            id: 1,
            created_at: '2026-05-10T12:00:00.000000Z',
            updated_at: '2026-05-10T12:00:00.000000Z',
            source_type: 'url',
            source_payload: { url: 'https://example.com' },
            submitter: 'api:telegram',
            status: 'failed',
            attempts: 5,
            last_error: 'boom',
            processed_at: '2026-05-10T12:01:00.000000Z',
            confidence: null,
            vault_path: null,
            claude_session_id: null,
            claude_input_tokens: null,
            claude_output_tokens: null,
            claude_duration_ms: null,
          },
        ],
        next_cursor: null,
      },
    });
  });

  it('renders queue items from the API', async () => {
    renderPage(<QueuePage />);
    expect(await screen.findByText('#1')).toBeInTheDocument();
    expect(screen.getByText('Failed')).toBeInTheDocument();
    expect(screen.getByText('api:telegram')).toBeInTheDocument();
  });

  it('disables retry button when no token is set', async () => {
    renderPage(<QueuePage />);
    await screen.findByText('#1');
    const retryButton = screen.getByLabelText('retry item 1');
    expect(retryButton).toBeDisabled();
  });

  it('enables retry when a token is present', async () => {
    tokenStorage.set('test-token');
    renderPage(<QueuePage />);
    await screen.findByText('#1');
    const retryButton = screen.getByLabelText('retry item 1');
    expect(retryButton).not.toBeDisabled();
  });

  it('automatically refetches the queue on a background interval', async () => {
    let callCount = 0;
    global.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString();
      if (url.includes('/api/v1/queue')) {
        callCount += 1;
        const id = callCount === 1 ? 1 : 2;
        const status = callCount === 1 ? 'queued' : 'filed';
        return new Response(
          JSON.stringify({
            items: [
              {
                id,
                created_at: '2026-05-11T12:00:00.000000Z',
                updated_at: '2026-05-11T12:00:00.000000Z',
                source_type: 'url',
                source_payload: { url: 'https://example.com' },
                submitter: 'api:telegram',
                status,
                attempts: 1,
                last_error: null,
                processed_at: null,
                confidence: null,
                vault_path: null,
                claude_session_id: null,
                claude_input_tokens: null,
                claude_output_tokens: null,
                claude_duration_ms: null,
              },
            ],
            next_cursor: null,
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      return new Response('{}', { status: 404 });
    }) as unknown as typeof global.fetch;

    // Only fake setInterval/clearInterval so screen.findBy* and act keep working
    // against the real microtask queue.
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
    try {
      renderPage(<QueuePage />);
      expect(await screen.findByText('#1')).toBeInTheDocument();
      expect(callCount).toBe(1);

      await act(async () => {
        vi.advanceTimersByTime(QUEUE_POLL_INTERVAL_MS + 50);
      });

      await waitFor(() => {
        expect(callCount).toBeGreaterThanOrEqual(2);
      });
      expect(await screen.findByText('#2')).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('Inbox page', () => {
  beforeEach(() => {
    mockFetch({
      '/api/v1/inbox': { items: [] },
      '/api/v1/taxonomy': {
        document: {
          schema_version: 1,
          default_route: '_inbox',
          confidence: { autonomous_threshold: 0.8, review_threshold: 0.6 },
          folders: [],
        },
        raw_yaml: '',
      },
    });
  });

  it('renders empty inbox state', async () => {
    renderPage(<InboxPage />);
    expect(await screen.findByText(/Inbox is clear/)).toBeInTheDocument();
  });
});

describe('Taxonomy page', () => {
  beforeEach(() => {
    mockFetch({
      '/api/v1/taxonomy': {
        document: {
          schema_version: 1,
          default_route: '_inbox',
          confidence: { autonomous_threshold: 0.8, review_threshold: 0.6 },
          folders: [
            {
              path: 'projects/memex',
              description: 'memex',
              keywords: ['memex'],
              confidence_override: null,
            },
          ],
        },
        raw_yaml: '',
      },
    });
  });

  it('renders the loaded taxonomy', async () => {
    renderPage(<TaxonomyPage />);
    expect(await screen.findByDisplayValue('projects/memex')).toBeInTheDocument();
  });

  it('disables save when no token is set', async () => {
    renderPage(<TaxonomyPage />);
    await screen.findByDisplayValue('projects/memex');
    const save = screen.getByRole('button', { name: /save taxonomy/i });
    expect(save).toBeDisabled();
  });

  it('lets the user add a folder', async () => {
    renderPage(<TaxonomyPage />);
    await screen.findByDisplayValue('projects/memex');
    const addBtn = screen.getByRole('button', { name: /add folder/i });
    await userEvent.click(addBtn);
    // After add, there are now two empty path inputs.
    const allPathInputs = screen.getAllByLabelText(/^Path$/);
    expect(allPathInputs.length).toBe(2);
  });
});

describe('Captures page', () => {
  beforeEach(() => {
    mockFetch({
      '/api/v1/captures': {
        items: [
          {
            path: 'projects/memex/2026-05-10--note.md',
            title: 'My note',
            captured_at: '2026-05-10T12:00:00.000000Z',
            processed_at: '2026-05-10T12:01:00.000000Z',
            folder: 'projects/memex',
            tags: ['memex', 'pi'],
            needs_review: false,
            size_bytes: 200,
          },
        ],
        next_cursor: null,
      },
    });
  });

  it('renders capture rows', async () => {
    renderPage(<CapturesPage />);
    expect(await screen.findByText('My note')).toBeInTheDocument();
  });
});

describe('RateLimit page', () => {
  it('renders unavailable state when telemetry table is missing', async () => {
    mockFetch({
      '/api/v1/rate-limit': {
        available: false,
        total_24h: 0,
        error_rate_5m: 0,
        last_call_ts: null,
        by_hour: [],
        recent_calls: [],
        services_breakdown_24h: {},
      },
    });
    renderPage(<RateLimitPage />);
    expect(
      await screen.findByText(/Rate-limit telemetry not yet recorded/),
    ).toBeInTheDocument();
  });

  it('renders the snapshot when telemetry is present', async () => {
    mockFetch({
      '/api/v1/rate-limit': {
        available: true,
        total_24h: 7,
        error_rate_5m: 0,
        last_call_ts: '2026-05-10T12:00:00.000000Z',
        by_hour: [],
        recent_calls: [
          {
            id: 1,
            ts: '2026-05-10T12:00:00.000000Z',
            service: 'worker',
            purpose: 'file',
            queue_item_id: 1,
            session_id: 'sess',
            input_tokens: 100,
            output_tokens: 50,
            duration_ms: 1000,
            exit_code: 0,
          },
        ],
        services_breakdown_24h: { worker: 5, telegram_bot: 2 },
      },
    });
    renderPage(<RateLimitPage />);
    expect(await screen.findByText(/Recent calls/)).toBeInTheDocument();
    expect(screen.getByText(/worker: 5/)).toBeInTheDocument();
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});
