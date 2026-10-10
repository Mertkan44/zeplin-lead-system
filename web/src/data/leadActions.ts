// Lead actions started from buttons: open the right source, copy a draft,
// start a call or generate the AI report, and record what happened.
import { apiRequest } from '../lib/api';
import { copyText, downloadFile, openExternal } from '../lib/browser';
import { getPrimaryActionMeta, telHref } from '../domain/lead';
import { addOutreach } from './mutations';
import type { AuditFinding, Lead } from './types';

const now = () => new Date().toISOString();

/** Runs the lead's primary action; resolves with a message for the user. */
export function startLeadAction(lead: Lead): Promise<{ feedback: string }> {
  const nextAction = lead.next_action || 'Sonraki aksiyon başlatıldı';
  const meta = getPrimaryActionMeta(lead);

  if (meta.intent === 'enrich' || meta.intent === 'verify') {
    openExternal(lead.maps_url || lead.website?.website_url || lead.social?.instagram_url);
    return addOutreach(lead.name, 'data_enrichment_started', now(), nextAction).then(() => ({
      feedback: meta.intent === 'verify'
        ? 'Doğrulama kaynağı açıldı; uygun hizmeti görüşmede netleştir.'
        : 'Veri tamamlama aksiyonu kaydedildi.',
    }));
  }

  if (meta.intent === 'generate_ai') {
    return apiRequest<{ lead?: Lead }>('/api/lead_ai', { method: 'POST', body: { name: lead.name } }).then(data => ({
      feedback: data.lead?.ai_email
        ? 'İhtiyaç raporu ve incelenebilir e-posta taslağı hazırlandı.'
        : 'İhtiyaç raporu hazırlandı. E-posta için yeterli doğrulanmış kanıt bulunmadı.',
    }));
  }

  if (meta.intent === 'draft' && lead.ai_email) {
    void copyText(lead.ai_email);
    return addOutreach(lead.name, 'email_drafted', now(), 'Hazır taslak panoya kopyalandı')
      .then(() => ({ feedback: 'Mail taslağı panoya kopyalandı.' }));
  }

  if (meta.intent === 'call' && lead.phone) {
    window.location.href = telHref(lead.phone);
    return addOutreach(lead.name, 'call_started', now(), nextAction)
      .then(() => ({ feedback: 'Arama ekranı açıldı. Görüşme bitince sonucu ayrıca kaydet.' }));
  }

  return addOutreach(lead.name, 'email_drafted', now(), nextAction).then(() => ({ feedback: 'Aksiyon kaydedildi.' }));
}

/** Opens the most useful source for the lead without recording anything. */
export function triggerQuickLeadAction(lead: Lead): void {
  const meta = getPrimaryActionMeta(lead);
  if (meta.intent === 'call' && lead.phone) {
    openExternal(telHref(lead.phone));
    return;
  }
  if (meta.intent === 'draft' && lead.ai_email) {
    void copyText(lead.ai_email);
    return;
  }
  if (meta.intent === 'enrich') {
    openExternal(lead.maps_url || lead.website?.website_url || lead.social?.instagram_url);
    return;
  }
  openExternal(lead.website?.website_url || lead.maps_url || lead.social?.instagram_url);
}

/** Records that a call was started from a tel: link (the link itself dials). */
export function recordCallStarted(lead: Lead): void {
  addOutreach(lead.name, 'call_started', now(), 'Telefon bağlantısı açıldı').catch(() => {});
}

/** Copies the AI email draft and records it; resolves once both are done. */
export function copyEmailDraft(lead: Lead): Promise<void> {
  return copyText(lead.ai_email || '').then(() => addOutreach(lead.name, 'email_drafted', now(), 'Taslak panoya kopyalandı'));
}

/** Opens a finding's source and copies its text; returns a message for the user. */
export function openFixContext(lead: Lead, issue: AuditFinding | string | null): string {
  const target = (typeof issue === 'object' && issue?.source_url) || lead.website?.website_url || lead.maps_url || lead.social?.instagram_url;
  const issueText = typeof issue === 'string'
    ? issue
    : [issue?.title, issue?.evidence, issue?.verification].filter(Boolean).join(' — ');
  if (issue) void copyText(`${lead.name}: ${issueText}`);
  if (target) {
    openExternal(target);
    return 'Doğrulama kaynağı yeni sekmede açıldı.';
  }
  return `${lead.name} için açılabilecek doğrulama kaynağı bulunamadı.`;
}

/** Saves an internal call-preparation note as a text file and records it. */
export function createProposal(lead: Lead): Promise<void> {
  const recommendation = lead.recommended_package || {};
  const primary = (lead.matched_services || [])[0] || ({} as Partial<NonNullable<Lead['matched_services']>[number]>);
  const bullets = (items: string[] | undefined, limit?: number) => (items || []).slice(0, limit).map(item => `- ${item}`).join('\n');
  const text = [
    `ZEPLIN MEDIA GÖRÜŞME HAZIRLIK NOTU`,
    `İşletme: ${lead.name}`,
    `Önerilen hizmet: ${recommendation.primary_service || recommendation.name || 'Görüşmede netleştirilecek'}`,
    `Durum: ${recommendation.stage || 'Keşif'}`,
    ``,
    `DOĞRULANAN AÇIKLAR`,
    bullets(primary.evidence || recommendation.evidence) || `- Yeterli kanıt yok; önce veri doğrulanmalı.`,
    ``,
    `SUNABİLECEĞİMİZ İŞLER`,
    bullets(primary.deliverables || recommendation.deliverables, 3) || `- İhtiyaç görüşmesinde netleştirilecek.`,
    ``,
    `GÖRÜŞMEDE SOR`,
    bullets(primary.discovery_questions || recommendation.discovery_questions, 3) || `- İşletmenin öncelikli hedefi ve mevcut süreci nedir?`,
    ``,
    `Bu belge iç hazırlık notudur; müşteriye teklif olarak gönderilmez.`,
  ].join('\n');
  downloadFile(`${lead.name.replace(/[^\wçğıöşüÇĞİÖŞÜ-]+/g, '-')}-gorusme-notu.txt`, text, 'text/plain;charset=utf-8');
  return addOutreach(lead.name, 'proposal_created', now(), recommendation.name || 'Görüşme notu');
}
