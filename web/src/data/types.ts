// Shapes of the API payloads the dashboard reads. Only the fields the screens
// use are listed; the API sends more.

export type Role = 'admin' | 'sales';

export interface User {
  email: string;
  name?: string | null;
  role?: Role | string | null;
  title?: string | null;
  avatar_url?: string | null;
  active?: boolean;
}

export type LeadStatus = 'yeni' | 'missing_info' | 'ready' | 'contacted' | 'follow_up' | 'converted' | 'lost';

export interface AuditFinding {
  code?: string;
  title?: string;
  evidence?: string;
  impact?: string;
  severity?: string;
  finding_type?: string;
  confidence?: number;
  talking_point?: string;
  verification?: string;
  source_url?: string;
}

export interface AuditCheck {
  code: string;
  label: string;
  note?: string;
  status: 'pass' | 'fail' | 'unknown' | string;
  source_url?: string;
}

export interface ServiceMatch {
  slug: string;
  name: string;
  category?: string;
  desc?: string;
  why?: string;
  confidence?: number;
  match_type?: string;
  requires_discovery?: boolean;
  evidence?: string[];
  deliverables?: string[];
  discovery_questions?: string[];
}

export interface WorkflowCheck {
  key: string;
  label: string;
  complete: boolean;
}

export interface Workflow {
  stage?: string;
  stage_label?: string;
  checks?: WorkflowCheck[];
  missing?: string[];
  completed_count?: number;
  required_count?: number;
  ready_to_contact?: boolean;
  contact_available?: boolean;
  latest_contact_at?: string | null;
}

export interface Lead {
  lead_id?: number | null;
  name: string;
  city?: string;
  sector?: string;
  category?: string;
  phone?: string;
  email?: string;
  address?: string;
  maps_url?: string;
  status?: LeadStatus | string;
  revision?: number;
  last_analyzed?: string;
  website?: { has_website?: boolean; website_url?: string; [key: string]: unknown };
  social?: {
    has_instagram?: boolean;
    instagram_url?: string;
    instagram_username?: string | null;
    identity_confidence?: number;
    stats?: Record<string, any>;
    [key: string]: unknown;
  };
  research?: Record<string, any>;
  audit_findings?: AuditFinding[];
  audit_checks?: AuditCheck[];
  scoring: {
    score: number;
    grade: string;
    score_status?: string;
    coverage?: number;
    confidence?: number;
  };
  matched_services?: ServiceMatch[];
  discovery_services?: ServiceMatch[];
  recommended_package?: Record<string, any>;
  estimated_value_tl?: number;
  sales_priority_score?: number;
  next_action?: string;
  priority_reason?: string;
  ai_report?: string | null;
  ai_email?: string | null;
  ai_state?: string;
  sales_playbook?: Record<string, any>;
  research_brief_v2?: Record<string, any> | null;
  workflow?: Workflow;
  manual_verification?: Record<string, any> | null;
  facts?: Record<string, any>;
  assigned_to?: string | null;
  assigned_user_id?: string | null;
  assignment_due_at?: string | null;
}

/** An outreach event as the screens use it (normalized from the API row). */
export interface OutreachEvent {
  lead: string;
  action: string;
  date: string;
  note: string;
  channel: string | null;
  channelLabel: string | null;
  outcome: string | null;
  outcomeLabel: string | null;
  followUpAt: string | null;
  serviceSlugs: string[];
  contactName: string | null;
  draftStatus: string | null;
  draftSubject: string | null;
  draftBody: string | null;
  manualVerification: Record<string, any> | null;
  /** Server id, or a local timestamp until the server copy arrives. */
  ts: number | string;
}

export interface Assignment {
  lead_name?: string;
  user_email: string;
  status: string;
  due_at?: string | null;
}

export interface SchemaStatus {
  ready: boolean;
  version?: string | null;
  required_version?: string;
  failed_checks?: string[];
}

export interface WorkspaceSummary {
  assigned_count?: number;
  today_call_count?: number;
  today_result_count?: number;
  today_interested_count?: number;
  today_no_answer_count?: number;
  overdue_follow_up_count?: number;
  follow_up_count?: number;
  won_count?: number;
  service_interest?: Array<{ slug: string; count: number }>;
  [key: string]: unknown;
}

/** /api/workspace after normalization (see data/workspace.ts). */
export interface Workspace {
  leads: Lead[];
  outreach: OutreachEvent[];
  summary: WorkspaceSummary | null;
  assignments: Assignment[];
  teamPerformance: Array<Record<string, any>>;
  integrations: { google_places?: boolean };
  schema: SchemaStatus | null;
}
