import { apiFetch } from './client';
import type {
  CaptureFileBody,
  CaptureListing,
  InboxFile,
  InboxListing,
  QueueActionAck,
  QueueItem,
  QueueListing,
  RateLimitSnapshot,
  RetrievalResponse,
  TaxonomyDocument,
  TaxonomyResponse,
} from '../types/api';

export const queueApi = {
  list: (params?: { status?: string; source_type?: string; limit?: number; cursor?: number }) =>
    apiFetch<QueueListing>('/api/v1/queue', { params }),
  get: (id: number) => apiFetch<QueueItem>(`/api/v1/queue/${id}`),
  retry: (id: number) =>
    apiFetch<QueueActionAck>(`/api/v1/queue/${id}/retry`, { method: 'POST', withAuth: true }),
  cancel: (id: number) =>
    apiFetch<QueueActionAck>(`/api/v1/queue/${id}/cancel`, { method: 'POST', withAuth: true }),
};

export const inboxApi = {
  list: () => apiFetch<InboxListing>('/api/v1/inbox'),
  get: (path: string) => apiFetch<InboxFile>(`/api/v1/inbox/${path}`),
  route: (path: string, target_folder: string) =>
    apiFetch<{ new_path: string }>(`/api/v1/inbox/${path}/route`, {
      method: 'POST',
      withAuth: true,
      json: { target_folder },
    }),
  trash: (path: string) =>
    apiFetch<{ trashed_path: string }>(`/api/v1/inbox/${path}/delete`, {
      method: 'POST',
      withAuth: true,
    }),
};

export const taxonomyApi = {
  get: () => apiFetch<TaxonomyResponse>('/api/v1/taxonomy'),
  put: (document: TaxonomyDocument) =>
    apiFetch<TaxonomyResponse>('/api/v1/taxonomy', {
      method: 'PUT',
      withAuth: true,
      json: { document },
    }),
};

export const capturesApi = {
  list: (params?: { folder?: string; q?: string; needs_review?: boolean; limit?: number; cursor?: number }) =>
    apiFetch<CaptureListing>('/api/v1/captures', { params }),
  get: (path: string) => apiFetch<CaptureFileBody>(`/api/v1/captures/${path}`),
};

export const rateLimitApi = {
  snapshot: () => apiFetch<RateLimitSnapshot>('/api/v1/rate-limit'),
};

export const retrievalApi = {
  ask: (question: string) =>
    apiFetch<RetrievalResponse>('/api/v1/retrieval', {
      method: 'POST',
      withAuth: true,
      json: { question },
    }),
};
