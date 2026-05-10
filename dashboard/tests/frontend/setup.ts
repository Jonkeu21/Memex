import '@testing-library/jest-dom/vitest';
import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';
import * as React from 'react';

// Strip the lazy markdown viewer in tests — its dynamic imports interact
// poorly with jsdom's module loader and obscure the things we actually want
// to assert. The smoke tests render answer text via plain JSX instead.
vi.mock('../../frontend/src/components/MarkdownViewer', () => ({
  MarkdownViewer: ({ body }: { body: string }) =>
    React.createElement('div', { 'data-testid': 'md-viewer' }, body),
}));

// Stub apexcharts so the rate-limit page renders without spinning up a chart
// engine in jsdom.
vi.mock('react-apexcharts', () => ({
  default: () => React.createElement('div', { 'data-testid': 'apex-chart' }),
}));

afterEach(() => {
  cleanup();
  localStorage.clear();
});
