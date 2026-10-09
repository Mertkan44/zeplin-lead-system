// Reading CRM data: the workspace payload, a lead's full timeline and the team
// list, through the query cache (lib/queryClient.ts).
import { createContext, useContext } from 'react';
import { useQuery } from '@tanstack/react-query';

import { apiRequest } from '../lib/api';
import { normalizeStatus } from '../domain/catalog';
import type { Lead, LeadStatus, OutreachEvent, User, Workspace } from './types';

export const queryKeys = {
  workspaceRoot: ['workspace'] as const,
  workspace: (email: string) => ['workspace', email] as const,
  timelineRoot: ['timeline'] as const,
  timeline: (email: string, leadName: string) => ['timeline', email, leadName] as const,
  users: (email: string) => ['users', email] as const,
};

export function normalizeOutreachEvent(item: Record<string, any> | null | undefined): OutreachEvent | null {
  if (!item) return null;
  return {
    lead: item.lead || item.lead_name || '',
    action: item.action || 'note_added',
    date: item.date || item.happened_at || item.created_at || new Date().toISOString(),
    note: item.note || '',
    channel: item.channel || null,
    channelLabel: item.channel_label || item.channelLabel || null,
    outcome: item.outcome || null,
    outcomeLabel: item.outcome_label || item.outcomeLabel || null,
    followUpAt: item.follow_up_at || item.followUpAt || null,
    serviceSlugs: item.service_slugs || item.serviceSlugs || [],
    contactName: item.contact_name || item.contactName || null,
    draftStatus: item.draft_status || item.draftStatus || null,
    draftSubject: item.draft_subject || item.draftSubject || null,
    draftBody: item.draft_body || item.draftBody || null,
    manualVerification: item.manual_verification || item.manualVerification || null,
    ts: item.ts || item.id || Date.now(),
  };
}

function normalizeEvents(rows: unknown): OutreachEvent[] {
  return Array.isArray(rows) ? rows.map(normalizeOutreachEvent).filter((event): event is OutreachEvent => event !== null) : [];
}

export function normalizeWorkspace(data: Record<string, any>): Workspace {
  return {
    leads: Array.isArray(data.leads) ? data.leads : [],
    outreach: normalizeEvents(data.outreach),
    summary: data.summary || null,
    assignments: Array.isArray(data.assignments) ? data.assignments : [],
    teamPerformance: Array.isArray(data.team_performance) ? data.team_performance : [],
    integrations: data.integrations || {},
    schema: data.schema || null,
  };
}

export function useWorkspaceQuery(email: string) {
  return useQuery({
    queryKey: queryKeys.workspace(email),
    queryFn: ({ signal }) => apiRequest('/api/workspace', { signal }).then(normalizeWorkspace),
  });
}

/** The workspace carries the last 30 days of events; this is one lead's full timeline. */
export function useLeadTimeline(email: string, leadName: string) {
  return useQuery({
    queryKey: queryKeys.timeline(email, leadName),
    queryFn: ({ signal }) =>
      apiRequest<{ items?: unknown }>(`/api/outreach?lead=${encodeURIComponent(leadName)}&limit=200`, { signal })
        .then(data => normalizeEvents(data.items)),
  });
}

/** Team members; when the list cannot be read the signed-in user stands alone. */
export function useTeamUsers(user: User) {
  return useQuery({
    queryKey: queryKeys.users(user.email),
    queryFn: ({ signal }) =>
      apiRequest<{ users?: User[] }>('/api/users', { signal })
        .then(data => (Array.isArray(data.users) ? data.users : []))
        .catch(() => [user]),
  });
}

const newestFirst = (a: OutreachEvent, b: OutreachEvent) => b.date.localeCompare(a.date);

/** Events of one lead from several sources, deduplicated by id, newest first. */
export function mergeEvents(...lists: OutreachEvent[][]): OutreachEvent[] {
  const byKey = new Map<OutreachEvent['ts'], OutreachEvent>();
  lists.forEach(list => list.forEach(event => byKey.set(event.ts, event)));
  return [...byKey.values()].sort(newestFirst);
}

/** The workspace as the screens read it. */
export interface Crm extends Workspace {
  /** Leads as the API sent them. */
  rows: Lead[];
  /** Leads by score, highest first: the order of every list and of prev/next. */
  leads: Lead[];
  statuses: Record<string, LeadStatus>;
  /** A lead's events, newest first. */
  eventsFor: (leadName: string) => OutreachEvent[];
}

const NO_EVENTS: OutreachEvent[] = [];

export function buildCrm(workspace: Workspace): Crm {
  const statuses: Record<string, LeadStatus> = {};
  workspace.leads.forEach(lead => { statuses[lead.name] = normalizeStatus(lead.status); });
  const byLead = new Map<string, OutreachEvent[]>();
  workspace.outreach.forEach(event => {
    const list = byLead.get(event.lead);
    if (list) list.push(event);
    else byLead.set(event.lead, [event]);
  });
  byLead.forEach(list => list.sort(newestFirst));
  return {
    ...workspace,
    rows: workspace.leads,
    leads: [...workspace.leads].sort((a, b) => b.scoring.score - a.scoring.score),
    statuses,
    eventsFor: name => byLead.get(name) || NO_EVENTS,
  };
}

export const CrmContext = createContext<Crm | null>(null);

export function useCrm(): Crm {
  const crm = useContext(CrmContext);
  if (!crm) throw new Error('useCrm must be used inside the dashboard');
  return crm;
}

export interface Session {
  user: User;
  /** Opens the logout confirmation. */
  requestLogout: () => void;
}

export const SessionContext = createContext<Session | null>(null);

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error('useSession must be used inside a signed-in session');
  return session;
}
