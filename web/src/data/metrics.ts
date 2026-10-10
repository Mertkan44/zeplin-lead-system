// Report metrics from GET /api/workspace?view=metrics (src/metrics.py): every
// number comes with its label and the definition shown to the user.
import { useQuery } from '@tanstack/react-query';

import { apiRequest } from '../lib/api';

export type Period = '7' | '30' | '90' | 'all';

export interface Metric {
  value: number | null;
  label: string;
  definition: string;
  sample?: number;
  excluded?: number;
}

export interface CountItem {
  key?: string;
  label?: string;
  count: number;
}

export interface Metrics {
  period: { key: Period; label: string; start: string | null; end: string; timezone: string };
  lead_count: number;
  sales: {
    contacted_businesses: Metric;
    contact_results: Metric;
    interested_businesses: Metric;
    proposal_businesses: Metric;
    won_businesses: Metric;
    lost_businesses: Metric;
    outcomes: CountItem[];
  };
  tasks: { overdue: Metric; due_today: Metric; upcoming: Metric };
  statuses: { label: string; definition: string; items: CountItem[] };
  research: {
    new_leads: Metric;
    analyzed_leads: Metric;
    average_score: Metric;
    average_coverage: Metric;
    grades: { definition: string; items: CountItem[]; unscored: number };
    sectors: { definition: string; items: CountItem[]; total: number };
  };
  weekly: { definition: string; weeks: string[]; new_leads: number[]; contact_results: number[] };
}

export function useMetrics(email: string, period: Period) {
  return useQuery({
    queryKey: ['metrics', email, period],
    queryFn: ({ signal }) =>
      apiRequest<{ metrics: Metrics }>(`/api/workspace?view=metrics&period=${period}`, { signal }).then(data => data.metrics),
    placeholderData: previous => previous,
  });
}
