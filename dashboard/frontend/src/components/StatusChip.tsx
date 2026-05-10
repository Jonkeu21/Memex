import { Chip } from '@mui/material';
import type { QueueStatus } from '../types/api';

const STATUS_COLORS: Record<QueueStatus, { color: string; bg: string; label: string }> = {
  queued: { color: '#637381', bg: 'rgba(145, 158, 171, 0.16)', label: 'Queued' },
  processing: { color: '#006C9C', bg: 'rgba(0, 184, 217, 0.16)', label: 'Processing' },
  filed: { color: '#118D57', bg: 'rgba(34, 197, 94, 0.16)', label: 'Filed' },
  needs_review: { color: '#B76E00', bg: 'rgba(255, 171, 0, 0.16)', label: 'Needs review' },
  failed: { color: '#B71D18', bg: 'rgba(255, 86, 48, 0.16)', label: 'Failed' },
};

export function StatusChip({ status }: { status: QueueStatus }): JSX.Element {
  const cfg = STATUS_COLORS[status];
  return (
    <Chip
      size="small"
      label={cfg.label}
      sx={{
        color: cfg.color,
        backgroundColor: cfg.bg,
        fontWeight: 600,
      }}
      aria-label={`Queue status: ${cfg.label}`}
    />
  );
}
