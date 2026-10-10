// Rules about a lead that several screens share. Pure functions: the lead's
// status and events are passed in, nothing is read from shared state.
import type { Lead, LeadStatus, OutreachEvent } from '../data/types';
import { FOLLOW_UP_DELAYS, SECTOR_LABELS, type LeadFilter, type PipelineStageKey } from './catalog';
import { daysFromNowAtTen } from './format';

export function scoreIsAvailable(lead: Lead | null | undefined): boolean {
  return (lead?.scoring?.score_status || 'insufficient') !== 'insufficient';
}

export function verifiedInstagram(lead: Lead | null | undefined): boolean {
  return lead?.social?.has_instagram === true && Number(lead?.social?.identity_confidence || 0) >= 70;
}

export function hasContactInfo(lead: Lead): boolean {
  const researchEmails = lead.research?.website?.emails || [];
  return Boolean(lead.phone || researchEmails.length || verifiedInstagram(lead));
}

export function needsContactCompletion(lead: Lead): boolean {
  return /telefon|adres/i.test(lead.next_action || '') || !hasContactInfo(lead);
}

export function websiteHost(url: string | null | undefined): string {
  return String(url || '').replace(/^https?:\/\//, '').replace(/\/$/, '');
}

export function telHref(phone: string): string {
  return `tel:${phone.replace(/\s+/g, '')}`;
}

export type ActionIntent = 'enrich' | 'verify' | 'generate_ai' | 'draft' | 'call' | 'review';

export interface PrimaryAction {
  label: string;
  helper: string;
  intent: ActionIntent;
}

/** The next thing to do with a lead, in the order the sales process needs it. */
export function getPrimaryActionMeta(lead: Lead): PrimaryAction {
  if (needsContactCompletion(lead)) {
    return { label: 'Veriyi tamamla', helper: 'Maps ya da siteyi açar; pipeline durumu değişmez.', intent: 'enrich' };
  }
  if (!lead.matched_services || !lead.matched_services.length) {
    return { label: 'İhtiyacı doğrula', helper: 'Kaynağı açar; kanıt olmadan hizmet veya AI taslağı üretmez.', intent: 'verify' };
  }
  if (!lead.ai_report) {
    return {
      label: 'İhtiyaç raporu üret',
      helper: 'Kanıtlanan açık ve eşleşen hizmetten araştırma raporu; kanıt yeterliyse e-posta taslağı oluşturur.',
      intent: 'generate_ai',
    };
  }
  if (lead.ai_state === 'stale') {
    return {
      label: 'Raporu yenile',
      helper: 'İşletme verisi rapordan sonra değişti; rapor güncel veriyle yeniden üretilir.',
      intent: 'generate_ai',
    };
  }
  if (lead.ai_email) {
    return { label: 'Taslağı kopyala', helper: 'Hazır e-postayı panoya kopyalar; otomatik göndermez.', intent: 'draft' };
  }
  if (lead.phone) {
    return { label: 'Telefonu aç', helper: 'Mail için güçlü kanıt yok; raporu kullanarak telefon görüşmesi yap.', intent: 'call' };
  }
  return { label: 'Aksiyonu kaydet', helper: 'Sadece takip icin aktivite olusturur.', intent: 'review' };
}

export function getLeadReadiness(lead: Lead): Array<{ label: string; ready: boolean }> {
  if (lead.workflow?.checks) {
    return [
      ...lead.workflow.checks.map(item => ({ label: item.label, ready: item.complete })),
      { label: 'İletişim kanalı', ready: Boolean(lead.workflow.contact_available) },
    ];
  }
  const scoreStatus = lead.scoring?.score_status || 'insufficient';
  return [
    { label: 'İletişim kanalı', ready: hasContactInfo(lead) },
    { label: 'Denetim kanıtı', ready: scoreStatus !== 'insufficient' && Boolean(lead.audit_findings?.length) },
    { label: 'AI raporu', ready: Boolean(lead.ai_report) },
    { label: 'Kanıtlı hizmet', ready: Boolean(lead.matched_services?.length) },
  ];
}

const STAGE_BY_ACTION: Record<string, PipelineStageKey> = {
  data_enrichment_started: 'enrich',
  email_drafted: 'draft',
  draft_prepared: 'draft',
  outreach_review_started: 'draft',
  email_sent: 'contacted',
  reply_received: 'contacted',
  call_completed: 'contacted',
  call_made: 'contacted',
  follow_up_scheduled: 'meeting',
  meeting_scheduled: 'meeting',
  deal_won: 'won',
  deal_lost: 'lost',
};

/** `events` are the lead's events, newest first. */
export function getPipelineStage(status: LeadStatus, events: OutreachEvent[]): PipelineStageKey {
  if (status === 'converted') return 'won';
  if (status === 'lost') return 'lost';
  if (status === 'follow_up') return 'meeting';
  if (status === 'missing_info') return 'enrich';
  if (status === 'ready') return 'draft';
  const fallback = status === 'contacted' ? 'contacted' : 'new';
  const last = events.find(event => !['note', 'note_added'].includes(event.action));
  if (!last) return fallback;
  return STAGE_BY_ACTION[last.action] || fallback;
}

export function issueToSeverity(text: string | null | undefined): string {
  if (!text) return 'Bilgi';
  const t = text.toLowerCase();
  if (t.includes('ssl') || t.includes('https')) return 'Kritik';
  if (t.includes('web sitesi yok') || t.includes('website yok') || t.includes('site yok')) return 'Yüksek';
  if (t.includes('schema') || t.includes('og') || t.includes('open graph')) return 'Orta';
  if (t.includes('telefon') || t.includes('adres') || t.includes('tamamla') || t.includes('instagram yok')) return 'Düşük';
  return 'Bilgi';
}

export function findingSeverity(finding: { severity?: string; title?: string } | string | null | undefined): string {
  const severity = typeof finding === 'object' && finding ? finding.severity : undefined;
  const labels: Record<string, string> = { critical: 'Kritik', high: 'Yüksek', medium: 'Orta', low: 'Düşük' };
  return (severity && labels[severity])
    || issueToSeverity(typeof finding === 'object' && finding ? finding.title : String(finding || ''));
}

export function filterLeads(leads: Lead[], key: LeadFilter): Lead[] {
  if (key === 'a') return leads.filter(l => scoreIsAvailable(l) && l.scoring.grade === 'A');
  if (key === 'b') return leads.filter(l => scoreIsAvailable(l) && l.scoring.grade !== 'A');
  if (key === 'web') return leads.filter(l => (l.audit_findings || []).some(f => ['website.absent', 'website.invalid_candidate'].includes(f.code || '')));
  if (key === 'ig') return leads.filter(l => (l.audit_findings || []).some(f => f.code === 'social.instagram_absent'));
  if (key === 'sicak') return leads.filter(l => (l.sales_priority_score || 0) >= 85);
  return leads;
}

export function searchLeads(rows: Lead[], query: string): Lead[] {
  const term = String(query || '').trim().toLocaleLowerCase('tr-TR');
  if (!term) return rows.slice(0, 8);
  return rows.filter(lead => {
    const haystack = [
      lead.name,
      lead.city,
      lead.category,
      lead.sector,
      lead.next_action,
      lead.phone,
      lead.address,
      ...(lead.audit_findings || []).map(item => `${item.title || ''} ${item.evidence || ''}`),
      ...(lead.matched_services || []).map(item => item.name),
    ].filter(Boolean).join(' ').toLocaleLowerCase('tr-TR');
    return haystack.includes(term);
  }).slice(0, 12);
}

export function computeTabCounts(leads: Lead[], statuses: Record<string, LeadStatus>) {
  return {
    total: leads.length,
    yeni: leads.filter(l => (statuses[l.name] || 'yeni') === 'yeni').length,
    contacted: leads.filter(l => statuses[l.name] === 'contacted').length,
    converted: leads.filter(l => statuses[l.name] === 'converted').length,
    low: leads.filter(l => scoreIsAvailable(l) && l.scoring.score < 50).length,
  };
}

export function computeReadinessBuckets(leads: Lead[]) {
  return {
    readyToCall: leads.filter(lead => Boolean(lead.phone)).length,
    needsData: leads.filter(lead => needsContactCompletion(lead)).length,
    proposalReady: leads.filter(lead => Boolean(lead.ai_report) && Boolean(lead.ai_email) && Boolean(lead.matched_services?.length)).length,
  };
}

/** Leads analysed per week over the last 8 weeks, oldest first. */
export function computeWeekBuckets(leads: Lead[]): number[] {
  const now = Date.now();
  const buckets = new Array<number>(8).fill(0);
  leads.forEach(lead => {
    if (!lead.last_analyzed) return;
    const stamp = new Date(lead.last_analyzed.replace(' ', 'T')).getTime();
    if (Number.isNaN(stamp)) return;
    const weekIdx = Math.floor(Math.floor((now - stamp) / 86400000) / 7);
    if (weekIdx >= 0 && weekIdx < 8) buckets[7 - weekIdx] += 1;
  });
  return buckets;
}

export function mostCommonCity(leads: Lead[]): string {
  const counts: Record<string, number> = {};
  leads.forEach(lead => { if (lead.city) counts[lead.city] = (counts[lead.city] || 0) + 1; });
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  return entries.length ? entries[0][0] : '';
}

export function canonicalSector(lead: Lead): string {
  const stored = String(lead.sector || '').trim().toLowerCase();
  if (SECTOR_LABELS[stored]) return SECTOR_LABELS[stored];
  const category = String(lead.category || '').toLocaleLowerCase('tr-TR');
  if (/restoran|restaurant|cafe|kafe|coffee|bistro|lokanta|pastane|fırın|bakery/.test(category)) return SECTOR_LABELS.restaurant;
  if (/diş|dental|dentist|klinik|clinic|doktor|sağlık|eczane|optik/.test(category)) return SECTOR_LABELS.health;
  if (/kuaför|güzellik|beauty|spa|nail|berber|brow|lash|pilates|yoga|masaj/.test(category)) return SECTOR_LABELS.salon;
  if (/oto|otomotiv|araba|araç|kaporta|lastik|galeri|garaj/.test(category)) return SECTOR_LABELS.auto;
  if (/mağaza|market|butik|shop|store|giyim|perakende|çiçek|kitap|mobilya|depo/.test(category)) return SECTOR_LABELS.retail;
  return SECTOR_LABELS.default;
}

/** Default follow-up time for a contact outcome ('' when it needs none). */
export function followUpForOutcome(outcome: string): string {
  const days = FOLLOW_UP_DELAYS[outcome];
  return days ? daysFromNowAtTen(days) : '';
}

export function manualVerificationDefaults(lead: Lead) {
  const current = lead.manual_verification || {};
  return {
    google: {
      checked: !!current.google?.checked,
      status: current.google?.status || (lead.maps_url ? 'found' : 'unknown'),
      rating: current.google?.rating ?? '',
      review_count: current.google?.review_count ?? '',
    },
    instagram: {
      checked: !!current.instagram?.checked,
      status: current.instagram?.status || 'unknown',
      followers: current.instagram?.followers ?? '',
      post_count: current.instagram?.post_count ?? '',
      url: current.instagram?.url || lead.social?.instagram_url || '',
    },
    menu: {
      checked: !!current.menu?.checked,
      status: current.menu?.status || 'unknown',
      url: current.menu?.url || '',
    },
    website: {
      checked: !!current.website?.checked,
      status: current.website?.status || 'unknown',
      url: current.website?.url || lead.website?.website_url || '',
    },
    notes: current.notes || '',
  };
}
