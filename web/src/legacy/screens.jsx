// Dashboard screens still on legacy inline styles, moved unchanged from the
// runtime-compiled template. Data comes from the query cache (data/), rules
// from domain/; each screen moves to a typed module with CSS, then leaves
// this file (WP09 stage 2).
import * as React from 'react';

import { apiRequest, ApiError, fetchAdminJSON } from '../lib/api';
import { newRequestId, openExternal } from '../lib/browser';
import {
  ACTIONS,
  AI_STATE_NOTES,
  FACT_LABELS,
  FACT_SOURCES,
  GRADE_COLORS,
  PIPE_STAGES,
  PLACE_REASONS,
  SERVICES as services,
  STATUS_OPTIONS,
  roleLabel,
} from '../domain/catalog';
import { fmt, fmtDate, initialsFor } from '../domain/format';
import {
  canonicalSector,
  computeReadinessBuckets,
  computeTabCounts,
  findingSeverity,
  getLeadReadiness,
  getPipelineStage,
  getPrimaryActionMeta,
  manualVerificationDefaults,
  scoreIsAvailable,
  verifiedInstagram,
} from '../domain/lead';
import {
  copyEmailDraft,
  openFixContext,
  recordCallStarted,
  startLeadAction,
  triggerQuickLeadAction,
} from '../data/leadActions';
import {
  addOutreach,
  saveDraftReview,
  saveManualVerification,
  setLeadStatus,
} from '../data/mutations';
import { mergeEvents, useCrm, useLeadTimeline, useSession } from '../data/workspace';

function roleTone(role) {
  return role === 'admin'
    ? { bg: 'var(--accent)', fg: 'var(--accent-ink)', bd: 'transparent' }
    : { bg: 'var(--raised)', fg: 'var(--sub)', bd: 'var(--line)' };
}

function scoreDash(score) { return 326.7 * (1 - score / 100); }

function sevStyle(s) {
  return ({ Kritik: { background: 'rgba(255,107,107,0.14)', color: '#ff8f8f' }, Yüksek: { background: 'rgba(255,159,67,0.14)', color: '#ffb36b' }, Orta: { background: 'rgba(255,207,74,0.14)', color: '#ffcf4a' }, Düşük: { background: 'rgba(124,197,255,0.14)', color: '#7cc5ff' }, Bilgi: { background: 'var(--raised)', color: 'var(--sub)' } })[s] || { background: 'var(--raised)', color: 'var(--sub)' };
}

const factValue = fact => fact.status === 'absent' ? 'yok' : String(fact.value ?? '—');

function ManualVerificationCard({ lead, onDataChange, onFeedback, placesEnabled }) {
  const [values, setValues] = React.useState(() => manualVerificationDefaults(lead));
  const [busy, setBusy] = React.useState(false);
  const [placesBusy, setPlacesBusy] = React.useState(false);
  const [placeChoice, setPlaceChoice] = React.useState(null);
  const current = lead.manual_verification || null;
  const storedAttempt = lead.research?.google_places?.last_attempt;
  const choice = placeChoice || (storedAttempt?.status === 'ambiguous' ? storedAttempt : null);
  const candidates = placesEnabled ? (choice?.candidates || []) : [];
  // Conflicts between sources, and team/Places data past its re-check date.
  const factIssues = Object.entries(lead.facts || {}).filter(([, fact]) => (fact.conflicts || []).length || (fact.stale && fact.source !== 'scrape'));

  React.useEffect(() => setPlaceChoice(null), [lead.name]);

  React.useEffect(() => setValues(manualVerificationDefaults(lead)), [lead.name, current?.checked_at]);

  function update(group, field, value) {
    setValues(previous => ({
      ...previous,
      [group]: { ...previous[group], [field]: value },
    }));
  }

  function submit(event) {
    event.preventDefault();
    if (!['google', 'instagram', 'menu', 'website'].some(group => values[group].checked)) {
      onFeedback('Kaydetmek için en az bir alanı kontrol edildi olarak işaretle.');
      return;
    }
    setBusy(true);
    saveManualVerification(lead, values).then(() => {
      onFeedback('Manuel kontrol kaydedildi; öneriler güncellendi.');
      if (onDataChange) return onDataChange();
    }).catch(() => onFeedback('Manuel kontrol kaydedilemedi.')).finally(() => setBusy(false));
  }

  function refreshGooglePlace(placeId) {
    setPlacesBusy(true);
    apiRequest('/api/place_refresh', {
      method: 'POST',
      body: placeId ? { lead_name: lead.name, place_id: placeId } : { lead_name: lead.name },
    }).catch(err => {
      throw new Error((err instanceof ApiError && err.data.error) || 'Google verisi yenilenemedi.');
    }).then(data => {
      const place = data.place || {};
      if (place.status === 'verified') {
        setPlaceChoice(null);
        onFeedback(place.match_method === 'text_search'
          ? `Google verisi yenilendi · %${place.match_confidence || 0} eşleşme güveni.`
          : 'Google verisi kayıtlı işletme üzerinden yenilendi.');
      } else if (place.status === 'ambiguous') {
        setPlaceChoice(place);
        onFeedback(PLACE_REASONS[place.reason] || 'Google sonucu belirsiz; doğru işletmeyi seç.');
      } else {
        setPlaceChoice(null);
        throw new Error(PLACE_REASONS[place.reason] || 'Google’da güvenilir işletme eşleşmesi bulunamadı; manuel kontrol et.');
      }
      if (onDataChange) return onDataChange();
    }).catch(error => onFeedback(error.message || 'Google verisi yenilenemedi.')).finally(() => setPlacesBusy(false));
  }

  const sourceButton = (url, label) => url ? (
    <button type="button" style={ld.manualSource} onClick={() => openExternal(url)}>{label} ↗</button>
  ) : null;
  const sectionStyle = checked => ({ ...ld.manualSection, opacity: checked ? 1 : 0.72 });

  return (
    <form style={ld.manualCard} onSubmit={submit}>
      <div style={ld.findHeader}>
        <div>
          <div style={ld.eyebrow}>EKİP DOĞRULAMASI</div>
          <div style={ld.cardTitle}>Kaynakları aç, gördüğünü kaydet</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
          {placesEnabled && <button type="button" disabled={placesBusy} style={ld.btnGhost} onClick={refreshGooglePlace}>{placesBusy ? 'Google yenileniyor…' : 'Google verisini yenile'}</button>}
          {current?.checked_at ? (
            <span style={ld.verifiedBadge}>{fmtDate(current.checked_at)} · {current.checked_by || 'Ekip'}</span>
          ) : <span style={ld.countBadge}>Henüz yapılmadı</span>}
        </div>
      </div>
      {candidates.length > 0 && (
        <div style={ld.placeChoices}>
          <div style={ld.placeChoiceHint}>{PLACE_REASONS[choice?.reason] || 'Google sonucu belirsiz; doğru işletmeyi seç.'}</div>
          {candidates.map(candidate => (
            <div key={candidate.place_id} style={ld.placeChoice}>
              <div style={{ minWidth: 0 }}>
                <strong>{candidate.display_name || 'İsimsiz kayıt'}</strong>
                <div style={ld.placeChoiceMeta}>{[candidate.formatted_address, candidate.phone].filter(Boolean).join(' · ')}</div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
                {sourceButton(candidate.maps_url, 'Maps')}
                <button type="button" disabled={placesBusy} style={ld.btnGhost} onClick={() => refreshGooglePlace(candidate.place_id)}>Bu işletme</button>
              </div>
            </div>
          ))}
        </div>
      )}
      {factIssues.length > 0 && (
        <div style={ld.factIssues}>
          {factIssues.map(([key, fact]) => (
            <div key={key}>
              <strong>{FACT_LABELS[key] || key}:</strong> {factValue(fact)}{' '}
              <span style={{ opacity: .8 }}>({FACT_SOURCES[fact.source] || fact.source}{fact.observed_at ? `, ${fmtDate(fact.observed_at)}` : ''}{fact.stale ? ', yeniden kontrol et' : ''})</span>
              {(fact.conflicts || []).map((other, index) => (
                <span key={index}> · {FACT_SOURCES[other.source] || other.source} farklı diyor: {factValue(other)}</span>
              ))}
            </div>
          ))}
        </div>
      )}
      <div className="manual-verification-grid" style={ld.manualGrid}>
        <section style={sectionStyle(values.google.checked)}>
          <div style={ld.manualSectionHead}>
            <label style={ld.manualCheck}><input type="checkbox" checked={values.google.checked} onChange={event => update('google', 'checked', event.target.checked)}/><strong>Google Maps</strong></label>
            {sourceButton(lead.maps_url, 'Maps aç')}
          </div>
          <select aria-label="Google profil durumu" disabled={!values.google.checked} value={values.google.status} onChange={event => update('google', 'status', event.target.value)} style={ld.manualInput}>
            <option value="found">Profil bulundu</option><option value="not_found">Profil bulunamadı</option><option value="unknown">Sonuç belirsiz</option>
          </select>
          <div className="manual-field-grid" style={ld.manualFields}>
            <input aria-label="Google puanı" disabled={!values.google.checked} type="number" min="0" max="5" step="0.1" placeholder="Puan (4.3)" value={values.google.rating} onChange={event => update('google', 'rating', event.target.value)} style={ld.manualInput}/>
            <input aria-label="Google yorum sayısı" disabled={!values.google.checked} type="number" min="0" placeholder="Yorum sayısı" value={values.google.review_count} onChange={event => update('google', 'review_count', event.target.value)} style={ld.manualInput}/>
          </div>
        </section>

        <section style={sectionStyle(values.instagram.checked)}>
          <div style={ld.manualSectionHead}>
            <label style={ld.manualCheck}><input type="checkbox" checked={values.instagram.checked} onChange={event => update('instagram', 'checked', event.target.checked)}/><strong>Instagram</strong></label>
            {sourceButton(values.instagram.url || lead.social?.instagram_url, 'Instagram aç')}
          </div>
          <select aria-label="Instagram durumu" disabled={!values.instagram.checked} value={values.instagram.status} onChange={event => update('instagram', 'status', event.target.value)} style={ld.manualInput}>
            <option value="active">Aktif kullanılıyor</option><option value="inactive">Uzun süredir pasif</option><option value="not_found">Hesap bulunamadı</option><option value="unknown">Sonuç belirsiz</option>
          </select>
          <div className="manual-field-grid" style={ld.manualFields}>
            <input aria-label="Instagram takipçi sayısı" disabled={!values.instagram.checked} type="number" min="0" placeholder="Takipçi" value={values.instagram.followers} onChange={event => update('instagram', 'followers', event.target.value)} style={ld.manualInput}/>
            <input aria-label="Instagram gönderi sayısı" disabled={!values.instagram.checked} type="number" min="0" placeholder="Gönderi" value={values.instagram.post_count} onChange={event => update('instagram', 'post_count', event.target.value)} style={ld.manualInput}/>
          </div>
          <input aria-label="Instagram URL" disabled={!values.instagram.checked} placeholder="Instagram profil URL" value={values.instagram.url} onChange={event => update('instagram', 'url', event.target.value)} style={ld.manualInput}/>
        </section>

        <section style={sectionStyle(values.menu.checked)}>
          <div style={ld.manualSectionHead}>
            <label style={ld.manualCheck}><input type="checkbox" checked={values.menu.checked} onChange={event => update('menu', 'checked', event.target.checked)}/><strong>Menü</strong></label>
            {sourceButton(values.menu.url, 'Menüyü aç')}
          </div>
          <select aria-label="Menü durumu" disabled={!values.menu.checked} value={values.menu.status} onChange={event => update('menu', 'status', event.target.value)} style={ld.manualInput}>
            <option value="current">Güncel ve yeterli</option><option value="outdated">Eski / görseller yetersiz</option><option value="not_found">Dijital menü yok</option><option value="unknown">Sonuç belirsiz</option>
          </select>
          <input aria-label="Menü URL" disabled={!values.menu.checked} placeholder="Menü URL (varsa)" value={values.menu.url} onChange={event => update('menu', 'url', event.target.value)} style={ld.manualInput}/>
        </section>

        <section style={sectionStyle(values.website.checked)}>
          <div style={ld.manualSectionHead}>
            <label style={ld.manualCheck}><input type="checkbox" checked={values.website.checked} onChange={event => update('website', 'checked', event.target.checked)}/><strong>Website</strong></label>
            {sourceButton(values.website.url || lead.website?.website_url, 'Siteyi aç')}
          </div>
          <select aria-label="Website durumu" disabled={!values.website.checked} value={values.website.status} onChange={event => update('website', 'status', event.target.value)} style={ld.manualInput}>
            <option value="working">Çalışıyor ve güncel</option><option value="outdated">Eski / yetersiz</option><option value="not_found">Website yok</option><option value="unknown">Sonuç belirsiz</option>
          </select>
          <input aria-label="Website URL" disabled={!values.website.checked} placeholder="Website URL (varsa)" value={values.website.url} onChange={event => update('website', 'url', event.target.value)} style={ld.manualInput}/>
        </section>
      </div>
      <div style={ld.manualFooter}>
        <textarea aria-label="Manuel kontrol notu" placeholder="Kısa ekip notu (isteğe bağlı)" value={values.notes} onChange={event => setValues(previous => ({ ...previous, notes: event.target.value }))} style={ld.manualNote}/>
        <button type="submit" disabled={busy} style={{ ...ld.btnDark, opacity: busy ? .6 : 1 }}>{busy ? 'Kaydediliyor…' : 'Doğrulamayı kaydet'}</button>
      </div>
    </form>
  );
}

function ResearchBriefCard({ brief }) {
  if (!brief) return null;
  const gaps = [...(brief.confirmed_gaps || []), ...(brief.likely_gaps || [])];
  const manualFacts = brief.manual_facts || [];
  const unknowns = brief.manual_checks || brief.unknowns || [];
  const tone = brief.status === 'ready' ? ld.verifiedBadge : brief.status === 'partial' ? ld.discoveryBadge : ld.countBadge;
  return (
    <section style={ld.researchCard}>
      <div style={ld.findHeader}>
        <div>
          <div style={ld.eyebrow}>ARAŞTIRMA DOSYASI</div>
          <div style={ld.cardTitle}>Ne biliyoruz, neyi hâlâ sormalıyız?</div>
        </div>
        <span style={tone}>{brief.status_label}</span>
      </div>
      <div className="responsive-stats lead-research-stats" style={ld.researchStats}>
        <div style={ld.researchStat}><strong>{brief.counts?.confirmed || 0}</strong><span>Doğrulanmış açık</span></div>
        <div style={ld.researchStat}><strong>{brief.counts?.opportunities || 0}</strong><span>Fırsat sinyali</span></div>
        <div style={ld.researchStat}><strong>%{brief.coverage || 0}</strong><span>Tarama kapsamı</span></div>
        <div style={ld.researchStat}><strong>{brief.source_count || 0}</strong><span>Kaynak</span></div>
      </div>
      {brief.stale && <div style={ld.researchWarning}>Araştırma 30 günden eski veya tarihsiz. Temastan önce kaynakları yeniden kontrol et.</div>}
      {manualFacts.length > 0 && <div style={ld.manualFactStrip}>{manualFacts.map(item => <span key={item.code}><strong>{item.title}:</strong> {item.evidence}</span>)}</div>}
      <div className="responsive-opportunity-columns lead-research-columns" style={ld.researchColumns}>
        <div>
          <div style={ld.miniLabel}>MÜŞTERİYE SÖYLENEBİLİR</div>
          {gaps.length ? gaps.slice(0, 4).map((item, index) => (
            <div key={`${item.code}-${index}`} style={ld.researchRow}>
              <div style={ld.researchRowHead}><strong>{item.title}</strong><span>%{item.confidence}</span></div>
              <p style={ld.researchEvidence}>{item.evidence}</p>
              <div style={ld.researchSource}>
                <span>{item.source_label}</span>
                {item.source_url && <button type="button" style={ld.researchLink} onClick={() => openExternal(item.source_url)}>Kaynağı aç</button>}
              </div>
            </div>
          )) : <div style={ld.emptyResearch}>Kesin açık bulunmadı. Satış iddiası yerine keşif sorularını kullan.</div>}
        </div>
        <div>
          <div style={ld.miniLabel}>GÖRÜŞMEDE DOĞRULA</div>
          {unknowns.length ? unknowns.slice(0, 5).map((item, index) => (
            <div key={`${item.code || item.title}-${index}`} style={ld.manualRow}>
              <strong>{item.title}</strong>
              <span>{item.next_step || item.note}</span>
              {item.source_url && <button type="button" style={ld.researchLink} onClick={() => openExternal(item.source_url)}>Kontrol et</button>}
            </div>
          )) : <div style={ld.emptyResearch}>Bekleyen manuel kontrol yok.</div>}
        </div>
      </div>
      <div style={ld.guardrail}>{brief.guardrail}</div>
    </section>
  );
}

function CommunicationCenter({ lead, playbook, onFeedback, onDataChange }) {
  const sourceDrafts = playbook.channel_drafts || [];
  const firstChannel = sourceDrafts.find(item => item.recipient_available)?.channel || sourceDrafts[0]?.channel || 'phone';
  const [activeChannel, setActiveChannel] = React.useState(firstChannel);
  const [drafts, setDrafts] = React.useState(() => Object.fromEntries(sourceDrafts.map(item => [item.channel, { ...item }])));
  const [busy, setBusy] = React.useState(false);
  const [approved, setApproved] = React.useState({});

  React.useEffect(() => {
    const rows = playbook.channel_drafts || [];
    const next = Object.fromEntries(rows.map(item => [item.channel, { ...item }]));
    setDrafts(next);
    setActiveChannel(rows.find(item => item.recipient_available)?.channel || rows[0]?.channel || 'phone');
    setApproved({});
  }, [lead.name, playbook.version]);

  const draft = drafts[activeChannel];
  if (!draft) return null;

  function updateDraft(field, value) {
    setDrafts(current => ({ ...current, [activeChannel]: { ...current[activeChannel], [field]: value } }));
    setApproved(current => ({ ...current, [activeChannel]: false }));
  }

  function copyDraft() {
    const text = draft.subject ? `Konu: ${draft.subject}\n\n${draft.body}` : draft.body;
    if (!navigator.clipboard?.writeText) return;
    navigator.clipboard.writeText(text).then(() => onFeedback(`${draft.label} taslağı kopyalandı.`));
  }

  function approveDraft() {
    if (!draft.body?.trim()) return;
    setBusy(true);
    saveDraftReview(lead, draft).then(() => {
      setApproved(current => ({ ...current, [activeChannel]: true }));
      onFeedback(`${draft.label} taslağı onaylandı; henüz gönderilmedi.`);
      if (onDataChange) onDataChange();
    }).catch(() => onFeedback('Taslak onayı kaydedilemedi.')).finally(() => setBusy(false));
  }

  return (
    <div className="lead-comms" style={ld.comms}>
      <div className="lead-comms-head" style={ld.commsHead}>
        <div>
          <div style={ld.miniLabel}>İLETİŞİM MERKEZİ</div>
          <strong>Metni kontrol et, düzenle ve onayla</strong>
        </div>
        <span style={ld.notSentBadge}>Otomatik gönderilmez</span>
      </div>
      <div className="hide-sb lead-channel-tabs" style={ld.channelTabs}>
        {sourceDrafts.map(item => (
          <button type="button" key={item.channel} style={activeChannel === item.channel ? ld.channelTabActive : ld.channelTab} onClick={() => setActiveChannel(item.channel)}>
            <span style={{ ...ld.channelDot, background: item.recipient_available ? 'var(--accent)' : 'var(--muted)' }}/>
            {item.label}
          </button>
        ))}
      </div>
      <div style={ld.draftMeta}>
        <span>{draft.recipient_available ? (draft.recipient || 'İletişim kanalı hazır') : 'Alıcı/kanal bilgisi eksik'}</span>
        <span>{playbook.discovery_only ? 'Keşif dili' : 'Kanıta dayalı dil'}</span>
      </div>
      {draft.subject !== undefined && (
        <input aria-label="E-posta konusu" value={draft.subject || ''} onChange={event => updateDraft('subject', event.target.value)} style={ld.draftSubject}/>
      )}
      <textarea aria-label={`${draft.label} taslağı`} value={draft.body || ''} onChange={event => updateDraft('body', event.target.value)} style={ld.draftEditor}/>
      <div style={ld.draftReview}><strong>Göndermeden önce:</strong> {draft.review_note}</div>
      <div className="lead-draft-footer" style={ld.draftFooter}>
        <span>{(draft.body || '').length} karakter</span>
        <div style={{ display: 'flex', gap: 8 }}>
          <button type="button" style={ld.btnGhost} onClick={copyDraft}>Kopyala</button>
          <button type="button" style={{ ...ld.btnDark, opacity: busy || !draft.body?.trim() ? 0.55 : 1 }} onClick={approveDraft} disabled={busy || !draft.body?.trim()}>
            {approved[activeChannel] ? 'Onaylandı' : busy ? 'Kaydediliyor…' : 'Taslağı onayla'}
          </button>
        </div>
      </div>
    </div>
  );
}

function LeadDetail({ lead, idx, total, status, onStatusChange, onBack, onPrev, onNext, onDataChange, onOpenResult, integrations }) {
  const [showReport, setShowReport] = React.useState(false);
  const [showEmail,  setShowEmail]  = React.useState(false);
  const [copied,     setCopied]     = React.useState(false);
  const [note,       setNote]       = React.useState('');
  const noteRequestRef = React.useRef(null);
  const [feedback,   setFeedback]   = React.useState('');

  // The workspace carries the last 30 days of events; this adds the lead's full timeline.
  const crm = useCrm();
  const { user } = useSession();
  const timeline = useLeadTimeline(user.email, lead.name);
  const [busy,       setBusy]       = React.useState(false);
  const findings   = lead.audit_findings || [];
  const opportunityFindings = findings.filter(finding => finding.finding_type === 'opportunity');
  const gapFindings = findings.filter(finding => finding.finding_type !== 'opportunity');
  const unknownChecks = (lead.audit_checks || []).filter(check => check.status === 'unknown');
  const serviceMatches = lead.matched_services || [];
  const discoveryMatches = lead.discovery_services || [];
  const displayedServices = serviceMatches.length > 0 ? serviceMatches : discoveryMatches;
  const hasRecommendation = displayedServices.length > 0;
  const isDiscoveryOnly = serviceMatches.length === 0;
  const svc = lead.recommended_package || {};
  const events     = mergeEvents(crm.eventsFor(lead.name), timeline.data || []);
  const actionMeta = getPrimaryActionMeta(lead);
  const readiness  = getLeadReadiness(lead);
  const lastEvent  = events[0] || null;
  const socialVerified = verifiedInstagram(lead);
  const manualInstagram = lead.manual_verification?.instagram?.checked
    ? lead.manual_verification.instagram
    : null;
  const socialStatsVerified = socialVerified
    && lead.social?.stats?.lookup_status === 'found';
  const scoreAvailable = scoreIsAvailable(lead);
  const playbook = lead.sales_playbook || {};
  const researchBrief = lead.research_brief_v2 || null;
  const workflow = lead.workflow || {};
  const contactReady = Boolean(workflow.ready_to_contact || workflow.latest_contact_at);

  function copyEmail() {
    copyEmailDraft(lead).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000); });
  }

  function copySalesText(text, label) {
    if (!text || !navigator.clipboard?.writeText) return;
    navigator.clipboard.writeText(text).then(() => setFeedback(`${label} kopyalandı.`));
  }

  function saveNote() {
    const value = note.trim();
    if (!value) return;
    setBusy(true);
    // Retrying the same unsaved text reuses its id, so a save that did reach
    // the server is not stored twice.
    if (!noteRequestRef.current || noteRequestRef.current.text !== value) {
      noteRequestRef.current = { text: value, id: newRequestId() };
    }
    addOutreach(lead.name, 'note_added', new Date().toISOString(), value, noteRequestRef.current.id).then(() => {
      noteRequestRef.current = null;
      setNote('');
      setFeedback('Not kaydedildi.');
      if (onDataChange) onDataChange();
    }).catch(() => {
      setFeedback('Not kaydedilemedi; metnin duruyor. Bağlantıyı kontrol edip tekrar kaydet.');
    }).finally(() => {
      setBusy(false);
    });
  }

  function skipLead() {
    onNext();
  }

  function handlePrimaryAction() {
    setFeedback('');
    setBusy(true);
    startLeadAction(lead).then(result => {
      setFeedback((result && result.feedback) || 'Aksiyon kaydedildi.');
      if (onDataChange) onDataChange();
    }).catch(error => {
      setFeedback(error?.message || 'Aksiyon tamamlanamadı. Lütfen tekrar dene.');
    }).finally(() => {
      setBusy(false);
    });
  }

  return (
    <div className="lead-detail-root" style={ld.root}>
      <header className="lead-detail-top" style={ld.top}>
        <div style={ld.crumbs}>
          <span style={{ ...ld.crumb, cursor: 'pointer', color: 'var(--sub)' }} onClick={onBack}>Workspace</span>
          <span style={ld.crumbSep}>/</span><span style={ld.crumb}>Leadler</span>
          <span style={ld.crumbSep}>/</span>
          <span style={{ ...ld.crumb, color: 'var(--tx)', fontWeight: 600 }}>{lead.name}</span>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button style={{ ...ld.btnGhost, opacity: idx === 0 ? 0.4 : 1 }} onClick={onPrev} disabled={idx === 0}>← Önceki</button>
          <button style={{ ...ld.btnGhost, opacity: idx === total-1 ? 0.4 : 1 }} onClick={onNext} disabled={idx === total-1}>Sonraki →</button>
          <button style={ld.btnDark} onClick={onBack}>← Workspace</button>
        </div>
      </header>

      <section className="lead-detail-hero" style={ld.hero}>
        <div style={ld.heroLeft}>
          <div style={ld.statusRow}>
            <span style={ld.statusBadge}>● {(status || 'yeni').toUpperCase()}</span>
            {(lead.category || lead.sector) && <span style={ld.metaTag}>{lead.category || lead.sector}</span>}
            {lead.city && <span style={ld.metaTag}>{lead.city}</span>}
            {lead.last_analyzed && <span style={ld.metaText}>Son analiz · {fmtDate(lead.last_analyzed)}</span>}
          </div>
          <h1 style={ld.h1}>{lead.name}</h1>
          <div style={ld.urls}>
            {lead.website?.website_url && <a href={lead.website.website_url} target="_blank" rel="noopener noreferrer" style={ld.urlChip}>{lead.website.website_url.replace(/^https?:\/\//, '').replace(/\/$/, '')} ↗</a>}
            {socialVerified && lead.social?.instagram_url && <a href={lead.social.instagram_url} target="_blank" rel="noopener noreferrer" style={ld.urlChip}>@{lead.social.instagram_username || 'instagram'} ↗</a>}
            {lead.maps_url && <a href={lead.maps_url} target="_blank" rel="noopener noreferrer" style={ld.urlChip}>Google Maps ↗</a>}
            {lead.phone && <span style={ld.urlChip}>{lead.phone}</span>}
          </div>
          <div style={ld.quickActions}>
            {contactReady && lead.phone && <a href={`tel:${lead.phone.replace(/\s+/g, '')}`} onClick={() => recordCallStarted(lead)} style={ld.quickBtn}>Telefonu aç</a>}
            {lead.website?.website_url && <button style={ld.quickBtn} onClick={() => openExternal(lead.website.website_url)}>Siteyi aç</button>}
            {socialVerified && lead.social?.instagram_url && <button style={ld.quickBtn} onClick={() => openExternal(lead.social.instagram_url)}>Instagram aç</button>}
            {lead.maps_url && <button style={ld.quickBtn} onClick={() => openExternal(lead.maps_url)}>Maps aç</button>}
            {lead.ai_email && <button style={ld.quickBtn} onClick={copyEmail}>{copied ? 'Taslak kopyalandi' : 'Taslagi kopyala'}</button>}
            <button disabled={!contactReady} title={contactReady ? 'Temas ekranını aç' : 'Önce zorunlu kontrolleri tamamla'} style={{ ...ld.quickBtn, background: contactReady ? 'var(--accent)' : 'var(--raised)', color: contactReady ? 'var(--accent-ink)' : 'var(--muted)', borderColor: contactReady ? 'var(--accent)' : 'var(--line)', opacity: contactReady ? 1 : .65 }} onClick={onOpenResult}>{contactReady ? 'Temas ekranı' : `${workflow.completed_count || 0}/${workflow.required_count || 0} kontrol`}</button>
          </div>
        </div>
        <div style={ld.heroRight}>
          <div>
            <svg width="120" height="120" viewBox="0 0 120 120">
              <circle cx="60" cy="60" r="52" fill="none" stroke="var(--line2)" strokeWidth="6"/>
              <circle cx="60" cy="60" r="52" fill="none" stroke={scoreAvailable ? 'var(--accent)' : 'var(--muted)'} strokeWidth="6" strokeDasharray="326.7" strokeDashoffset={scoreAvailable ? scoreDash(lead.scoring.score) : 326.7} transform="rotate(-90 60 60)" strokeLinecap="round"/>
              <text x="60" y="60" textAnchor="middle" fontSize="32" fontWeight="600" fill="var(--tx)" fontFamily="Space Grotesk">{scoreAvailable ? lead.scoring.score : '—'}</text>
              <text x="60" y="80" textAnchor="middle" fontSize="11" fill="var(--muted)" fontFamily="Space Grotesk">{scoreAvailable ? '/100' : `%${lead.scoring?.coverage || 0} kapsam`}</text>
            </svg>
          </div>
          <div style={ld.gradePill}>{scoreAvailable ? lead.scoring.grade : '?'}</div>
        </div>
      </section>

      {lead.next_action && (
        <div style={ld.nextAction}>
          <div>
            <div style={ld.naEyebrow}>SONRAKİ EN İYİ AKSİYON · ÖNCELİK {lead.sales_priority_score || '—'}</div>
            <div style={ld.naTitle}>{lead.next_action}</div>
            {lead.priority_reason && <div style={ld.naDesc}>{lead.priority_reason}</div>}
            <div style={ld.naHelper}>{actionMeta.helper}</div>
            {feedback && <div style={ld.inlineFeedback}>{feedback}</div>}
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button style={{ ...ld.btnGhost, opacity: busy ? 0.7 : 1 }} onClick={skipLead} disabled={busy}>Atla</button>
            <button style={{ ...ld.btnDark, opacity: busy ? 0.7 : 1 }} onClick={handlePrimaryAction} disabled={busy}>{busy ? (actionMeta.intent === 'generate_ai' ? 'Rapor hazırlanıyor…' : 'Kaydediliyor…') : `${actionMeta.label} →`}</button>
          </div>
        </div>
      )}

      <section className="responsive-detail" style={ld.cols}>
        <div>
          <div style={ld.statsCard}>
            <div style={ld.statsHeader}><div style={ld.eyebrow}>SOSYAL SİNYALLER</div><div style={ld.cardTitle}>Etkileşim ve büyüme</div></div>
            <div className="responsive-stats" style={ld.statsGrid}>
              {[
                ['Instagram', manualInstagram ? 'Ekip kontrol etti' : socialVerified ? 'Doğrulandı' : 'Doğrulanmadı'],
                ['Takipçi',   manualInstagram?.followers !== null && manualInstagram?.followers !== undefined ? String(manualInstagram.followers) : socialStatsVerified && lead.social?.stats?.followers !== null ? String(lead.social.stats.followers) : '—'],
                ['Gönderi',   manualInstagram?.post_count !== null && manualInstagram?.post_count !== undefined ? String(manualInstagram.post_count) : socialStatsVerified && lead.social?.stats?.post_count !== null ? String(lead.social.stats.post_count) : '—'],
                ['Ort. beğeni',socialStatsVerified && lead.social?.stats?.avg_likes !== null ? String(lead.social.stats.avg_likes) : '—'],
                ['Etkileşim', socialStatsVerified && lead.social?.stats?.engagement_rate !== null ? `%${lead.social.stats.engagement_rate}` : '—'],
              ].map(([l, v], i) => (
                <div key={i} style={{ ...ld.stat, ...(i === 4 ? { borderRight: 'none' } : {}) }}>
                  <div style={ld.statLabel}>{l}</div>
                  <div style={ld.statVal}>{v}</div>
                </div>
              ))}
            </div>
          </div>

          <ManualVerificationCard lead={lead} onDataChange={onDataChange} onFeedback={setFeedback} placesEnabled={integrations?.google_places}/>

          <ResearchBriefCard brief={researchBrief}/>

          {playbook.summary && (
            <div style={ld.salesCard}>
              <div style={ld.findHeader}>
                <div>
                  <div style={ld.eyebrow}>SATIŞ REHBERİ</div>
                  <div style={ld.cardTitle}>Bu işletmeyle nasıl konuşacağız?</div>
                </div>
                <span style={playbook.discovery_only ? ld.discoveryBadge : ld.verifiedBadge}>
                  {playbook.discovery_only ? 'Keşif görüşmesi' : 'Kanıta dayalı'}
                </span>
              </div>
              <div style={ld.salesSummary}>{playbook.summary}</div>
              {(playbook.evidence_points || []).length > 0 && (
                <div className="lead-sales-evidence" style={ld.salesEvidenceGrid}>
                  {playbook.evidence_points.slice(0, 3).map((item, itemIndex) => (
                    <div key={`${item.title}-${itemIndex}`} style={ld.salesEvidence}>
                      <div style={ld.miniLabel}>KANIT {itemIndex + 1}</div>
                      <strong>{item.title}</strong>
                      <span>{item.evidence}</span>
                    </div>
                  ))}
                </div>
              )}
              <CommunicationCenter lead={lead} playbook={playbook} onFeedback={setFeedback} onDataChange={onDataChange}/>
              <div className="responsive-opportunity-columns lead-script-grid" style={ld.scriptGrid}>
                <div>
                  <div style={ld.miniLabel}>GÖRÜŞMEDE SOR</div>
                  <ul style={ld.cleanList}>
                    {(playbook.discovery_questions || []).slice(0, 4).map((item, itemIndex) => <li key={itemIndex}>{item}</li>)}
                  </ul>
                </div>
                <div>
                  <div style={ld.miniLabel}>İTİRAZA HAZIRLIK</div>
                  {(playbook.objection_responses || []).slice(0, 3).map((item, itemIndex) => (
                    <div key={itemIndex} style={ld.objectionRow}><strong>{item.objection}</strong><span>{item.response}</span></div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {hasRecommendation ? (
            <div style={ld.packCard}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16 }}>
                <div style={{ flex: 1 }}>
                  <div style={ld.eyebrow}>{isDiscoveryOnly ? 'GÖRÜŞMEDE DOĞRULA' : 'BİRİNCİL HİZMET ÖNERİSİ'}</div>
                  <h3 style={ld.packTitle}>{svc.primary_service || svc.name}</h3>
                  <div style={ld.packDesc}>{svc.summary || 'Öneri, doğrulanan tarama sinyallerine dayanır.'}</div>
                </div>
                <span style={svc.requires_discovery ? ld.discoveryBadge : ld.verifiedBadge}>
                  {svc.requires_discovery ? 'Görüşmede doğrula' : 'Kanıtlandı'}
                </span>
              </div>
              <div style={ld.packTags}>
                {(svc.evidence || []).map((item, i) => <span key={i} style={ld.tagPrimary}>{item}</span>)}
              </div>
            </div>
          ) : (
            <div style={{ ...ld.packCard, background: 'var(--panel2)' }}>
              <div style={ld.eyebrow}>HİZMET ÖNERİSİ</div>
              <div style={{ fontSize: 14, color: 'var(--sub)', marginTop: 8 }}>
                Henüz doğrudan satış iddiası oluşturacak bir açık doğrulanmadı. Sektöre uygun keşif sorularını kullan.
              </div>
            </div>
          )}

          {hasRecommendation && (
            <div style={ld.opportunitySection}>
              <div style={ld.findHeader}>
                <div>
                  <div style={ld.eyebrow}>{isDiscoveryOnly ? 'UYGUN OLABİLECEK HİZMETLER' : 'KANITLANAN İHTİYAÇLAR'}</div>
                  <div style={ld.cardTitle}>Ne gördük, ne sunabiliriz?</div>
                </div>
                <span style={ld.countBadge}>{isDiscoveryOnly ? `${displayedServices.length} keşif başlığı` : `${serviceMatches.length} hizmet sinyali`}</span>
              </div>
              {displayedServices.slice(0, 4).map((service, serviceIndex) => (
                <div key={service.slug || serviceIndex} style={ld.opportunityRow}>
                  <div style={ld.opportunityTop}>
                    <div>
                      <div style={ld.opportunityIndex}>0{serviceIndex + 1} · {service.category || 'Hizmet'}</div>
                      <div style={ld.opportunityTitle}>{service.name}</div>
                      <div style={ld.opportunityDesc}>{service.desc}</div>
                    </div>
                    <span style={service.requires_discovery ? ld.discoveryBadge : ld.verifiedBadge}>
                      {service.requires_discovery ? 'Kontrol et' : `%${service.confidence || 0} güven`}
                    </span>
                  </div>

                  <div className="responsive-opportunity-columns" style={ld.opportunityColumns}>
                    {(service.evidence || []).length > 0 && <div>
                      <div style={ld.miniLabel}>TESPİT EDİLEN AÇIK</div>
                      <div style={ld.evidenceList}>
                        {(service.evidence || []).map((item, i) => (
                          <div key={i} style={ld.evidenceItem}><span style={ld.evidenceDot}></span>{item}</div>
                        ))}
                      </div>
                    </div>}
                    <div>
                      <div style={ld.miniLabel}>BİZ NE TESLİM EDERİZ?</div>
                      <ul style={ld.cleanList}>
                        {(service.deliverables || []).slice(0, 3).map((item, i) => <li key={i}>{item}</li>)}
                      </ul>
                    </div>
                  </div>

                  {(service.discovery_questions || []).length > 0 && (
                    <div style={ld.discoveryBox}>
                      <div style={ld.miniLabel}>GÖRÜŞMEDE SOR</div>
                      <div style={ld.questionList}>
                        {(service.discovery_questions || []).slice(0, 3).map((item, i) => (
                          <span key={i} style={ld.questionChip}>{item}</span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          <div style={ld.findCard}>
            <div style={ld.findHeader}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-end' }}>
                <div>
                  <div style={ld.eyebrow}>TARAMA BULGULARI VE FIRSATLAR</div>
                  <div style={ld.cardTitle}>{findings.length > 0 ? `${gapFindings.length} açık · ${opportunityFindings.length} büyüme fırsatı` : 'Kanıtlı açık yok'}</div>
                </div>
                <span style={ld.countBadge}>%{lead.scoring?.coverage || 0} kapsam · %{lead.scoring?.confidence || 0} güven</span>
              </div>
            </div>
            {findings.length === 0
              ? <div style={{ padding: '16px 24px', color: 'var(--sub)', fontSize: 13, lineHeight: 1.6 }}>
                  Bu “sorun yok” anlamına gelmez. {unknownChecks.length} kontrol henüz güvenilir biçimde tamamlanamadı.
                </div>
              : findings.map((finding, i) => {
                  const sev = findingSeverity(finding);
                  return (
                    <div key={finding.code || i} style={{ ...ld.findRow, alignItems: 'flex-start' }}>
                      <div style={{ ...ld.sevPill, ...sevStyle(sev) }}>{finding.finding_type === 'opportunity' ? 'Fırsat' : sev}</div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={ld.findTitle}>{finding.title}</div>
                        <div style={ld.findEvidence}><strong>Kanıt:</strong> {finding.evidence}</div>
                        <div style={ld.findImpact}><strong>İş etkisi:</strong> {finding.impact}</div>
                        {finding.talking_point && <div style={ld.talkingPoint}>Görüşmede söyle: “{finding.talking_point}”</div>}
                        {finding.verification && <div style={ld.verifyText}>Teyit: {finding.verification}</div>}
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'flex-end' }}>
                        <span style={ld.confidenceBadge}>%{finding.confidence || 0} güven</span>
                        <button style={ld.findBtn} onClick={() => setFeedback(openFixContext(lead, finding))}>Kaynağı aç →</button>
                      </div>
                    </div>
                  );
                })
            }
          </div>

          {unknownChecks.length > 0 && (
            <div style={{ ...ld.findCard, marginTop: 16 }}>
              <div style={ld.findHeader}>
                <div style={ld.eyebrow}>DOĞRULANMAYAN KONTROLLER</div>
                <div style={ld.cardTitle}>{unknownChecks.length} başlık satış iddiası olarak kullanılmıyor</div>
              </div>
              {unknownChecks.slice(0, 8).map((check, i) => (
                <div key={`${check.code}-${i}`} style={ld.unknownRow}>
                  <div>
                    <div style={ld.findTitle}>{check.label}</div>
                    <div style={ld.findEvidence}>{check.note}</div>
                  </div>
                  {check.source_url && <button style={ld.findBtn} onClick={() => openExternal(check.source_url)}>Kontrol et →</button>}
                </div>
              ))}
            </div>
          )}

          {lead.ai_report && (
            <div style={{ ...ld.findCard, marginTop: 16 }}>
              <div style={{ ...ld.findHeader, cursor: 'pointer', userSelect: 'none' }} onClick={() => setShowReport(r => !r)}>
                <div><div style={ld.eyebrow}>GÖRÜŞME HAZIRLIĞI</div><div style={ld.cardTitle}>AI ihtiyaç özeti {showReport ? '▲' : '▼'}</div></div>
              </div>
              {showReport && AI_STATE_NOTES[lead.ai_state] && <div style={ld.draftWarning}>{AI_STATE_NOTES[lead.ai_state]}</div>}
              {showReport && <div style={{ padding: '16px 24px', fontSize: 13.5, color: 'var(--sub)', lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>{lead.ai_report}</div>}
            </div>
          )}

          {lead.ai_email && (
            <div style={{ ...ld.findCard, marginTop: 16 }}>
              <div style={{ ...ld.findHeader, cursor: 'pointer', userSelect: 'none' }} onClick={() => setShowEmail(e => !e)}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
                  <div><div style={ld.eyebrow}>ONAY BEKLEYEN TASLAK</div><div style={ld.cardTitle}>E-posta taslağı {showEmail ? '▲' : '▼'}</div></div>
                  {showEmail && <button style={ld.findBtn} onClick={e => { e.stopPropagation(); copyEmail(); }}>{copied ? '✓ Kopyalandı' : 'Kopyala'}</button>}
                </div>
              </div>
              {showEmail && (
                <div>
                  <div style={ld.draftWarning}>Göndermeden önce işletme bilgilerini, kanıtı ve önerilen hizmeti kontrol et.</div>
                  <div style={{ padding: '16px 24px', fontSize: 13, color: 'var(--sub)', lineHeight: 1.7, whiteSpace: 'pre-wrap', fontFamily: "'Space Grotesk'", background: 'var(--panel2)' }}>{lead.ai_email}</div>
                </div>
              )}
            </div>
          )}
        </div>

        <aside style={ld.side}>
          <div style={ld.sideCard}>
            <div style={ld.eyebrow}>HAZIRLIK</div>
            <div style={{ ...ld.cardTitle, marginBottom: 14 }}>Temas checklist</div>
            <div style={ld.readinessGrid}>
              {readiness.map(item => (
                <div key={item.label} style={item.ready ? ld.readyItemOk : ld.readyItemWarn}>
                  <span>{item.ready ? 'Hazır' : 'Eksik'}</span>
                  <strong>{item.label}</strong>
                </div>
              ))}
            </div>
          </div>

          <div style={ld.sideCard}>
            <div style={ld.eyebrow}>DURUM</div>
            <div style={{ ...ld.cardTitle, marginBottom: 14 }}>Pipeline konumu</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {STATUS_OPTIONS.map(([key, label]) => (
                <button key={key} style={{ ...ld.findBtn, background: status === key ? 'var(--accent)' : 'var(--panel2)', color: status === key ? 'var(--accent-ink)' : 'var(--tx)', fontWeight: status === key ? 600 : 400, border: status === key ? 'none' : '1px solid var(--line)' }} onClick={() => onStatusChange(key)}>{label}</button>
              ))}
            </div>
          </div>

          <div style={ld.sideCard}>
            <div style={ld.eyebrow}>AKTİVİTE</div>
            <div style={{ ...ld.cardTitle, marginBottom: 14 }}>Zaman çizelgesi</div>
            {lastEvent && (
              <div style={ld.lastEventBanner}>
                <div style={ld.lastEventLabel}>Son hareket</div>
                <div style={ld.lastEventText}>{(ACTIONS[lastEvent.action] || ACTIONS.note_added).label}</div>
              </div>
            )}
            {events.map((event, eventIdx) => {
              const meta = ACTIONS[event.action] || ACTIONS.note_added;
              return (
                <div key={`${event.ts}-${eventIdx}`} style={ld.actRow}>
                  <div style={ld.actDot}/>
                  <div style={{ flex: 1 }}>
                    <div style={ld.actKind}>{meta.label}</div>
                    <div style={ld.actMeta}>
                      {fmtDate(event.date)}
                      {event.channelLabel ? ` · ${event.channelLabel}` : ''}
                      {event.outcomeLabel ? ` · ${event.outcomeLabel}` : ''}
                      {event.note ? ` · ${event.note}` : ''}
                      {event.followUpAt ? ` · Takip ${new Date(event.followUpAt).toLocaleString('tr-TR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}` : ''}
                    </div>
                  </div>
                </div>
              );
            })}
            {lead.last_analyzed && (
              <div style={ld.actRow}><div style={ld.actDot}/><div style={{ flex: 1 }}><div style={ld.actKind}>Tarama tamamlandı</div><div style={ld.actMeta}>{fmtDate(lead.last_analyzed)} · {scoreAvailable ? `Skor ${lead.scoring.score}` : `%${lead.scoring?.coverage || 0} kapsam`}</div></div></div>
            )}
            <div style={ld.actRow}><div style={ld.actDot}/><div style={{ flex: 1 }}><div style={ld.actKind}>Lead listesine eklendi</div><div style={ld.actMeta}>{lead.city || '—'}</div></div></div>
          </div>

          <div style={ld.sideCard}>
            <div style={ld.eyebrow}>NOT</div>
            <div style={{ ...ld.cardTitle, marginBottom: 12 }}>Hızlı not</div>
            <textarea style={ld.textarea} value={note} onChange={e => setNote(e.target.value)} placeholder="Lead hakkında not ekle..."/>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginTop: 10 }}>
              <div style={ld.noteHint}>{feedback || 'Kısa notu zaman çizelgesine ekler.'}</div>
              <button style={{ ...ld.btnDarkSm, opacity: busy || !note.trim() ? 0.7 : 1 }} onClick={saveNote} disabled={busy || !note.trim()}>{busy ? 'Kaydediliyor…' : 'Kaydet'}</button>
            </div>
          </div>
        </aside>
      </section>
    </div>
  );
}

const ld = {
  root:        { padding: '24px 48px 48px', flex: 1, fontFamily: "'Instrument Sans', system-ui, sans-serif", color: 'var(--tx)', background: 'var(--bg)', minWidth: 0 },
  top:         { display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingBottom: 18, borderBottom: '1px solid var(--line)', marginBottom: 32 },
  crumbs:      { display: 'flex', gap: 10, fontSize: 13, color: 'var(--muted)', alignItems: 'center', flexWrap: 'wrap' },
  crumb:       { fontFamily: "'Space Grotesk'" },
  crumbSep:    { color: 'var(--muted)' },
  btnGhost:    { padding: '8px 14px', background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 8, fontSize: 12.5, color: 'var(--sub)', cursor: 'pointer' },
  btnDark:     { padding: '8px 14px', background: 'var(--accent)', color: 'var(--accent-ink)', border: 'none', borderRadius: 8, fontSize: 12.5, fontWeight: 600, cursor: 'pointer' },
  btnDarkSm:   { padding: '6px 12px', background: 'var(--accent)', color: 'var(--accent-ink)', border: 'none', borderRadius: 7, fontSize: 11.5, fontWeight: 600, cursor: 'pointer' },
  hero:        { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 32, marginBottom: 24 },
  heroLeft:    { flex: 1 },
  statusRow:   { display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' },
  statusBadge: { fontSize: 11, fontFamily: "'Space Grotesk'", background: 'rgba(255,107,107,0.14)', color: '#ff8f8f', padding: '4px 10px', borderRadius: 99, fontWeight: 600, letterSpacing: 0.5 },
  metaTag:     { fontSize: 11.5, fontFamily: "'Space Grotesk'", background: 'var(--panel)', border: '1px solid var(--line)', padding: '4px 10px', borderRadius: 99, color: 'var(--sub)' },
  metaText:    { fontSize: 11.5, color: 'var(--muted)', fontFamily: "'Space Grotesk'", marginLeft: 6 },
  h1:          { fontFamily: "'Space Grotesk'", fontSize: 46, fontWeight: 600, letterSpacing: -1.6, lineHeight: 1.05, margin: '20px 0 0', color: 'var(--tx)' },
  urls:        { display: 'flex', gap: 8, marginTop: 18, flexWrap: 'wrap' },
  quickActions:{ display: 'flex', gap: 8, marginTop: 16, flexWrap: 'wrap' },
  quickBtn:    { padding: '8px 14px', background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 10, fontSize: 12, color: 'var(--tx)', cursor: 'pointer', fontWeight: 500 },
  urlChip:     { padding: '8px 14px', background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 99, fontSize: 12.5, color: 'var(--sub)', cursor: 'pointer', fontFamily: "'Space Grotesk'" },
  heroRight:   { display: 'flex', alignItems: 'center', gap: 16, flexShrink: 0 },
  gradePill:   { width: 56, height: 56, borderRadius: 14, background: 'var(--accent)', color: 'var(--accent-ink)', display: 'grid', placeItems: 'center', fontFamily: "'Space Grotesk'", fontSize: 26, fontWeight: 700 },
  nextAction:  { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 24, padding: '20px 24px', background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 'var(--rs)', marginBottom: 28 },
  naEyebrow:   { fontSize: 10.5, fontFamily: "'Space Grotesk'", textTransform: 'uppercase', letterSpacing: 1.2, color: '#ffcf4a' },
  naTitle:     { fontFamily: "'Space Grotesk'", fontSize: 22, fontWeight: 600, letterSpacing: -0.4, marginTop: 6, color: 'var(--tx)' },
  naDesc:      { fontSize: 13, color: 'var(--sub)', marginTop: 4, maxWidth: 600 },
  naHelper:    { fontSize: 12, color: 'var(--muted)', marginTop: 8, lineHeight: 1.45 },
  inlineFeedback:{ fontSize: 12, color: 'var(--accent)', marginTop: 10, fontWeight: 500 },
  cols:        { display: 'grid', gridTemplateColumns: '1.7fr 1fr', gap: 24 },
  side:        { display: 'flex', flexDirection: 'column', gap: 16 },
  eyebrow:     { fontSize: 11, fontFamily: "'Space Grotesk'", textTransform: 'uppercase', letterSpacing: 1.2, color: 'var(--muted)' },
  cardTitle:   { fontFamily: "'Space Grotesk'", fontSize: 20, fontWeight: 600, letterSpacing: -0.4, marginTop: 6, color: 'var(--tx)' },
  statsCard:   { background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 'var(--rs)', padding: 24, marginBottom: 16 },
  statsHeader: { marginBottom: 18 },
  statsGrid:   { display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 0, borderTop: '1px solid var(--line)', paddingTop: 18 },
  stat:        { padding: '0 14px', borderRight: '1px solid var(--line)' },
  statLabel:   { fontSize: 10.5, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: 1, fontFamily: "'Space Grotesk'" },
  statVal:     { fontFamily: "'Space Grotesk'", fontSize: 22, fontWeight: 700, letterSpacing: -0.6, marginTop: 8, color: 'var(--tx)' },
  salesCard:   { background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 'var(--rs)', overflow: 'hidden', marginBottom: 16 },
  salesSummary:{ padding: '18px 24px', color: 'var(--sub)', fontSize: 13.5, lineHeight: 1.65 },
  salesEvidenceGrid:{ display: 'grid', gridTemplateColumns: 'repeat(3,minmax(0,1fr))', gap: 8, padding: '0 24px 18px' },
  salesEvidence:{ display: 'flex', flexDirection: 'column', gap: 6, padding: 12, borderRadius: 8, background: 'var(--raised)', color: 'var(--tx)', fontSize: 12, lineHeight: 1.45 },
  callScript:  { margin: '0 24px 16px', padding: '15px 16px', borderRadius: 8, background: 'rgba(197,242,74,0.08)', border: '1px solid rgba(197,242,74,0.18)' },
  callScriptText:{ color: 'var(--tx)', fontSize: 13.5, lineHeight: 1.65, marginBottom: 10 },
  scriptGrid:  { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, padding: '0 24px 8px' },
  scriptPanel: { margin: '0 24px 16px', padding: 14, borderRadius: 8, background: 'var(--raised)', border: '1px solid var(--line)' },
  scriptText:  { color: 'var(--sub)', fontSize: 12.5, lineHeight: 1.6, marginBottom: 10 },
  objectionRow:{ display: 'flex', flexDirection: 'column', gap: 3, marginBottom: 8, color: 'var(--sub)', fontSize: 11.5, lineHeight: 1.45 },
  researchCard:{ background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 'var(--rs)', overflow: 'hidden', marginBottom: 16 },
  manualCard:{ background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 'var(--rs)', overflow: 'hidden', marginBottom: 16 },
  manualGrid:{ display: 'grid', gridTemplateColumns: 'repeat(2,minmax(0,1fr))', gap: 10, padding: '18px 24px' },
  manualSection:{ display: 'flex', flexDirection: 'column', gap: 9, padding: 14, borderRadius: 10, background: 'var(--raised)', border: '1px solid var(--line)' },
  manualSectionHead:{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, minHeight: 24 },
  manualCheck:{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--tx)', fontSize: 12.5, cursor: 'pointer' },
  manualSource:{ padding: 0, border: 'none', background: 'transparent', color: 'var(--accent)', fontSize: 10.5, cursor: 'pointer' },
  manualFields:{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 },
  manualInput:{ width: '100%', minWidth: 0, padding: '9px 10px', background: 'var(--bg)', border: '1px solid var(--line)', borderRadius: 7, color: 'var(--tx)', outline: 'none', fontSize: 11.5 },
  manualFooter:{ display: 'flex', alignItems: 'flex-end', gap: 10, padding: '0 24px 20px' },
  placeChoices:{ display: 'grid', gap: 8, margin: '16px 24px 0', padding: 12, borderRadius: 7, background: 'var(--warn-bg)', border: '1px solid var(--line)' },
  placeChoiceHint:{ color: 'var(--warn-tx)', fontSize: 11.5, fontWeight: 600 },
  placeChoice:{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap', padding: '8px 10px', borderRadius: 6, background: 'var(--panel)', fontSize: 12 },
  placeChoiceMeta:{ color: 'var(--sub)', fontSize: 11, marginTop: 2, overflowWrap: 'anywhere' },
  factIssues:{ display: 'grid', gap: 4, margin: '16px 24px 0', padding: '10px 12px', borderRadius: 7, background: 'var(--warn-bg)', color: 'var(--warn-tx)', fontSize: 11.5, overflowWrap: 'anywhere' },
  manualNote:{ flex: 1, minHeight: 62, resize: 'vertical', padding: '10px 12px', background: 'var(--bg)', border: '1px solid var(--line)', borderRadius: 8, color: 'var(--tx)', outline: 'none', fontSize: 11.5 },
  manualFactStrip:{ display: 'flex', flexDirection: 'column', gap: 5, margin: '16px 24px 0', padding: '11px 12px', borderRadius: 8, background: 'rgba(197,242,74,0.07)', border: '1px solid rgba(197,242,74,0.15)', color: 'var(--sub)', fontSize: 11.5, lineHeight: 1.45 },
  researchStats:{ display: 'grid', gridTemplateColumns: 'repeat(4,minmax(0,1fr))', borderBottom: '1px solid var(--line)' },
  researchStat:{ padding: '14px 18px', borderRight: '1px solid var(--line)', display: 'flex', flexDirection: 'column', gap: 4, color: 'var(--muted)', fontSize: 10.5 },
  researchColumns:{ display: 'grid', gridTemplateColumns: '1.15fr .85fr', gap: 24, padding: '20px 24px' },
  researchWarning:{ margin: '16px 24px 0', padding: '10px 12px', borderRadius: 7, background: 'rgba(255,159,67,0.1)', border: '1px solid rgba(255,159,67,0.18)', color: '#ffb36b', fontSize: 11.5 },
  researchRow:{ padding: '12px 0', borderBottom: '1px solid var(--line)' },
  researchRowHead:{ display: 'flex', justifyContent: 'space-between', gap: 12, color: 'var(--tx)', fontSize: 12.5 },
  researchEvidence:{ color: 'var(--sub)', fontSize: 11.5, lineHeight: 1.5, marginTop: 6 },
  researchSource:{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginTop: 8, color: 'var(--muted)', fontSize: 10.5 },
  researchLink:{ border: 'none', background: 'none', color: 'var(--accent)', fontSize: 10.5, cursor: 'pointer', padding: 0 },
  manualRow:{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '4px 10px', padding: '10px 0', borderBottom: '1px solid var(--line)', fontSize: 11.5, color: 'var(--sub)' },
  emptyResearch:{ color: 'var(--muted)', fontSize: 12, lineHeight: 1.5, padding: '10px 0' },
  guardrail:{ margin: '0 24px 20px', padding: '10px 12px', borderLeft: '2px solid var(--accent)', background: 'var(--raised)', color: 'var(--sub)', fontSize: 11.5, lineHeight: 1.5 },
  comms:{ borderTop: '1px solid var(--line)', borderBottom: '1px solid var(--line)', padding: '20px 24px', marginBottom: 18 },
  commsHead:{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-start' },
  notSentBadge:{ fontSize: 10.5, color: 'var(--sub)', border: '1px solid var(--line)', borderRadius: 6, padding: '5px 8px', whiteSpace: 'nowrap' },
  channelTabs:{ display: 'flex', gap: 6, overflowX: 'auto', marginTop: 16, paddingBottom: 2 },
  channelTab:{ display: 'flex', alignItems: 'center', gap: 7, padding: '8px 11px', border: '1px solid var(--line)', borderRadius: 7, background: 'var(--panel2)', color: 'var(--sub)', cursor: 'pointer', whiteSpace: 'nowrap', fontSize: 11.5 },
  channelTabActive:{ display: 'flex', alignItems: 'center', gap: 7, padding: '8px 11px', border: '1px solid var(--accent)', borderRadius: 7, background: 'rgba(197,242,74,0.08)', color: 'var(--tx)', cursor: 'pointer', whiteSpace: 'nowrap', fontSize: 11.5 },
  channelDot:{ width: 6, height: 6, borderRadius: 999, flexShrink: 0 },
  draftMeta:{ display: 'flex', justifyContent: 'space-between', gap: 12, color: 'var(--muted)', fontSize: 10.5, margin: '12px 0 8px' },
  draftSubject:{ width: '100%', padding: '10px 12px', background: 'var(--bg)', border: '1px solid var(--line)', borderBottom: 'none', borderRadius: '8px 8px 0 0', color: 'var(--tx)', outline: 'none', fontSize: 12.5 },
  draftEditor:{ width: '100%', minHeight: 180, resize: 'vertical', padding: 14, background: 'var(--bg)', border: '1px solid var(--line)', borderRadius: 8, color: 'var(--tx)', outline: 'none', fontSize: 12.5, lineHeight: 1.65 },
  draftReview:{ padding: '9px 11px', background: 'rgba(255,207,74,0.08)', color: '#d9bd5a', borderRadius: 7, marginTop: 8, fontSize: 11.5, lineHeight: 1.45 },
  draftFooter:{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, color: 'var(--muted)', fontSize: 10.5, marginTop: 10 },
  packCard:    { background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 'var(--rs)', padding: 22, marginBottom: 16 },
  packTitle:   { fontFamily: "'Space Grotesk'", fontSize: 22, fontWeight: 600, letterSpacing: -0.4, margin: '8px 0 6px', color: 'var(--tx)' },
  packDesc:    { fontSize: 13, color: 'var(--sub)', maxWidth: 480 },
  packRight:   { textAlign: 'right', minWidth: 160 },
  packPrice:   { fontFamily: "'Space Grotesk'", fontSize: 20, fontWeight: 700, letterSpacing: -0.4, color: 'var(--accent)' },
  packRange:   { fontSize: 12, color: 'var(--sub)', fontFamily: "'Space Grotesk'", marginTop: 4 },
  packTags:    { display: 'flex', gap: 6, marginTop: 14, paddingTop: 14, borderTop: '1px solid var(--line)', flexWrap: 'wrap' },
  tag:         { fontSize: 11, fontFamily: "'Space Grotesk'", background: 'var(--raised)', padding: '4px 10px', borderRadius: 6, color: 'var(--sub)' },
  tagPrimary:  { fontSize: 11, fontFamily: "'Space Grotesk'", background: 'var(--accent)', color: 'var(--accent-ink)', padding: '4px 10px', borderRadius: 6, fontWeight: 600 },
  verifiedBadge:{ fontSize: 10.5, fontFamily: "'Space Grotesk'", fontWeight: 600, padding: '5px 9px', borderRadius: 6, background: 'rgba(197,242,74,0.12)', color: 'var(--accent)', whiteSpace: 'nowrap' },
  discoveryBadge:{ fontSize: 10.5, fontFamily: "'Space Grotesk'", fontWeight: 600, padding: '5px 9px', borderRadius: 6, background: 'rgba(255,207,74,0.12)', color: '#ffcf4a', whiteSpace: 'nowrap' },
  opportunitySection:{ background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 'var(--rs)', overflow: 'hidden', marginBottom: 16 },
  opportunityRow:{ padding: '22px 24px', borderBottom: '1px solid var(--line)' },
  opportunityTop:{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 },
  opportunityIndex:{ fontSize: 10.5, color: 'var(--muted)', fontFamily: "'Space Grotesk'", textTransform: 'uppercase', letterSpacing: 1 },
  opportunityTitle:{ fontSize: 18, color: 'var(--tx)', fontFamily: "'Space Grotesk'", fontWeight: 600, marginTop: 6 },
  opportunityDesc:{ fontSize: 12.5, color: 'var(--sub)', lineHeight: 1.5, marginTop: 5, maxWidth: 620 },
  opportunityColumns:{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, marginTop: 18, paddingTop: 16, borderTop: '1px solid var(--line)' },
  miniLabel:{ fontSize: 10.5, color: 'var(--muted)', fontFamily: "'Space Grotesk'", textTransform: 'uppercase', letterSpacing: 1, marginBottom: 9 },
  evidenceList:{ display: 'flex', flexDirection: 'column', gap: 7 },
  evidenceItem:{ display: 'flex', alignItems: 'flex-start', gap: 8, fontSize: 12.5, color: 'var(--tx)', lineHeight: 1.45 },
  evidenceDot:{ width: 7, height: 7, borderRadius: 99, background: '#ffcf4a', marginTop: 5, flexShrink: 0 },
  cleanList:{ margin: 0, paddingLeft: 18, fontSize: 12.5, color: 'var(--tx)', lineHeight: 1.7 },
  discoveryBox:{ marginTop: 18, background: 'var(--panel2)', border: '1px solid var(--line)', borderRadius: 10, padding: '13px 14px' },
  questionList:{ display: 'flex', gap: 7, flexWrap: 'wrap' },
  questionChip:{ fontSize: 11.5, color: 'var(--sub)', background: 'var(--raised)', border: '1px solid var(--line)', borderRadius: 7, padding: '6px 9px', lineHeight: 1.35 },
  countBadge:{ fontSize: 11, color: 'var(--sub)', fontFamily: "'Space Grotesk'", background: 'var(--panel2)', border: '1px solid var(--line)', borderRadius: 7, padding: '5px 9px' },
  draftWarning:{ margin: '14px 24px 0', padding: '10px 12px', borderRadius: 8, background: 'rgba(255,207,74,0.10)', border: '1px solid rgba(255,207,74,0.18)', color: '#ffcf4a', fontSize: 11.5, lineHeight: 1.45 },
  findCard:    { background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 'var(--rs)', overflow: 'hidden' },
  findHeader:  { padding: '20px 24px', borderBottom: '1px solid var(--line)' },
  findRow:     { display: 'flex', alignItems: 'center', gap: 16, padding: '16px 24px', borderBottom: '1px solid var(--line)' },
  sevPill:     { fontSize: 10.5, fontFamily: "'Space Grotesk'", padding: '4px 10px', borderRadius: 6, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5, minWidth: 60, textAlign: 'center', flexShrink: 0 },
  findTitle:   { fontSize: 14, fontWeight: 600, color: 'var(--tx)' },
  findEvidence:{ fontSize: 12.5, color: 'var(--sub)', lineHeight: 1.55, marginTop: 7 },
  findImpact:  { fontSize: 12.5, color: 'var(--tx)', lineHeight: 1.55, marginTop: 5 },
  talkingPoint:{ fontSize: 12.5, color: 'var(--accent)', lineHeight: 1.55, marginTop: 9, padding: '9px 11px', borderRadius: 8, background: 'rgba(197,242,74,0.08)', border: '1px solid rgba(197,242,74,0.16)' },
  verifyText:  { fontSize: 11.5, color: 'var(--muted)', lineHeight: 1.5, marginTop: 8 },
  confidenceBadge:{ fontSize: 10.5, color: 'var(--sub)', fontFamily: "'Space Grotesk'", background: 'var(--panel2)', border: '1px solid var(--line)', borderRadius: 7, padding: '5px 8px', whiteSpace: 'nowrap' },
  unknownRow:  { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, padding: '14px 24px', borderBottom: '1px solid var(--line)' },
  findBtn:     { padding: '7px 12px', background: 'var(--panel2)', border: '1px solid var(--line)', borderRadius: 7, fontSize: 12, color: 'var(--tx)', cursor: 'pointer', fontWeight: 500, whiteSpace: 'nowrap' },
  sideCard:    { background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 'var(--rs)', padding: 22 },
  readinessGrid:{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 },
  readyItemOk: { display: 'flex', flexDirection: 'column', gap: 4, padding: '10px 12px', borderRadius: 10, background: 'rgba(197,242,74,0.1)', color: 'var(--accent)', fontSize: 11.5, fontFamily: "'Space Grotesk'" },
  readyItemWarn:{ display: 'flex', flexDirection: 'column', gap: 4, padding: '10px 12px', borderRadius: 10, background: 'rgba(255,159,67,0.12)', color: '#ffb36b', fontSize: 11.5, fontFamily: "'Space Grotesk'" },
  lastEventBanner:{ padding: '10px 12px', borderRadius: 10, background: 'var(--panel2)', border: '1px solid var(--line)', marginBottom: 8 },
  lastEventLabel:{ fontSize: 10.5, color: 'var(--muted)', fontFamily: "'Space Grotesk'", textTransform: 'uppercase', letterSpacing: 1 },
  lastEventText: { fontSize: 13, color: 'var(--tx)', fontWeight: 600, marginTop: 6 },
  actRow:      { display: 'flex', alignItems: 'flex-start', gap: 12, padding: '8px 0' },
  actDot:      { width: 8, height: 8, borderRadius: 99, background: 'var(--accent)', marginTop: 6, flexShrink: 0 },
  actKind:     { fontSize: 13, fontWeight: 500, color: 'var(--tx)' },
  actMeta:     { fontSize: 11.5, color: 'var(--muted)', fontFamily: "'Space Grotesk'", marginTop: 2 },
  noteHint:    { fontSize: 11.5, color: 'var(--muted)', lineHeight: 1.4 },
  textarea:    { width: '100%', minHeight: 80, padding: 12, border: '1px solid var(--line)', borderRadius: 10, fontSize: 13, resize: 'vertical', boxSizing: 'border-box', color: 'var(--tx)', background: 'var(--panel2)', outline: 'none' },
};

// ── Pipeline View ──────────────────────────────────────────────────────────

function PipelineView({ leads, onSelect, onDataChange }) {
  const crm = useCrm();
  const [tick, setTick] = React.useState(0);
  const [busyLead, setBusyLead] = React.useState('');
  const dragRef = React.useRef('');

  function refresh() { setTick(t => t + 1); }

  const byStage = {};
  PIPE_STAGES.forEach(s => { byStage[s.key] = []; });
  leads.forEach(l => { const stage = getPipelineStage(crm.statuses[l.name] || 'yeni', crm.eventsFor(l.name)); (byStage[stage] = byStage[stage] || []).push(l); });

  const won = byStage['won'].length;
  const active = ['draft','contacted','meeting'].reduce((a, k) => a + (byStage[k]||[]).length, 0);

  function runCardAction(lead, event) {
    event.stopPropagation();
    setBusyLead(lead.name);
    startLeadAction(lead)
      .finally(() => {
        setBusyLead('');
        if (onDataChange) onDataChange();
        refresh();
      });
  }

  function handleDrop(e, stageKey) {
    e.preventDefault();
    e.currentTarget.classList.remove('drag-over');
    const name = dragRef.current;
    if (!name) return;
    const stageObj = PIPE_STAGES.find(s => s.key === stageKey);
    if (!stageObj) return;
    let operation;
    if (stageObj.actions.length) {
      operation = addOutreach(name, stageObj.actions[0], new Date().toISOString().slice(0,16), '');
    } else if (stageKey === 'new') {
      operation = setLeadStatus(name, 'yeni');
    } else if (stageKey === 'contacted') {
      operation = setLeadStatus(name, 'contacted');
    } else if (stageKey === 'won') {
      operation = addOutreach(name, 'deal_won', new Date().toISOString().slice(0,16), '');
    } else if (stageKey === 'lost') {
      operation = addOutreach(name, 'deal_lost', new Date().toISOString().slice(0,16), '');
    }
    dragRef.current = '';
    Promise.resolve(operation).then(() => {
      if (onDataChange) onDataChange();
      refresh();
    }).catch(err => console.error('Pipeline update failed:', err));
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, background: 'var(--bg)' }}>
      <div style={pv.header}>
        <div>
          <div style={pv.pageEyebrow}>PIPELINE</div>
          <h1 style={pv.pageTitle}>Satış kanalı</h1>
          <p style={pv.pageSub}>{leads.length} lead · {won} kazanıldı · {active} aktif temasta</p>
        </div>
      </div>
      <div className="responsive-pipeline" style={pv.board}>
        {PIPE_STAGES.map(stage => {
          const cards = byStage[stage.key] || [];
          return (
            <div
              key={stage.key}
              style={pv.col}
              className="pipe-col"
              onDragOver={e => { e.preventDefault(); e.currentTarget.classList.add('drag-over'); }}
              onDragLeave={e => e.currentTarget.classList.remove('drag-over')}
              onDrop={e => handleDrop(e, stage.key)}
            >
              <div style={pv.colHead}>
                <span style={{ ...pv.colDot, background: stage.color }}/>
                <span style={pv.colTitle}>{stage.label}</span>
                <span style={pv.colCnt}>{cards.length}</span>
              </div>
              <div style={pv.cards}>
                {cards.map(l => {
                  const globalIdx = leads.indexOf(l);
                  const val = l.estimated_value_tl || 0;
                  return (
                    <div
                      key={l.name}
                      style={pv.card}
                      className="pipe-card"
                      draggable
                      onDragStart={e => { dragRef.current = l.name; e.currentTarget.classList.add('dragging'); }}
                      onDragEnd={e => e.currentTarget.classList.remove('dragging')}
                      onClick={() => onSelect(globalIdx)}
                    >
                      <div style={pv.cardName}>{l.name}</div>
                      <div style={pv.cardActionLabel}>{getPrimaryActionMeta(l).label}</div>
                      <div style={pv.cardMeta}>
                        <span style={{ ...pv.cardScore, background: stage.color + '22', color: stage.color }}>{l.scoring.grade} {l.scoring.score}</span>
                        {val > 0 && <span style={pv.cardVal}>~{fmt(val)} ₺</span>}
                      </div>
                      <div style={pv.cardActions}>
                        <button
                          style={{ ...pv.cardBtn, ...(busyLead === l.name ? pv.cardBtnMuted : null) }}
                          onClick={e => runCardAction(l, e)}
                          disabled={busyLead === l.name}
                        >
                          {busyLead === l.name ? 'Kaydediliyor…' : getPrimaryActionMeta(l).label}
                        </button>
                        <button style={pv.cardBtnGhost} onClick={e => { e.stopPropagation(); triggerQuickLeadAction(l); }}>
                          Hızlı aç
                        </button>
                      </div>
                    </div>
                  );
                })}
                {cards.length === 0 && <div style={pv.empty}>Buraya sürükle</div>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

const pv = {
  header:      { padding: '26px 32px 20px', borderBottom: '1px solid var(--line)', background: 'var(--bg)' },
  pageEyebrow: { fontSize: 11, fontFamily: "'Space Grotesk'", textTransform: 'uppercase', letterSpacing: 1.2, color: 'var(--muted)', marginBottom: 8 },
  pageTitle:   { fontFamily: "'Space Grotesk'", fontSize: 34, fontWeight: 600, letterSpacing: -1.2, margin: 0, color: 'var(--tx)' },
  pageSub:     { fontSize: 13, color: 'var(--sub)', marginTop: 6, fontFamily: "'Space Grotesk'" },
  board:       { display: 'flex', gap: 14, padding: '24px 32px 40px', overflowX: 'auto', alignItems: 'flex-start', flex: 1 },
  col:         { minWidth: 220, flex: '0 0 220px', background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 'var(--rs)', padding: 14, display: 'flex', flexDirection: 'column', gap: 0 },
  colHead:     { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 },
  colDot:      { width: 8, height: 8, borderRadius: 99, flexShrink: 0 },
  colTitle:    { fontSize: 12.5, fontWeight: 600, flex: 1, color: 'var(--tx)' },
  colCnt:      { fontSize: 11, fontFamily: "'Space Grotesk'", background: 'var(--raised)', padding: '2px 7px', borderRadius: 99, color: 'var(--sub)' },
  cards:       { display: 'flex', flexDirection: 'column', gap: 10 },
  card:        { background: 'var(--raised)', border: '1px solid var(--line)', borderRadius: 14, padding: '14px', cursor: 'pointer' },
  cardName:    { fontSize: 13, fontWeight: 600, lineHeight: 1.3, marginBottom: 8, color: 'var(--tx)' },
  cardActionLabel:{ fontSize: 10.5, color: 'var(--muted)', fontFamily: "'Space Grotesk'", textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 8 },
  cardMeta:    { display: 'flex', gap: 6, flexWrap: 'wrap' },
  cardActions: { display: 'flex', gap: 6, marginTop: 10, flexWrap: 'wrap' },
  cardBtn:     { flex: 1, minHeight: 32, padding: '7px 10px', borderRadius: 8, border: 'none', background: 'var(--accent)', color: 'var(--accent-ink)', fontSize: 11.5, fontWeight: 600, cursor: 'pointer' },
  cardBtnMuted:{ opacity: 0.72, cursor: 'progress' },
  cardBtnGhost:{ minHeight: 32, padding: '7px 10px', borderRadius: 8, border: '1px solid var(--line)', background: 'var(--panel2)', color: 'var(--sub)', fontSize: 11.5, fontWeight: 500, cursor: 'pointer' },
  cardScore:   { fontSize: 11, fontFamily: "'Space Grotesk'", fontWeight: 700, padding: '2px 8px', borderRadius: 6 },
  cardVal:     { fontSize: 11, color: 'var(--accent)', fontFamily: "'Space Grotesk'" },
  empty:       { fontSize: 12, color: 'var(--muted)', textAlign: 'center', padding: '20px 0', border: '1.5px dashed var(--line2)', borderRadius: 10 },
};

// ── Hizmetler View ─────────────────────────────────────────────────────────

function HizmetlerView({ leads }) {
  const svcMap = {};
  leads.forEach(l => {
    (l.matched_services || []).forEach(svc => {
      if (!svcMap[svc.slug]) svcMap[svc.slug] = { svc, matches: [] };
      svcMap[svc.slug].matches.push({ lead: l, match: svc });
    });
  });

  const entries = services.map(svc => {
    const active = svcMap[svc.slug] || { matches: [] };
    const confirmed = active.matches.filter(item => item.match.match_type === 'confirmed_gap');
    const conditional = active.matches.filter(item => item.match.match_type === 'conditional_gap');
    const opportunities = active.matches.filter(item => item.match.match_type === 'qualified_opportunity');
    return { svc, matches: active.matches, confirmed, conditional, opportunities };
  }).sort((a, b) => b.matches.length - a.matches.length);

  const serviceTypeLabel = type => ({
    monthly: 'Aylık',
    project: 'Proje',
    project_or_monthly: 'Proje / Aylık',
  }[type] || 'Kapsamlanacak');

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, background: 'var(--bg)' }}>
      <div style={pv.header}>
        <div>
          <div style={pv.pageEyebrow}>HİZMETLER</div>
          <h1 style={pv.pageTitle}>Zeplin Media Hizmetleri</h1>
          <p style={pv.pageSub}>{entries.length} onaylı hizmet · {entries.reduce((a,e)=>a+e.matches.length,0)} ölçülebilir hizmet sinyali · Kesin açık ve görüşme fırsatı ayrı gösterilir</p>
        </div>
      </div>
      <div style={hv.grid}>
        {entries.map(({ svc, matches, confirmed, conditional, opportunities }) => (
          <div key={svc.slug} style={hv.card}>
            <div style={hv.cardTop}>
              <span style={{ ...hv.badge, background: svc.monthly ? 'rgba(124,197,255,0.14)' : 'rgba(197,242,74,0.12)', color: svc.monthly ? '#7cc5ff' : 'var(--accent)' }}>
                {serviceTypeLabel(svc.service_type)}
              </span>
              <span style={{ ...hv.badge, background: 'var(--raised)', color: 'var(--sub)' }}>{svc.category || 'Genel'}</span>
            </div>
            <div style={hv.cardName}>{svc.name}</div>
            {svc.desc && <div style={hv.cardDesc}>{svc.desc}</div>}
            {svc.detects && <div style={hv.detects}><strong style={{ color: 'var(--sub)' }}>Bot tespit eder:</strong> {svc.detects}</div>}
            <div style={hv.cardStats}>
              <div><div style={hv.statVal}>{matches.length}</div><div style={hv.statLbl}>Toplam Sinyal</div></div>
              <div><div style={{ ...hv.statVal, color: 'var(--accent)' }}>{confirmed.length}</div><div style={hv.statLbl}>Kesin Açık</div></div>
              <div><div style={{ ...hv.statVal, color: '#ffcf4a' }}>{conditional.length + opportunities.length}</div><div style={hv.statLbl}>Görüşmede Doğrula</div></div>
            </div>
            <div style={hv.price}>Fiyat ve kapsam görüşme sonrasında yönetim onayıyla belirlenir.</div>
          </div>
        ))}
      </div>
    </div>
  );
}

const hv = {
  grid:     { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 14, padding: '24px 32px 40px' },
  card:     { background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 'var(--rs)', padding: 20, display: 'flex', flexDirection: 'column', gap: 10 },
  cardTop:  { display: 'flex', gap: 6 },
  badge:    { fontSize: 10.5, fontFamily: "'Space Grotesk'", fontWeight: 600, padding: '3px 9px', borderRadius: 99 },
  cardName: { fontFamily: "'Space Grotesk'", fontSize: 17, fontWeight: 600, letterSpacing: -0.3, marginTop: 4, color: 'var(--tx)' },
  cardDesc: { fontSize: 12.5, color: 'var(--sub)', lineHeight: 1.45 },
  detects:  { fontSize: 12, color: 'var(--sub)', background: 'var(--panel2)', padding: '8px 12px', borderRadius: 8, lineHeight: 1.4 },
  cardStats:{ display: 'flex', gap: 24, paddingTop: 10, borderTop: '1px solid var(--line)', marginTop: 4 },
  statVal:  { fontFamily: "'Space Grotesk'", fontSize: 20, fontWeight: 700, letterSpacing: -0.5, color: 'var(--tx)' },
  statLbl:  { fontSize: 11, color: 'var(--muted)', fontFamily: "'Space Grotesk'", marginTop: 2 },
  price:    { fontFamily: "'Space Grotesk'", fontSize: 15, fontWeight: 600, color: 'var(--tx)', marginTop: 4 },
};

function AdminView({ user }) {
  const [query, setQuery] = React.useState('restoran');
  const [city, setCity] = React.useState('Istanbul Kadıköy');
  const [maxResults, setMaxResults] = React.useState(10);
  const [deepResearch, setDeepResearch] = React.useState(true);
  const [aiMode, setAiMode] = React.useState('smart');
  const [jobs, setJobs] = React.useState([]);
  const [tokens, setTokens] = React.useState(null);
  const [feedback, setFeedback] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const isAdmin = user?.role === 'admin';

  const [estimate, setEstimate] = React.useState(null);

  // The estimate comes from the API: the same figure the job will reserve.
  React.useEffect(() => {
    if (!isAdmin) return undefined;
    let cancelled = false;
    const params = new URLSearchParams({ estimate: '1', max_results: String(maxResults || 1), deep_research: deepResearch ? '1' : '0', ai_mode: aiMode });
    const timer = setTimeout(() => {
      fetchAdminJSON(`/api/admin_search?${params}`)
        .then(data => { if (!cancelled) setEstimate(data.estimate || null); })
        .catch(() => { if (!cancelled) setEstimate(null); });
    }, 250);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [isAdmin, maxResults, deepResearch, aiMode]);
  const usd = value => `$${Number(value || 0).toFixed(4)}`;

  function refreshAdmin() {
    return fetchAdminJSON('/api/admin_search')
      .then(data => {
        setJobs(data.jobs || []);
        setTokens(data.token_summary || null);
      })
      .catch(err => setFeedback(err.message));
  }

  React.useEffect(() => {
    if (isAdmin) refreshAdmin();
  }, [isAdmin]);

  function createJob(e) {
    e.preventDefault();
    setBusy(true);
    setFeedback('');
    fetchAdminJSON('/api/admin_search', {
      method: 'POST',
      body: JSON.stringify({
        query,
        city,
        max_results: Number(maxResults),
        deep_research: deepResearch,
        ai_mode: aiMode,
      }),
    })
      .then(data => {
        setFeedback(`Search job #${data.job.id} kuyruğa alındı. Tahmini ${data.estimate.estimated_tokens.toLocaleString('tr-TR')} token.`);
        return refreshAdmin();
      })
      .catch(err => setFeedback(err.message))
      .finally(() => setBusy(false));
  }

  if (!isAdmin) {
    return (
      <div style={av.root}>
        <div style={av.loginCard}>
          <div style={pv.pageEyebrow}>YETKİ</div>
          <h1 style={pv.pageTitle}>Admin alanı</h1>
          <p style={av.text}>Yeni search ve token bütçesi sadece patron hesaplarında açık.</p>
        </div>
      </div>
    );
  }

  return (
    <div style={av.root}>
      <div style={{ ...pv.header, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={pv.pageEyebrow}>ADMIN</div>
          <h1 style={pv.pageTitle}>Search operasyonu</h1>
          <p style={pv.pageSub}>Yeni lead taraması, DeepSeek bütçesi ve Supabase job kuyruğu.</p>
        </div>
        <div style={av.userChip}>{user?.name || user?.email}</div>
      </div>

      <div className="responsive-admin" style={av.grid}>
        <form style={av.panel} onSubmit={createJob}>
          <div style={ld.eyebrow}>YENİ SEARCH</div>
          <div style={ld.cardTitle}>Admin tarama başlat</div>
          <label style={av.label}>Arama tipi</label>
          <input value={query} onChange={e => setQuery(e.target.value)} style={av.input} placeholder="restoran, mağaza, kuaför" />
          <label style={av.label}>Bölge</label>
          <input value={city} onChange={e => setCity(e.target.value)} style={av.input} placeholder="Istanbul Kadıköy" />
          <div style={av.row}>
            <div style={{ flex: 1 }}>
              <label style={av.label}>Sonuç</label>
              <input type="number" min="1" max="30" value={maxResults} onChange={e => setMaxResults(e.target.value)} style={av.input} />
            </div>
            <div style={{ flex: 1 }}>
              <label style={av.label}>AI modu</label>
              <select value={aiMode} onChange={e => setAiMode(e.target.value)} style={av.input}>
                <option value="smart">Smart</option>
                <option value="flash">Flash</option>
                <option value="pro">Pro</option>
              </select>
            </div>
          </div>
          <label style={av.checkRow}>
            <input type="checkbox" checked={deepResearch} onChange={e => setDeepResearch(e.target.checked)} />
            <span>Deep research açık</span>
          </label>
          <div style={av.estimate}>
            <div><strong>{estimate ? Number(estimate.estimated_tokens).toLocaleString('tr-TR') : '—'}</strong><span> tahmini token</span></div>
            <div><strong>{estimate ? (estimate.priced ? usd(estimate.estimated_cost_usd) : 'Fiyat yok') : '—'}</strong><span> tahmini maliyet</span></div>
          </div>
          {feedback && <div style={av.feedback}>{feedback}</div>}
          <button style={av.primaryBtn} disabled={busy || !query.trim() || !city.trim()}>{busy ? 'Kuyruğa alınıyor…' : 'Search job oluştur'}</button>
        </form>

        <div style={av.sideStack}>
          <div style={av.panel}>
            <div style={ld.eyebrow}>TOKEN</div>
            <div style={ld.cardTitle}>AI kullanımı</div>
            <div style={av.metricRow}><span>Gerçek harcama (tüm zamanlar)</span><strong>{usd(tokens?.actual_cost_usd)}</strong></div>
            <div style={av.metricRow}><span>Bugün</span><strong>{usd(tokens?.today_cost_usd)}</strong></div>
            <div style={av.metricRow}><span>Gerçek token</span><strong>{Number(tokens?.actual_tokens || 0).toLocaleString('tr-TR')}</strong></div>
            <div style={av.metricRow}><span>Açık rezervasyon</span><strong>{usd(tokens?.active_reserved_usd)}</strong></div>
            <div style={av.metricRow}><span>Sağlayıcı çağrısı · önbellekten</span><strong>{Number(tokens?.provider_calls || 0)} · {Number(tokens?.cache_hits || 0)}</strong></div>
            {(Number(tokens?.failed_calls || 0) > 0 || Number(tokens?.unpriced_calls || 0) > 0) && (
              <div style={av.metricRow}><span>Başarısız · fiyatsız çağrı</span><strong>{Number(tokens?.failed_calls || 0)} · {Number(tokens?.unpriced_calls || 0)}</strong></div>
            )}
          </div>

          <div style={av.panel}>
            <div style={ld.eyebrow}>SON İŞLER</div>
            <div style={ld.cardTitle}>Search kuyruğu</div>
            <div style={av.jobs}>
              {jobs.length === 0 && <div style={av.muted}>Henüz job yok.</div>}
              {jobs.map(job => (
                <div key={job.id} style={av.jobRow}>
                  <div>
                    <div style={av.jobTitle}>#{job.id} {job.query} · {job.city}</div>
                    <div style={av.muted}>{job.max_results} lead · {job.ai_mode} · {Number(job.estimated_tokens || 0).toLocaleString('tr-TR')} token</div>
                  </div>
                  <span style={av.jobStatus}>{job.status}</span>
                </div>
              ))}
            </div>
            <button style={ld.btnGhost} onClick={refreshAdmin}>Yenile</button>
          </div>
        </div>
      </div>
    </div>
  );
}

const av = {
  root:      { flex: 1, minWidth: 0, background: 'var(--bg)', fontFamily: "'Instrument Sans', system-ui, sans-serif", color: 'var(--tx)' },
  empty:     { padding: 40, color: 'var(--sub)' },
  grid:      { display: 'grid', gridTemplateColumns: '1.1fr 0.9fr', gap: 18, padding: '24px 32px 40px' },
  sideStack: { display: 'flex', flexDirection: 'column', gap: 18 },
  panel:     { background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 'var(--rs)', padding: 22 },
  loginCard: { width: 420, margin: '80px auto', background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 'var(--rs)', padding: 24 },
  text:      { fontSize: 13, color: 'var(--sub)', lineHeight: 1.5, margin: '12px 0 18px' },
  label:     { display: 'block', fontSize: 11, color: 'var(--muted)', fontFamily: "'Space Grotesk'", textTransform: 'uppercase', letterSpacing: 1, margin: '16px 0 6px' },
  input:     { width: '100%', padding: '10px 12px', border: '1px solid var(--line)', borderRadius: 9, background: 'var(--panel2)', color: 'var(--tx)', outline: 'none', fontSize: 13 },
  row:       { display: 'flex', gap: 10 },
  checkRow:  { display: 'flex', alignItems: 'center', gap: 8, marginTop: 16, fontSize: 13, color: 'var(--sub)' },
  estimate:  { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginTop: 16 },
  feedback:  { marginTop: 14, padding: '10px 12px', borderRadius: 9, background: 'var(--raised)', color: 'var(--sub)', fontSize: 12.5 },
  primaryBtn:{ width: '100%', marginTop: 16, padding: '11px 14px', borderRadius: 9, border: 'none', background: 'var(--accent)', color: 'var(--accent-ink)', fontWeight: 600, cursor: 'pointer' },
  metricRow: { display: 'flex', justifyContent: 'space-between', padding: '12px 0', borderBottom: '1px solid var(--line)', fontSize: 13 },
  jobs:      { display: 'flex', flexDirection: 'column', gap: 8, margin: '14px 0' },
  jobRow:    { display: 'flex', justifyContent: 'space-between', gap: 12, padding: 12, border: '1px solid var(--line)', borderRadius: 10, background: 'var(--panel2)' },
  jobTitle:  { fontSize: 13, fontWeight: 600, color: 'var(--tx)' },
  jobStatus: { alignSelf: 'flex-start', padding: '4px 8px', borderRadius: 99, background: 'var(--accent)', color: 'var(--accent-ink)', fontSize: 10.5, fontFamily: "'Space Grotesk'" },
  muted:     { fontSize: 11.5, color: 'var(--muted)', marginTop: 4 },
  userChip:  { border: '1px solid var(--line)', background: 'var(--panel)', color: 'var(--sub)', borderRadius: 999, padding: '9px 14px', fontSize: 12.5, fontWeight: 600 },
};

// ── Analytics (Raporlar) View ──────────────────────────────────────────────

function bar(pct, color) { return { width: `${pct}%`, height: '100%', borderRadius: 99, background: color }; }

function AnalyticsView({ leads, statuses }) {
  const [periodDays, setPeriodDays] = React.useState('all');
  const cutoff = periodDays === 'all' ? null : Date.now() - periodDays * 86400000;
  const periodLeads = leads.filter(lead => {
    if (cutoff === null) return true;
    if (!lead.last_analyzed) return false;
    const stamp = new Date(lead.last_analyzed.replace(' ', 'T')).getTime();
    return !Number.isNaN(stamp) && stamp >= cutoff;
  });
  const actualTotal = periodLeads.length;
  const total = actualTotal || 1;

  const GRADE_COLORS = { A: '#b6f24a', B: '#ffcf4a', C: '#ff8f4a', D: '#7a7a78' };
  const gradeCounts = { A: 0, B: 0, C: 0, D: 0 };
  periodLeads.forEach(l => { const g = l.scoring?.grade; if (gradeCounts[g] !== undefined) gradeCounts[g] += 1; });
  const gradeMax = Math.max(...Object.values(gradeCounts), 1);
  const gradeBars = ['A','B','C','D'].map(g => ({ g, n: gradeCounts[g], c: GRADE_COLORS[g], pct: (gradeCounts[g]/gradeMax*100) }));

  const counts = computeTabCounts(periodLeads, statuses);
  const funnelSteps = [
    { label: 'Toplam', n: actualTotal, bg: 'var(--raised)', tx: 'var(--tx)' },
    { label: 'Yeni', n: counts.yeni, bg: 'var(--panel2)', tx: 'var(--tx)' },
    { label: 'Temasta', n: counts.contacted, bg: 'rgba(124,197,255,0.16)', tx: '#7cc5ff' },
    { label: 'Kazanıldı', n: counts.converted, bg: 'var(--accent)', tx: 'var(--accent-ink)' },
  ];

  const avgScore = Math.round(periodLeads.reduce((a, l) => a + (l.scoring?.score || 0), 0) / total);
  const gaugeCirc = 389.6;
  const gaugeOffset = gaugeCirc * (1 - Math.min(avgScore, 100) / 100);

  const now = new Date();
  const weekBuckets = new Array(8).fill(0);
  periodLeads.forEach(l => {
    if (!l.last_analyzed) return;
    const d = new Date(l.last_analyzed.replace(' ', 'T'));
    if (isNaN(d)) return;
    const diffDays = Math.floor((now - d) / 86400000);
    const weekIdx = Math.floor(diffDays / 7);
    if (weekIdx >= 0 && weekIdx < 8) weekBuckets[7 - weekIdx] += 1;
  });
  const weekMax = Math.max(...weekBuckets, 1);
  const weekly = weekBuckets.map((n, i) => ({ n, label: i === 7 ? 'Bu hafta' : `-${7-i}h`, pct: (n/weekMax*100) }));
  const weeklyTotal = weekBuckets.reduce((a, b) => a + b, 0);

  const sectorMap = {};
  periodLeads.forEach(l => {
    const s = canonicalSector(l);
    sectorMap[s] = (sectorMap[s] || 0) + 1;
  });
  const sectors = Object.entries(sectorMap).sort((a, b) => b[1] - a[1]).slice(0, 5)
    .map(([s, n], i) => ({ s, pct: Math.round(n/total*100), c: ['#b6f24a','#ffcf4a','#ff8f4a','#7cc5ff','#a78bfa'][i] || 'var(--sub)' }));

  const readiness = computeReadinessBuckets(periodLeads);

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, background: 'var(--bg)' }}>
      <div style={{ ...pv.header, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
        <div>
          <div style={pv.pageEyebrow}>{periodDays === 'all' ? 'PERFORMANS · TÜM ZAMANLAR' : `PERFORMANS · SON ${periodDays} GÜN`}</div>
          <h1 style={pv.pageTitle}>Raporlar</h1>
        </div>
        <div style={{ display: 'flex', gap: 4, background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 999, padding: 5 }}>
          {[7, 30, 90, 'all'].map(days => (
            <button key={days} onClick={() => setPeriodDays(days)} style={{ padding: '8px 16px', borderRadius: 999, border: 'none', cursor: 'pointer', background: periodDays === days ? 'var(--selected-bg)' : 'transparent', color: periodDays === days ? 'var(--selected-tx)' : 'var(--sub)', fontSize: 12.5, fontWeight: periodDays === days ? 600 : 500 }}>
              {days === 'all' ? 'Tümü' : days === 90 ? 'Çeyrek' : `${days}g`}
            </button>
          ))}
        </div>
      </div>

      <div className="responsive-report" style={rp.grid}>
        <div style={rp.card}>
          <div style={rp.cardTitle}>Not Dağılımı</div>
          <div style={rp.cardSub}>{actualTotal} lead sınıflandırıldı</div>
          <div style={rp.stack}>
            {gradeBars.map(g => (
              <div key={g.g}>
                <div style={rp.rowHead}><span style={{ fontWeight: 600, color: g.c }}>Sınıf {g.g}</span><span style={rp.num}>{g.n}</span></div>
                <div style={rp.barTrack}><div style={bar(g.pct, g.c)}/></div>
              </div>
            ))}
          </div>
        </div>

        <div style={rp.card}>
          <div style={rp.cardTitle}>Dönüşüm Hunisi</div>
          <div style={rp.cardSub}>Yeni → Müşteri · %{Math.round(counts.converted/total*100)}</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {funnelSteps.map(s => (
              <div key={s.label} style={{ width: `${40 + (s.n/total*60)}%`, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px', borderRadius: 12, background: s.bg }}>
                <span style={{ fontSize: 12.5, fontWeight: 600, color: s.tx }}>{s.label}</span>
                <span style={{ ...rp.num, fontSize: 14, fontWeight: 700, color: s.tx }}>{s.n}</span>
              </div>
            ))}
          </div>
        </div>

        <div style={{ ...rp.card, alignItems: 'center', justifyContent: 'center', display: 'flex', flexDirection: 'column' }}>
          <div style={{ ...rp.cardTitle, alignSelf: 'flex-start' }}>Ortalama Skor</div>
          <div style={{ ...rp.cardSub, alignSelf: 'flex-start' }}>tüm aktif leadler</div>
          <div style={{ position: 'relative', width: 150, height: 150, margin: '14px 0 6px' }}>
            <svg width="150" height="150" viewBox="0 0 150 150" style={{ transform: 'rotate(-90deg)' }}>
              <circle cx="75" cy="75" r="62" fill="none" stroke="var(--line2)" strokeWidth="11"/>
              <circle cx="75" cy="75" r="62" fill="none" stroke="var(--accent)" strokeWidth="11" strokeLinecap="round" strokeDasharray={gaugeCirc} strokeDashoffset={gaugeOffset} style={{ transition: 'stroke-dashoffset .9s cubic-bezier(.22,1,.36,1)' }}/>
            </svg>
            <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
              <span style={{ fontFamily: "'Space Grotesk'", fontSize: 44, fontWeight: 700, lineHeight: 1, color: 'var(--tx)' }}>{avgScore}</span>
              <span style={{ fontSize: 11, color: 'var(--muted)' }}>/ 100</span>
            </div>
          </div>
        </div>

        <div style={{ ...rp.card, gridColumn: 'span 2' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 18 }}>
            <div>
              <div style={rp.cardTitle}>Haftalık Yeni Lead</div>
              <div style={rp.cardSub}>tarama hacmi · 8 hafta</div>
            </div>
            <div style={{ fontFamily: "'Space Grotesk'", fontSize: 26, fontWeight: 700, color: 'var(--tx)' }}>{weeklyTotal}<span style={{ fontSize: 13, color: 'var(--muted)', fontWeight: 500 }}> toplam</span></div>
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 12, height: 150 }}>
            {weekly.map((w, i) => (
              <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, height: '100%', justifyContent: 'flex-end' }}>
                <span style={{ ...rp.num, fontSize: 11, color: 'var(--sub)' }}>{w.n}</span>
                <div style={{ width: '70%', minWidth: 14, height: `${Math.max(w.pct, 4)}%`, borderRadius: 6, background: 'linear-gradient(180deg, var(--accent), rgba(197,242,74,0.35))' }}/>
                <span style={{ fontSize: 10.5, color: 'var(--muted)' }}>{w.label}</span>
              </div>
            ))}
          </div>
        </div>

        <div style={rp.card}>
          <div style={rp.cardTitle}>Sektör Dağılımı</div>
          <div style={rp.cardSub}>seçili dönemdeki {actualTotal} lead · benzer kategoriler birleştirildi</div>
          <div style={rp.stack}>
            {sectors.map(s => (
              <div key={s.s}>
                <div style={rp.rowHead}><span>{s.s}</span><span style={rp.num}>{s.pct}%</span></div>
                <div style={{ ...rp.barTrack, height: 7 }}><div style={bar(s.pct, s.c)}/></div>
              </div>
            ))}
          </div>
        </div>

        <div style={{ ...rp.card, gridColumn: 'span 3', flexDirection: 'row', gap: 14, alignItems: 'stretch' }}>
          {[
            { label: 'Hazır arama', val: readiness.readyToCall, sub: 'telefon bilgisi tamam' },
            { label: 'Veri tamamlama', val: readiness.needsData, sub: 'telefon / adres eksik' },
            { label: 'Temasa hazır', val: readiness.proposalReady, sub: 'kanıt + hizmet + onaylı taslak' },
          ].map(r => (
            <div key={r.label} style={{ flex: 1, background: 'var(--raised)', borderRadius: 14, padding: '16px 18px' }}>
              <div style={{ fontFamily: "'Space Grotesk'", fontSize: 28, fontWeight: 700, color: 'var(--tx)' }}>{r.val}</div>
              <div style={{ fontSize: 12.5, fontWeight: 600, marginTop: 4, color: 'var(--tx)' }}>{r.label}</div>
              <div style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 2 }}>{r.sub}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

const rp = {
  grid:     { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14, padding: '24px 32px 40px' },
  card:     { background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 'var(--r)', padding: 22, display: 'flex', flexDirection: 'column' },
  cardTitle:{ fontSize: 13, fontWeight: 600, marginBottom: 4, color: 'var(--tx)' },
  cardSub:  { fontSize: 11.5, color: 'var(--muted)', marginBottom: 18 },
  stack:    { display: 'flex', flexDirection: 'column', gap: 14 },
  rowHead:  { display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 6 },
  num:      { fontFamily: "'Space Grotesk'", color: 'var(--sub)' },
  barTrack: { height: 9, background: 'var(--raised)', borderRadius: 99, overflow: 'hidden' },
};

// ── Profile View ──────────────────────────────────────────────────────────

function ProfileView({ user, users, summary, assignments, onLogout }) {
  const list = React.useMemo(() => {
    const byEmail = new Map();
    (users || []).forEach(item => {
      if (item?.email) byEmail.set(item.email, item);
    });
    if (user?.email && !byEmail.has(user.email)) byEmail.set(user.email, user);
    return [...byEmail.values()].sort((a, b) => {
      const ar = a.role === 'admin' ? 0 : 1;
      const br = b.role === 'admin' ? 0 : 1;
      if (ar !== br) return ar - br;
      return String(a.name || a.email).localeCompare(String(b.name || b.email), 'tr');
    });
  }, [users, user]);

  const assignmentCounts = React.useMemo(() => {
    const counts = {};
    (assignments || []).forEach(item => {
      if (item.status !== 'active') return;
      counts[item.user_email] = (counts[item.user_email] || 0) + 1;
    });
    return counts;
  }, [assignments]);

  const currentEmail = user?.email;
  const current = list.find(item => item.email === currentEmail) || user || {};
  const currentCount = user?.role === 'admin'
    ? (summary?.assigned_count ?? Object.values(assignmentCounts).reduce((a, b) => a + b, 0))
    : (summary?.assigned_count ?? assignmentCounts[currentEmail] ?? 0);
  const activeMembers = list.filter(item => item.active !== false).length;
  const bossCount = list.filter(item => item.role === 'admin').length;
  const salesCount = list.filter(item => item.role === 'sales').length;

  return (
    <div style={pf.root}>
      <div style={{ ...pv.header, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 18 }}>
        <div>
          <div style={pv.pageEyebrow}>PROFİL</div>
          <h1 style={pv.pageTitle}>Ekip ve hesap</h1>
          <p style={pv.pageSub}>Aktif oturum, ekip rolleri ve profil fotoğrafları.</p>
        </div>
        <button style={ld.btnGhost} onClick={onLogout}>Çıkış yap</button>
      </div>

      <div style={pf.hero}>
        <div style={pf.heroPhotoWrap}>
          {current.avatar_url ? <img src={current.avatar_url} alt={current.name || current.email || 'Profil'} style={pf.heroPhoto}/> : <div style={pf.heroInitial}>{initialsFor(current.name || current.email)}</div>}
        </div>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={pf.heroEyebrow}>Şu an bu hesaptasın</div>
          <div style={pf.heroName}>{current.name || current.email}</div>
          <div style={pf.heroMeta}>
            <span>{current.email}</span>
            <span>·</span>
            <span>{current.title || roleLabel(current.role)}</span>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 16 }}>
            <ProfilePill role={current.role}/>
            <span style={pf.softPill}>{current.active === false ? 'Pasif' : 'Aktif hesap'}</span>
            <span style={pf.softPill}>{currentCount} atanmış lead</span>
          </div>
        </div>
        <div style={pf.heroStats}>
          <div style={pf.statBox}><span>{list.length}</span><small>Toplam kişi</small></div>
          <div style={pf.statBox}><span>{activeMembers}</span><small>Aktif</small></div>
          <div style={pf.statBox}><span>{bossCount}</span><small>Patron</small></div>
          <div style={pf.statBox}><span>{salesCount}</span><small>Çalışan</small></div>
        </div>
      </div>

      <div style={pf.sectionHead}>
        <div>
          <div style={ld.eyebrow}>EKİP</div>
          <div style={pf.sectionTitle}>Zeplin kullanıcıları</div>
        </div>
        <div style={pf.sectionHint}>Fotoğraflar canlı profilden geliyor.</div>
      </div>

      <div style={pf.teamGrid}>
        {list.map(member => {
          const isMe = member.email === currentEmail;
          const count = assignmentCounts[member.email] || 0;
          return (
            <div key={member.email} style={{ ...pf.memberCard, ...(isMe ? pf.memberCardActive : null) }}>
              <div style={pf.memberPhotoWrap}>
                {member.avatar_url ? <img src={member.avatar_url} alt={member.name || member.email} style={pf.memberPhoto}/> : <div style={pf.memberInitial}>{initialsFor(member.name || member.email)}</div>}
                {isMe && <span style={pf.meBadge}>Bu hesap</span>}
              </div>
              <div style={pf.memberBody}>
                <div style={pf.memberName}>{member.name || member.email}</div>
                <div style={pf.memberEmail}>{member.email}</div>
                <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap', marginTop: 12 }}>
                  <ProfilePill role={member.role}/>
                  <span style={pf.softPill}>{member.title || roleLabel(member.role)}</span>
                  <span style={member.active === false ? pf.passivePill : pf.softPill}>{member.active === false ? 'Pasif' : 'Aktif'}</span>
                </div>
              </div>
              <div style={pf.memberFooter}>
                <span>Atanmış lead</span>
                <strong>{user?.role === 'admin' || isMe ? count : '—'}</strong>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ProfilePill({ role }) {
  const tone = roleTone(role);
  return <span style={{ ...pf.rolePill, background: tone.bg, color: tone.fg, borderColor: tone.bd }}>{roleLabel(role)}</span>;
}

const pf = {
  root:           { flex: 1, minWidth: 0, background: 'var(--bg)', color: 'var(--tx)' },
  hero:           { margin: '24px 32px 0', padding: 24, border: '1px solid var(--line)', borderRadius: 24, background: 'linear-gradient(135deg, var(--panel), var(--panel2))', display: 'flex', flexWrap: 'wrap', gap: 22, alignItems: 'center' },
  heroPhotoWrap:  { width: 136, height: 136, borderRadius: 24, overflow: 'hidden', border: '1px solid var(--line)', background: 'var(--raised)', boxShadow: '0 20px 44px rgba(0,0,0,0.12)' },
  heroPhoto:      { width: '100%', height: '100%', objectFit: 'cover', display: 'block' },
  heroInitial:    { width: '100%', height: '100%', display: 'grid', placeItems: 'center', fontFamily: "'Space Grotesk'", fontSize: 34, fontWeight: 700, color: 'var(--accent-ink)', background: 'var(--accent)' },
  heroEyebrow:    { fontFamily: "'Space Grotesk'", fontSize: 11, color: 'var(--muted)', letterSpacing: 1.4, textTransform: 'uppercase', marginBottom: 8 },
  heroName:       { fontFamily: "'Space Grotesk'", fontSize: 42, lineHeight: 1, fontWeight: 700, letterSpacing: '-0.04em', color: 'var(--tx)' },
  heroMeta:       { marginTop: 10, display: 'flex', gap: 8, flexWrap: 'wrap', color: 'var(--sub)', fontSize: 13.5 },
  heroStats:      { display: 'grid', gridTemplateColumns: 'repeat(2, minmax(110px, 1fr))', gap: 10, flex: '1 1 260px', maxWidth: 380 },
  statBox:        { background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 16, padding: 15, minHeight: 82, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' },
  sectionHead:    { margin: '28px 32px 12px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: 12, flexWrap: 'wrap' },
  sectionTitle:   { fontFamily: "'Space Grotesk'", fontSize: 24, fontWeight: 700, letterSpacing: '-0.03em' },
  sectionHint:    { fontSize: 12.5, color: 'var(--muted)' },
  teamGrid:       { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14, padding: '0 32px 40px' },
  memberCard:     { background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 22, overflow: 'hidden', display: 'flex', flexDirection: 'column', minWidth: 0 },
  memberCardActive:{ borderColor: 'rgba(197,242,74,0.65)', boxShadow: '0 16px 38px rgba(197,242,74,0.12)' },
  memberPhotoWrap:{ position: 'relative', aspectRatio: '1 / 1', background: 'var(--raised)', overflow: 'hidden' },
  memberPhoto:    { width: '100%', height: '100%', objectFit: 'cover', display: 'block' },
  memberInitial:  { width: '100%', height: '100%', display: 'grid', placeItems: 'center', fontFamily: "'Space Grotesk'", fontSize: 28, fontWeight: 700, color: 'var(--accent-ink)', background: 'var(--accent)' },
  meBadge:        { position: 'absolute', top: 12, left: 12, background: 'var(--accent)', color: 'var(--accent-ink)', borderRadius: 999, padding: '6px 10px', fontSize: 11, fontWeight: 700 },
  memberBody:     { padding: 16, minHeight: 126 },
  memberName:     { fontFamily: "'Space Grotesk'", fontSize: 18, fontWeight: 700, letterSpacing: '-0.02em', color: 'var(--tx)' },
  memberEmail:    { marginTop: 4, fontSize: 12.5, color: 'var(--muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' },
  memberFooter:   { marginTop: 'auto', padding: '12px 16px', borderTop: '1px solid var(--line)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'var(--sub)', fontSize: 12.5 },
  rolePill:       { border: '1px solid', borderRadius: 999, padding: '5px 9px', fontSize: 11.5, fontWeight: 700 },
  softPill:       { border: '1px solid var(--line)', background: 'var(--raised)', color: 'var(--sub)', borderRadius: 999, padding: '5px 9px', fontSize: 11.5, fontWeight: 600 },
  passivePill:    { border: '1px solid rgba(255,107,107,0.25)', background: 'rgba(255,107,107,0.1)', color: '#ff8f8f', borderRadius: 999, padding: '5px 9px', fontSize: 11.5, fontWeight: 600 },
};



export {
  AdminView,
  AnalyticsView,
  HizmetlerView,
  LeadDetail,
  PipelineView,
  ProfileView,
};
