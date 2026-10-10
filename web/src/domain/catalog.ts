// Fixed vocabularies: lead statuses, activity kinds, pipeline stages, contact
// options and user-facing messages for API codes.
import { appConfig } from '../lib/config';
import type { LeadStatus } from '../data/types';

/** Services and follow-up delays come from the Python source of truth. */
export const SERVICES = appConfig.services;
/** Default follow-up delay in days per contact outcome (src/activity.py). */
export const FOLLOW_UP_DELAYS = appConfig.followUpDelays;

export interface StatusMeta {
  label: string;
}

/** Colors per status live in ui/Badge.module.css (one readable pair per theme). */
export const STATUS_META: Record<LeadStatus, StatusMeta> = {
  yeni: { label: 'Yeni' },
  missing_info: { label: 'Veri Eksik' },
  ready: { label: 'Hazır' },
  contacted: { label: 'Görüşüldü' },
  follow_up: { label: 'Takipte' },
  converted: { label: 'Müşteri' },
  lost: { label: 'Kaybedildi' },
};

export function normalizeStatus(status: string | null | undefined): LeadStatus {
  return status && status in STATUS_META ? (status as LeadStatus) : 'yeni';
}

export function statusMeta(status: string | null | undefined): StatusMeta {
  return STATUS_META[normalizeStatus(status)];
}

export const STATUS_OPTIONS: Array<[LeadStatus, string]> = [
  ['yeni', 'Yeni'],
  ['missing_info', 'Veri eksik'],
  ['ready', 'Hazır'],
  ['contacted', 'Temasta'],
  ['follow_up', 'Takipte'],
  ['converted', 'Kazanıldı'],
  ['lost', 'Kaybedildi'],
];

export interface ActionMeta {
  label: string;
  icon: string;
  /** Status the lead moves to when this activity is recorded, if any. */
  status: LeadStatus | null;
}

export const ACTIONS: Record<string, ActionMeta> = {
  data_enrichment_started:   { label: 'Veri Tamamlama Başladı',    icon: '🧭', status: null },
  email_drafted:             { label: 'Mail Taslağı Hazır',        icon: '📝', status: null },
  outreach_review_started:   { label: 'Aksiyon İnceleniyor',       icon: '🗂️', status: null },
  draft_reviewed:            { label: 'Taslak Onaylandı',          icon: '✓',  status: null },
  manual_verification_saved: { label: 'Manuel Kontrol Tamamlandı', icon: '✓',  status: null },
  email_sent:                { label: 'Mail Gönderildi',           icon: '✉️', status: 'contacted' },
  reply_received:            { label: 'Cevap Alındı',              icon: '💬', status: 'contacted' },
  call_started:              { label: 'Arama Başlatıldı',          icon: '📞', status: null },
  call_completed:            { label: 'Arama Tamamlandı',          icon: '📞', status: 'contacted' },
  contact_result_recorded:   { label: 'Temas Sonucu Kaydedildi',   icon: '✓',  status: null },
  follow_up_scheduled:       { label: 'Takip Planlandı',           icon: '📅', status: 'follow_up' },
  note_added:                { label: 'Not Eklendi',               icon: '📝', status: null },
  proposal_created:          { label: 'Teklif Taslağı Hazır',      icon: '📄', status: null },
  proposal_sent:             { label: 'Teklif Gönderildi',         icon: '📤', status: 'contacted' },
  deal_won:                  { label: 'Anlaşma Yapıldı 🎉',        icon: '🎉', status: 'converted' },
  deal_lost:                 { label: 'Anlaşma Düştü',             icon: '❌', status: 'lost' },
  opportunity_stage_changed: { label: 'Fırsat Aşaması Değişti',    icon: '→',  status: null },
};

export function actionMeta(action: string): ActionMeta {
  return ACTIONS[action] || ACTIONS.note_added;
}

export type PipelineStageKey = 'new' | 'enrich' | 'draft' | 'contacted' | 'meeting' | 'won' | 'lost';

export interface PipelineStage {
  key: PipelineStageKey;
  label: string;
  color: string;
  /** Activity recorded when a card is dropped on this stage. */
  actions: string[];
}

export const PIPE_STAGES: PipelineStage[] = [
  { key: 'new',       label: 'Yeni',           color: '#93938f', actions: [] },
  { key: 'enrich',    label: 'Veri Tamamlama', color: '#ffb36b', actions: ['data_enrichment_started'] },
  { key: 'draft',     label: 'Taslak Hazır',   color: '#76a6ff', actions: ['email_drafted'] },
  { key: 'contacted', label: 'Temasta',        color: '#b9a8ff', actions: [] },
  { key: 'meeting',   label: 'Takip',          color: '#ff9f43', actions: ['follow_up_scheduled'] },
  { key: 'won',       label: 'Kazanıldı',      color: '#7ce2b5', actions: ['deal_won'] },
  { key: 'lost',      label: 'Kaybedildi',     color: '#ff6770', actions: ['deal_lost'] },
];

export const CONTACT_CHANNEL_OPTIONS: Array<[string, string]> = [
  ['phone', 'Telefon'],
  ['whatsapp', 'WhatsApp'],
  ['instagram', 'Instagram'],
  ['email', 'E-posta'],
  ['other', 'Diğer'],
];

export const CONTACT_OUTCOME_OPTIONS: Array<[string, string]> = [
  ['reached_interested', 'İlgilendi'],
  ['proposal_requested', 'Teklif istedi'],
  ['reached_later', 'Sonra görüşelim'],
  ['no_answer', 'Ulaşılamadı'],
  ['wrong_number', 'Numara yanlış'],
  ['not_interested', 'İlgilenmedi'],
  ['won', 'Anlaşma yapıldı'],
  ['lost', 'Kaybedildi'],
];

export const GRADE_COLORS: Record<string, string> = { A: '#b6f24a', B: '#ffcf4a', C: '#ff8f4a', D: '#7a7a78' };

export function gradeColor(grade: string | null | undefined): string {
  return (grade && GRADE_COLORS[grade]) || '#93938f';
}

export type LeadFilter = 'hepsi' | 'a' | 'b' | 'web' | 'ig' | 'sicak';

export const FILTER_DEFS: Array<[LeadFilter, string]> = [
  ['hepsi', 'Hepsi'],
  ['a', 'A Sınıfı'],
  ['b', 'B/C/D'],
  ['web', 'Web Yok'],
  ['ig', 'Instagram Yok'],
  ['sicak', '🔥 Sıcak'],
];

// A report that is not known to match the current data is readable, never "current".
export const AI_STATE_NOTES: Record<string, string> = {
  stale: 'Bu rapor işletme verisi değişmeden önce üretildi; güncel değil. Yenilemek için “Raporu yenile”.',
  unknown: 'Bu raporun hangi veriyle üretildiği kayıtlı değil; güncelliği doğrulanamıyor.',
};

export const PLACE_REASONS: Record<string, string> = {
  close_candidates: 'Google’da birden fazla benzer işletme var; doğru şubeyi seç.',
  other_district: 'Aynı isimli işletme başka bir ilçede görünüyor; doğruysa seç.',
  location_unknown: 'Adayın konumu doğrulanamadı; doğruysa seç.',
  name_differs: 'Telefon veya website eşleşiyor ama isim farklı; doğruysa seç.',
  place_owned_by_other_lead: 'Bu Google kaydı başka bir lead’e bağlı; muhtemelen mükerrer kayıt. Yöneticiye bildir.',
  location_conflict: 'Aynı isimli işletme başka şehirde bulundu; eşleştirilmedi.',
  name_mismatch: 'Google’da bu isimle eşleşen işletme bulunamadı; manuel kontrol et.',
  no_candidates: 'Google’da sonuç bulunamadı; manuel kontrol et.',
  place_not_found: 'Seçilen Google kaydı artık yok; verileri yeniden yenile.',
};

export const FACT_LABELS: Record<string, string> = {
  website_url: 'Website',
  instagram_url: 'Instagram',
  phone: 'Telefon',
  rating: 'Google puanı',
  review_count: 'Yorum sayısı',
  maps_url: 'Maps bağlantısı',
  address: 'Adres',
  menu_url: 'Menü',
};

export const FACT_SOURCES: Record<string, string> = { manual: 'Ekip kontrolü', google_places: 'Google Places', scrape: 'Tarama' };

/** Messages for the error codes POST /api/outreach returns. */
export const OUTREACH_ERRORS: Record<string, string> = {
  LEAD_VERSION_CONFLICT: 'Bu lead sen formu doldururken başka bir işlemle güncellendi. Güncel veriyi alıp tekrar kaydet.',
  LEAD_NOT_ASSIGNED: 'Bu lead artık sana atanmış değil; sonuç kaydedilmedi.',
  LEAD_NOT_FOUND: 'Lead bulunamadı; silinmiş veya birleştirilmiş olabilir.',
  IDEMPOTENCY_KEY_REUSED: 'Form değişti; tekrar kaydet.',
  OPPORTUNITY_REOPEN_REQUIRED: 'Bu fırsat kapanmış. Yeni görüşme kaydetmeden önce yönetici yeniden açmalı.',
};

export function roleLabel(role: string | null | undefined): string {
  return role === 'admin' ? 'Patron' : 'Çalışan';
}
