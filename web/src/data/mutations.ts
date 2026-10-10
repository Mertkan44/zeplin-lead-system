// Writing CRM data. Each write goes to the API first; the cached workspace is
// then updated in place so the screen reflects it at once, and the caller
// refreshes from the server (refreshWorkspace) for the authoritative copy.
import { apiRequest, ApiError } from '../lib/api';
import { newRequestId } from '../lib/browser';
import { queryClient } from '../lib/queryClient';
import { ACTIONS, OUTREACH_ERRORS } from '../domain/catalog';
import { normalizeOutreachEvent, queryKeys } from './workspace';
import type { Lead, LeadStatus, OutreachEvent, Workspace } from './types';
import { opportunityKeys } from './opportunities';

/** Refetch the workspace and any open timeline from the server. */
export function refreshWorkspace(): Promise<void> {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.workspaceRoot }),
    queryClient.invalidateQueries({ queryKey: queryKeys.timelineRoot }),
    queryClient.invalidateQueries({ queryKey: opportunityKeys.root }),
    queryClient.invalidateQueries({ queryKey: opportunityKeys.historyRoot }),
  ]).then(() => undefined);
}

/** The workspace now in the cache (the one of the signed-in user). */
export function cachedWorkspace(): Workspace | undefined {
  return queryClient.getQueriesData<Workspace>({ queryKey: queryKeys.workspaceRoot })[0]?.[1];
}

function updateWorkspace(update: (workspace: Workspace) => Workspace): void {
  queryClient.setQueriesData<Workspace>({ queryKey: queryKeys.workspaceRoot }, current => (current ? update(current) : current));
}

function setCachedStatus(leadName: string, status: string | undefined): void {
  updateWorkspace(workspace => ({
    ...workspace,
    leads: workspace.leads.map(lead => (lead.name === leadName ? { ...lead, status } : lead)),
  }));
}

function addCachedEvent(event: OutreachEvent): void {
  updateWorkspace(workspace => ({
    ...workspace,
    outreach: [...workspace.outreach.filter(item => item.ts !== event.ts), event],
  }));
}

export class OutreachError extends Error {
  readonly code: string;

  constructor(code: string | undefined) {
    super((code && OUTREACH_ERRORS[code]) || 'Sonuç kaydedilemedi. Bağlantını kontrol edip tekrar dene.');
    this.name = 'OutreachError';
    this.code = code || 'outreach_save_failed';
  }
}

interface OutreachWrite {
  lead: string;
  action: string;
  date?: string;
  note?: string;
  channel?: string | null;
  outcome?: string | null;
  followUpAt?: string | null;
  serviceSlugs?: string[];
  contactName?: string | null;
  draftStatus?: string | null;
  draftSubject?: string | null;
  draftBody?: string | null;
  manualVerification?: Record<string, unknown> | null;
  expectedRevision?: number | null;
  requestId?: string;
}

interface OutreachResponse {
  event?: Record<string, unknown>;
  status?: LeadStatus;
  [key: string]: unknown;
}

function persistOutreachEvent(write: OutreachWrite): Promise<OutreachResponse> {
  return apiRequest<OutreachResponse>('/api/outreach', {
    method: 'POST',
    keepalive: true,
    body: {
      lead_name: write.lead,
      action: write.action,
      happened_at: write.date,
      note: write.note,
      channel: write.channel,
      outcome: write.outcome,
      follow_up_at: write.followUpAt,
      service_slugs: write.serviceSlugs,
      contact_name: write.contactName,
      draft_status: write.draftStatus,
      subject: write.draftSubject,
      body: write.draftBody,
      manual_verification: write.manualVerification,
      expected_revision: write.expectedRevision ?? null,
      source: 'dashboard',
      idempotency_key: write.requestId || newRequestId(),
    },
  }).catch(err => { throw new OutreachError(err instanceof ApiError ? err.code : undefined); });
}

function recordSaved(write: OutreachWrite, data: OutreachResponse): OutreachEvent {
  const saved = normalizeOutreachEvent(data.event || { ...write, ts: Date.now() })!;
  addCachedEvent(saved);
  return saved;
}

/** Moves a lead to `status`; the screen shows it at once and reverts if the save fails. */
export function setLeadStatus(leadName: string, status: LeadStatus): Promise<void> {
  const previous = cachedWorkspace()?.leads.find(lead => lead.name === leadName)?.status;
  setCachedStatus(leadName, status);
  return apiRequest('/api/status', { method: 'POST', body: { name: leadName, status } })
    .then(() => undefined)
    .catch(() => {
      setCachedStatus(leadName, previous);
      throw new Error('Durum kaydedilemedi.');
    });
}

/** Records an activity; actions that imply a status (deal_won, …) also set it. */
export function addOutreach(leadName: string, action: string, date: string, note: string, requestId?: string): Promise<void> {
  const write = { lead: leadName, action, date, note, requestId };
  return persistOutreachEvent(write).then(data => {
    recordSaved(write, data);
    const status = ACTIONS[action]?.status;
    return status ? setLeadStatus(leadName, status) : undefined;
  });
}

export interface ContactResultValues {
  channel: string;
  outcome: string;
  /** Sent only when the user picked a date; otherwise the server applies the default rule. */
  followUpAt: string | null;
  contactName: string;
  note: string;
  serviceSlugs: string[];
}

/** `requestId` stays the same across retries of the same form. */
export function saveContactResult(lead: Lead, values: ContactResultValues, requestId: string): Promise<OutreachResponse> {
  const write: OutreachWrite = {
    lead: lead.name,
    action: 'contact_result_recorded',
    note: values.note || '',
    channel: values.channel,
    outcome: values.outcome,
    followUpAt: values.followUpAt || null,
    serviceSlugs: values.serviceSlugs || [],
    contactName: values.contactName || null,
    expectedRevision: Number.isInteger(lead.revision) ? lead.revision : null,
    requestId,
  };
  return persistOutreachEvent(write).then(data => {
    recordSaved(write, data);
    if (data.status) setCachedStatus(lead.name, data.status);
    return data;
  });
}

export function saveDraftReview(lead: Lead, draft: { channel: string; subject?: string; body?: string }): Promise<OutreachResponse> {
  const write: OutreachWrite = {
    lead: lead.name,
    action: 'draft_reviewed',
    date: new Date().toISOString(),
    note: '',
    channel: draft.channel,
    draftStatus: 'approved',
    draftSubject: draft.subject || '',
    draftBody: draft.body || '',
  };
  return persistOutreachEvent(write).then(data => {
    recordSaved(write, data);
    return data;
  });
}

export function saveManualVerification(lead: Lead, values: Record<string, unknown>): Promise<OutreachResponse> {
  const write: OutreachWrite = {
    lead: lead.name,
    action: 'manual_verification_saved',
    date: new Date().toISOString(),
    note: '',
    manualVerification: values,
  };
  return persistOutreachEvent(write).then(data => {
    recordSaved(write, data);
    return data;
  });
}

export function saveLeadAssignment(leadName: string, userEmail: string, dueAt: string): Promise<void> {
  return apiRequest('/api/assignments', {
    method: 'POST',
    body: {
      lead_name: leadName,
      user_email: userEmail,
      due_at: dueAt ? new Date(dueAt).toISOString() : null,
      status: 'active',
    },
  })
    .then(() => undefined)
    .catch(err => { throw new Error((err instanceof ApiError && typeof err.data.error === 'string' && err.data.error) || 'Atama kaydedilemedi.'); });
}
