import { useQuery } from '@tanstack/react-query';
import { apiRequest, ApiError } from '../lib/api';
import { queryClient } from '../lib/queryClient';
import { OUTREACH_ERRORS } from '../domain/catalog';

export type OpportunityStage = 'new' | 'contact' | 'discovery' | 'proposal' | 'decision' | 'won' | 'lost';
export interface Opportunity {
  id: number;
  lead_id: number;
  lead_name: string;
  lead_revision: number;
  lead_status: string;
  revision: number;
  stage: OpportunityStage;
  service_slug: string | null;
  amount: number | null;
  amount_unknown: boolean;
  lost_reason: string | null;
  stage_entered_at: string;
  owner_email: string | null;
  due_at: string | null;
  last_contact_at: string | null;
  can_write: boolean;
}
export interface OpportunityHistory {
  id: number;
  revision: number;
  from_stage: OpportunityStage | null;
  to_stage: OpportunityStage;
  actor_email: string | null;
  source: string;
  note: string | null;
  amount: number | null;
  amount_unknown: boolean;
  service_slug: string | null;
  happened_at: string;
}

export const opportunityKeys = {
  root: ['opportunities'] as const,
  list: (email: string) => ['opportunities', email] as const,
  historyRoot: ['opportunity-history'] as const,
};

export function useOpportunities(email: string) {
  return useQuery({
    queryKey: opportunityKeys.list(email),
    queryFn: ({ signal }) => apiRequest<{ opportunities: Opportunity[] }>('/api/workspace?view=pipeline', { signal }).then(data => data.opportunities),
    refetchInterval: 30_000,
  });
}

export function fetchOpportunityHistory(leadId: number, before: number | null = null, signal?: AbortSignal) {
  return apiRequest<{ items: OpportunityHistory[]; next_before: number | null }>(`/api/workspace?view=pipeline&lead_id=${leadId}${before ? `&before=${before}` : ''}`, { signal });
}

export interface OpportunityWrite {
  idempotency_key: string;
  lead_id: number;
  expected_lead_revision: number;
  expected_opportunity_revision: number;
  stage: OpportunityStage;
  note: string;
  amount: string | null;
  amount_unknown: boolean;
  service_slug: string | null;
}

export class OpportunityError extends Error {
  constructor(readonly code: string | undefined) {
    super((code && (OUTREACH_ERRORS[code] || {
      OPPORTUNITY_VERSION_CONFLICT: 'Fırsat başka bir işlemle değişti. Güncel bilgileri alıp tekrar kaydet.',
      OPPORTUNITY_REOPEN_REQUIRED: 'Kapanmış fırsatı önce yönetici yeniden açmalı.',
      OPPORTUNITY_REOPEN_ADMIN_REQUIRED: 'Yeniden açmak için yönetici ve açıklama gerekli.',
      OPPORTUNITY_REASON_REQUIRED: 'Kaybetme veya önceki aşamaya dönme nedenini yaz.',
      OPPORTUNITY_AMOUNT_INVALID: 'Tutarı veya “henüz bilinmiyor” seçeneğini belirt.',
    }[code])) || 'Fırsat kaydedilemedi. Bağlantını kontrol edip tekrar dene.');
  }
}

export async function saveOpportunity(write: OpportunityWrite) {
  try {
    const response = await apiRequest<{ opportunity: Opportunity; lead_revision: number; lead_status: string }>('/api/workspace?view=pipeline', { method: 'POST', body: write });
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: opportunityKeys.root }),
      queryClient.invalidateQueries({ queryKey: opportunityKeys.historyRoot }),
    ]);
    return response;
  } catch (error) {
    if (error instanceof ApiError) throw new OpportunityError(error.code);
    throw error;
  }
}
