import {
  Alert,
  Card,
  CardContent,
  CardHeader,
  Chip,
  CircularProgress,
  Grid,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import { Suspense, lazy, useEffect, useMemo, useState } from 'react';
import { rateLimitApi } from '../api/endpoints';
import type { RateLimitSnapshot } from '../types/api';

const Chart = lazy(() => import('react-apexcharts'));

export function RateLimitPage(): JSX.Element {
  const [snapshot, setSnapshot] = useState<RateLimitSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    rateLimitApi
      .snapshot()
      .then(setSnapshot)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'Failed to load'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <Stack alignItems="center" sx={{ py: 6 }}>
        <CircularProgress size={28} />
      </Stack>
    );
  }
  if (error) return <Alert severity="error">{error}</Alert>;
  if (!snapshot) return <Alert severity="info">No telemetry yet.</Alert>;

  if (!snapshot.available) {
    return (
      <Alert severity="info">
        Rate-limit telemetry not yet recorded. The first <code>claude -p</code>
        invocation in the worker, bot, or dashboard will create the table.
      </Alert>
    );
  }

  return (
    <Stack spacing={3}>
      <Grid container spacing={3}>
        <Grid item xs={12} md={4}>
          <Card>
            <CardHeader title="Calls (24h)" />
            <CardContent>
              <Suspense fallback={<CircularProgress size={24} />}>
                <UsageGauge total={snapshot.total_24h} />
              </Suspense>
              <Stack direction="row" spacing={1} sx={{ mt: 2 }} useFlexGap flexWrap="wrap">
                {Object.entries(snapshot.services_breakdown_24h).map(([service, count]) => (
                  <Chip
                    key={service}
                    size="small"
                    label={`${service}: ${count}`}
                    color={service === 'dashboard' ? 'primary' : 'default'}
                    variant={service === 'dashboard' ? 'filled' : 'outlined'}
                  />
                ))}
              </Stack>
              <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
                Last call: {snapshot.last_call_ts ?? 'never'}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={8}>
          <Card>
            <CardHeader
              title="Calls per hour"
              subheader="Stacked by service over the last 24 hours."
            />
            <CardContent>
              <Suspense fallback={<CircularProgress size={24} />}>
                <CallsByHourChart snapshot={snapshot} />
              </Suspense>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Card>
        <CardHeader
          title="Recent calls"
          subheader={`5-minute error rate: ${(snapshot.error_rate_5m * 100).toFixed(1)}%`}
        />
        <CardContent sx={{ pt: 0 }}>
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Timestamp</TableCell>
                  <TableCell>Service</TableCell>
                  <TableCell>Purpose</TableCell>
                  <TableCell>Tokens (in/out)</TableCell>
                  <TableCell>Duration</TableCell>
                  <TableCell>Exit</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {snapshot.recent_calls.map((row) => (
                  <TableRow key={row.id}>
                    <TableCell>{row.ts.replace('T', ' ').replace('Z', '')}</TableCell>
                    <TableCell>
                      <Chip size="small" label={row.service} variant="outlined" />
                    </TableCell>
                    <TableCell>{row.purpose}</TableCell>
                    <TableCell>
                      {row.input_tokens ?? '—'} / {row.output_tokens ?? '—'}
                    </TableCell>
                    <TableCell>{row.duration_ms ? `${row.duration_ms} ms` : '—'}</TableCell>
                    <TableCell>
                      <Chip
                        size="small"
                        color={row.exit_code === 0 ? 'success' : 'error'}
                        label={row.exit_code}
                      />
                    </TableCell>
                  </TableRow>
                ))}
                {snapshot.recent_calls.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={6}>
                      <Typography color="text.secondary" align="center">
                        No recent calls.
                      </Typography>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </CardContent>
      </Card>
    </Stack>
  );
}

function UsageGauge({ total }: { total: number }): JSX.Element {
  const cap = 200; // a synthesis budget for visualisation purposes
  const percent = Math.min(100, Math.round((total / cap) * 100));
  return (
    <Chart
      type="radialBar"
      height={240}
      options={{
        chart: { sparkline: { enabled: true } },
        plotOptions: {
          radialBar: {
            startAngle: -90,
            endAngle: 90,
            hollow: { size: '60%' },
            track: { background: '#F4F6F8', strokeWidth: '100%' },
            dataLabels: {
              name: { show: false },
              value: {
                offsetY: -4,
                fontSize: '32px',
                fontWeight: 700,
                formatter: () => `${total}`,
              },
            },
          },
        },
        fill: {
          type: 'gradient',
          gradient: {
            shade: 'light',
            shadeIntensity: 0.4,
            gradientToColors: ['#5BE49B'],
            type: 'horizontal',
            opacityFrom: 1,
            opacityTo: 1,
            stops: [0, 100],
          },
        },
        colors: ['#00A76F'],
        labels: ['Calls'],
      }}
      series={[percent]}
    />
  );
}

function CallsByHourChart({ snapshot }: { snapshot: RateLimitSnapshot }): JSX.Element {
  const buckets = snapshot.by_hour;
  // Pivot: rows = hour, columns = service.
  const hours = useMemo(() => Array.from(new Set(buckets.map((b) => b.hour))).sort(), [buckets]);
  const services = useMemo(
    () => Array.from(new Set(buckets.map((b) => b.service))),
    [buckets],
  );
  const series = services.map((service) => ({
    name: service,
    data: hours.map((hour) => {
      const found = buckets.find((b) => b.hour === hour && b.service === service);
      return found ? found.count : 0;
    }),
  }));
  const colors = ['#00A76F', '#FFAB00', '#FF5630', '#637381'];
  return (
    <Chart
      type="bar"
      height={300}
      options={{
        chart: { stacked: true, toolbar: { show: false } },
        plotOptions: { bar: { borderRadius: 4, columnWidth: '40%' } },
        dataLabels: { enabled: false },
        legend: { position: 'top' },
        xaxis: {
          categories: hours.map((h) => h.slice(11, 16)),
          labels: { rotate: -45 },
        },
        colors,
        grid: { strokeDashArray: 4 },
      }}
      series={series}
    />
  );
}
