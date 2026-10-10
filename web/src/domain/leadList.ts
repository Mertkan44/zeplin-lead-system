// The lead list (review §12.4): what each row shows, and filtering, sorting
// and export over the leads the user can see.
import type { Lead, LeadStatus } from '../data/types';
import { STATUS_OPTIONS } from './catalog';
import { fmtDate } from './format';
import { lateness, sameDay, todayTask } from './today';

export type NextWorkKind = 'overdue' | 'due_today' | 'first_contact' | 'verification' | 'scheduled' | 'none';

export interface NextWork {
  kind: NextWorkKind;
  label: string;
  detail: string;
}

const clock = (date: Date) => date.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });

/** The next piece of work on a lead and when it is due. */
export function nextWork(lead: Lead, now = new Date()): NextWork {
  const task = todayTask(lead, now);
  const workflow = lead.workflow || {};
  if (task?.section === 'overdue' && task.followUpAt) return { kind: 'overdue', label: 'Takip gecikti', detail: lateness(task.followUpAt, now) };
  if (task?.section === 'due_today' && task.followUpAt) return { kind: 'due_today', label: 'Bugün takip', detail: clock(task.followUpAt) };
  if (task?.section === 'first_contact') return { kind: 'first_contact', label: 'İlk temas', detail: task.assignmentLate ? 'Atama tarihi geçti' : 'Aramaya hazır' };
  if (task?.section === 'verification') {
    return {
      kind: 'verification',
      label: workflow.latest_outcome === 'wrong_number' ? 'Numarayı doğrula' : 'Doğrulama',
      detail: `${workflow.completed_count || 0}/${workflow.required_count || 0} kontrol`,
    };
  }
  if (workflow.follow_up_at) {
    const at = new Date(workflow.follow_up_at);
    return { kind: 'scheduled', label: 'Takip planlı', detail: sameDay(at, now) ? clock(at) : fmtDate(workflow.follow_up_at) };
  }
  return { kind: 'none', label: '—', detail: workflow.stage === 'closed' ? 'Kapandı' : 'Planlı iş yok' };
}

export interface Opportunity {
  service: string;
  /** Proven by the research, or only worth asking about. */
  level: 'proven' | 'discovery' | 'none';
}

export function opportunity(lead: Lead): Opportunity {
  const proven = lead.matched_services || [];
  if (proven.length) {
    const name = lead.recommended_package?.primary_service || lead.recommended_package?.name || proven[0].name;
    return { service: name, level: proven[0].requires_discovery ? 'discovery' : 'proven' };
  }
  const discovery = lead.discovery_services || [];
  if (discovery.length) return { service: discovery[0].name, level: 'discovery' };
  return { service: '—', level: 'none' };
}

export type Trust = 'current' | 'partial' | 'stale' | 'missing';

export const TRUST_LABELS: Record<Trust, string> = { current: 'Güncel', partial: 'Kısmi', stale: 'Eski', missing: 'Eksik' };

/** How far the research behind a lead can be trusted. */
export function dataTrust(lead: Lead): Trust {
  const brief = lead.research_brief_v2;
  if (!brief) return 'missing';
  if (brief.stale) return 'stale';
  if (brief.status === 'ready') return 'current';
  if (brief.status === 'partial') return 'partial';
  return 'missing';
}

export interface LastContact {
  at: string;
  outcome: string;
}

export function lastContact(lead: Lead): LastContact | null {
  const workflow = lead.workflow || {};
  if (!workflow.latest_contact_at) return null;
  return { at: workflow.latest_contact_at, outcome: workflow.latest_outcome_label || 'Sonuç kaydedildi' };
}

/** Filters as they appear in the URL (Turkish keys, readable links). */
export interface ListFilters {
  q: string;
  asama: string;
  is: string;
  sorumlu: string;
  sehir: string;
  hizmet: string;
  guven: string;
}

export const FILTER_KEYS: Array<keyof ListFilters> = ['q', 'asama', 'is', 'sorumlu', 'sehir', 'hizmet', 'guven'];

export const NEXT_WORK_OPTIONS: Array<[NextWorkKind, string]> = [
  ['overdue', 'Takip gecikti'],
  ['due_today', 'Bugün takip'],
  ['first_contact', 'İlk temas'],
  ['verification', 'Doğrulama'],
  ['scheduled', 'Takip planlı'],
  ['none', 'Planlı iş yok'],
];

export const STAGE_OPTIONS = STATUS_OPTIONS;

export type SortKey = 'oncelik' | 'is' | 'temas' | 'isim';

export const SORT_OPTIONS: Array<[SortKey, string]> = [
  ['oncelik', 'Öncelik'],
  ['is', 'Sonraki iş'],
  ['temas', 'Son temas'],
  ['isim', 'İsim (A–Z)'],
];

const WORK_ORDER: Record<NextWorkKind, number> = { overdue: 0, due_today: 1, first_contact: 2, verification: 3, scheduled: 4, none: 5 };

function haystack(lead: Lead): string {
  return [lead.name, lead.city, lead.category, lead.sector, lead.phone, lead.address, ...(lead.matched_services || []).map(item => item.name)]
    .filter(Boolean).join(' ').toLocaleLowerCase('tr-TR');
}

export function applyFilters(leads: Lead[], filters: ListFilters, statuses: Record<string, LeadStatus>, now = new Date()): Lead[] {
  const term = filters.q.trim().toLocaleLowerCase('tr-TR');
  return leads.filter(lead => {
    if (term && !haystack(lead).includes(term)) return false;
    if (filters.asama && (statuses[lead.name] || 'yeni') !== filters.asama) return false;
    if (filters.is && nextWork(lead, now).kind !== filters.is) return false;
    if (filters.sorumlu === 'yok' ? Boolean(lead.assigned_to) : filters.sorumlu && lead.assigned_to !== filters.sorumlu) return false;
    if (filters.sehir && lead.city !== filters.sehir) return false;
    if (filters.hizmet && !(lead.matched_services || []).some(item => item.slug === filters.hizmet)) return false;
    if (filters.guven && dataTrust(lead) !== filters.guven) return false;
    return true;
  });
}

export function sortLeads(leads: Lead[], key: SortKey, now = new Date()): Lead[] {
  const rows = [...leads];
  const priority = (lead: Lead) => Number(lead.sales_priority_score || 0);
  if (key === 'isim') return rows.sort((a, b) => a.name.localeCompare(b.name, 'tr'));
  if (key === 'temas') return rows.sort((a, b) => String(b.workflow?.latest_contact_at || '').localeCompare(String(a.workflow?.latest_contact_at || '')));
  if (key === 'is') return rows.sort((a, b) => WORK_ORDER[nextWork(a, now).kind] - WORK_ORDER[nextWork(b, now).kind] || priority(b) - priority(a));
  return rows.sort((a, b) => priority(b) - priority(a) || b.scoring.score - a.scoring.score);
}

/**
 * One CSV cell. Text a spreadsheet would run as a formula (=, +, -, @, tab,
 * carriage return at the start) gets a leading apostrophe; quotes are
 * doubled; everything is quoted, so phone numbers stay text.
 */
export function csvCell(value: unknown): string {
  let text = value === null || value === undefined ? '' : String(value);
  if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`;
  return `"${text.replace(/"/g, '""')}"`;
}

export function leadsToCsv(leads: Lead[], ownerName: (email: string) => string, statusLabel: (lead: Lead) => string, now = new Date()): string {
  const header = ['İşletme', 'Sektör', 'Şehir', 'Telefon', 'Aşama', 'Sonraki iş', 'Sorumlu', 'Fırsat', 'Son temas', 'Son sonuç', 'Veri güveni', 'Öncelik'];
  const rows = leads.map(lead => {
    const work = nextWork(lead, now);
    const contact = lastContact(lead);
    return [
      lead.name,
      lead.category || lead.sector || '',
      lead.city || '',
      lead.phone || '',
      statusLabel(lead),
      work.kind === 'none' ? '' : `${work.label} (${work.detail})`,
      lead.assigned_to ? ownerName(lead.assigned_to) : '',
      opportunity(lead).service === '—' ? '' : opportunity(lead).service,
      contact ? fmtDate(contact.at) : '',
      contact ? contact.outcome : '',
      TRUST_LABELS[dataTrust(lead)],
      lead.sales_priority_score ?? '',
    ];
  });
  return [header, ...rows].map(row => row.map(csvCell).join(',')).join('\r\n');
}
