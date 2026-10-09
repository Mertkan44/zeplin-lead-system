// One lead: who they are, what the research found, what to offer, and the
// next step; on the side the contact checklist, pipeline status, timeline
// and a quick note. Render with key={lead id} so nothing carries over to the
// next lead (an unsaved note is kept per lead, lib/drafts.ts).
import { useRef, useState } from 'react';

import { copyEmailDraft, openFixContext, recordCallStarted, startLeadAction } from '../../data/leadActions';
import { addOutreach, refreshWorkspace } from '../../data/mutations';
import type { AuditCheck, Lead, LeadStatus, ServiceMatch } from '../../data/types';
import { mergeEvents, useCrm, useLeadTimeline, useSession } from '../../data/workspace';
import { actionMeta, AI_STATE_NOTES, STATUS_OPTIONS } from '../../domain/catalog';
import { fmtDate, fmtShortDateTime } from '../../domain/format';
import { findingSeverity, getLeadReadiness, getPrimaryActionMeta, scoreIsAvailable, telHref, verifiedInstagram, websiteHost } from '../../domain/lead';
import { newRequestId, openExternal } from '../../lib/browser';
import { useDraft } from '../../lib/drafts';
import { Button, Link, StatusBadge } from '../../ui';
import { CommunicationCenter } from './CommunicationCenter';
import { ManualVerificationCard } from './ManualVerificationCard';
import { ResearchBriefCard } from './ResearchBriefCard';
import styles from './LeadDetail.module.css';

const SEVERITY_CLASS: Record<string, string> = {
  Kritik: styles.sevCritical,
  Yüksek: styles.sevHigh,
  Orta: styles.sevMedium,
  Düşük: styles.sevLow,
};

const RING = 326.7;

export interface LeadDetailViewProps {
  lead: Lead;
  index: number;
  total: number;
  status: LeadStatus;
  homePath: string;
  placesEnabled: boolean;
  onStatusChange: (status: LeadStatus) => void;
  onPrev: () => void;
  onNext: () => void;
  onOpenResult: () => void;
}

export function LeadDetailView({ lead, index, total, status, homePath, placesEnabled, onStatusChange, onPrev, onNext, onOpenResult }: LeadDetailViewProps) {
  const crm = useCrm();
  const { user } = useSession();
  // The workspace carries the last 30 days of events; this adds the lead's full timeline.
  const timeline = useLeadTimeline(user.email, lead.name);
  const [note, setNote] = useDraft(`note:${lead.lead_id ?? lead.name}`);
  const noteRequestRef = useRef<{ text: string; id: string } | null>(null);
  const [showReport, setShowReport] = useState(false);
  const [showEmail, setShowEmail] = useState(false);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState('');

  const findings = lead.audit_findings || [];
  const opportunityCount = findings.filter(finding => finding.finding_type === 'opportunity').length;
  const unknownChecks: AuditCheck[] = (lead.audit_checks || []).filter(check => check.status === 'unknown');
  const serviceMatches = lead.matched_services || [];
  const displayedServices: ServiceMatch[] = serviceMatches.length > 0 ? serviceMatches : lead.discovery_services || [];
  const isDiscoveryOnly = serviceMatches.length === 0;
  const pkg = lead.recommended_package || {};
  const events = mergeEvents(crm.eventsFor(lead.name), timeline.data || []);
  const primary = getPrimaryActionMeta(lead);
  const readiness = getLeadReadiness(lead);
  const socialVerified = verifiedInstagram(lead);
  const manualInstagram = lead.manual_verification?.instagram?.checked ? lead.manual_verification.instagram : null;
  const stats = socialVerified && lead.social?.stats?.lookup_status === 'found' ? lead.social.stats : null;
  const scoreAvailable = scoreIsAvailable(lead);
  const playbook = lead.sales_playbook || {};
  const workflow = lead.workflow || {};
  const contactReady = Boolean(workflow.ready_to_contact || workflow.latest_contact_at);
  const websiteUrl = lead.website?.website_url;
  const instagramUrl = socialVerified ? lead.social?.instagram_url : undefined;

  const shown = (value: unknown) => (value !== null && value !== undefined ? String(value) : null);
  const socialStats: Array<[string, string]> = [
    ['Instagram', manualInstagram ? 'Ekip kontrol etti' : socialVerified ? 'Doğrulandı' : 'Doğrulanmadı'],
    ['Takipçi', shown(manualInstagram?.followers) ?? shown(stats?.followers) ?? '—'],
    ['Gönderi', shown(manualInstagram?.post_count) ?? shown(stats?.post_count) ?? '—'],
    ['Ort. beğeni', shown(stats?.avg_likes) ?? '—'],
    ['Etkileşim', stats?.engagement_rate !== null && stats?.engagement_rate !== undefined ? `%${stats.engagement_rate}` : '—'],
  ];

  function copyEmail() {
    copyEmailDraft(lead).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }).catch(() => setFeedback('Taslak kopyalandı ama kaydedilemedi.'));
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
    addOutreach(lead.name, 'note_added', new Date().toISOString(), value, noteRequestRef.current.id)
      .then(() => {
        noteRequestRef.current = null;
        setNote('');
        setFeedback('Not kaydedildi.');
        void refreshWorkspace();
      })
      .catch(() => setFeedback('Not kaydedilemedi; metnin duruyor. Bağlantıyı kontrol edip tekrar kaydet.'))
      .finally(() => setBusy(false));
  }

  function runPrimaryAction() {
    setFeedback('');
    setBusy(true);
    startLeadAction(lead)
      .then(result => {
        setFeedback(result.feedback || 'Aksiyon kaydedildi.');
        void refreshWorkspace();
      })
      .catch((error: Error) => setFeedback(error?.message || 'Aksiyon tamamlanamadı. Lütfen tekrar dene.'))
      .finally(() => setBusy(false));
  }

  return (
    <main className={styles.root}>
      <header className={styles.top}>
        <nav aria-label="Konum">
          <ol className={styles.crumbs}>
            <li><Link to={homePath}>Workspace</Link></li>
            <li aria-hidden="true">/</li>
            <li><Link to="/raporlar">Leadler</Link></li>
            <li aria-hidden="true">/</li>
            <li className={styles.crumbCurrent} aria-current="page">{lead.name}</li>
          </ol>
        </nav>
        <div className={styles.nav}>
          <Button onClick={onPrev} disabled={index === 0}>← Önceki</Button>
          <Button onClick={onNext} disabled={index === total - 1}>Sonraki →</Button>
        </div>
      </header>

      <section className={styles.hero}>
        <div className={styles.heroLeft}>
          <div className={styles.statusRow}>
            <StatusBadge status={status} />
            {(lead.category || lead.sector) && <span className={styles.metaTag}>{lead.category || lead.sector}</span>}
            {lead.city && <span className={styles.metaTag}>{lead.city}</span>}
            {lead.last_analyzed && <span className={styles.metaText}>Son analiz · {fmtDate(lead.last_analyzed)}</span>}
          </div>
          <h1 className={styles.title}>{lead.name}</h1>
          <div className={styles.urls}>
            {websiteUrl && <a href={websiteUrl} target="_blank" rel="noopener noreferrer" className={styles.urlChip}>{websiteHost(websiteUrl)} ↗</a>}
            {instagramUrl && <a href={instagramUrl} target="_blank" rel="noopener noreferrer" className={styles.urlChip}>@{lead.social?.instagram_username || 'instagram'} ↗</a>}
            {lead.maps_url && <a href={lead.maps_url} target="_blank" rel="noopener noreferrer" className={styles.urlChip}>Google Maps ↗</a>}
            {lead.phone && <span className={styles.urlChip}>{lead.phone}</span>}
          </div>
          <div className={styles.quickActions}>
            {contactReady && lead.phone && <a href={telHref(lead.phone)} onClick={() => recordCallStarted(lead)} className={styles.quickButton}>Telefonu aç</a>}
            {websiteUrl && <button type="button" className={styles.quickButton} onClick={() => openExternal(websiteUrl)}>Siteyi aç</button>}
            {instagramUrl && <button type="button" className={styles.quickButton} onClick={() => openExternal(instagramUrl)}>Instagram aç</button>}
            {lead.maps_url && <button type="button" className={styles.quickButton} onClick={() => openExternal(lead.maps_url)}>Maps aç</button>}
            {lead.ai_email && <button type="button" className={styles.quickButton} onClick={copyEmail}>{copied ? 'Taslak kopyalandı' : 'Taslağı kopyala'}</button>}
            <button
              type="button"
              disabled={!contactReady}
              title={contactReady ? 'Temas ekranını aç' : 'Önce zorunlu kontrolleri tamamla'}
              className={`${styles.quickButton} ${styles.quickPrimary}`}
              onClick={onOpenResult}
            >
              {contactReady ? 'Temas ekranı' : `${workflow.completed_count || 0}/${workflow.required_count || 0} kontrol`}
            </button>
          </div>
        </div>
        <div className={styles.heroRight}>
          <svg width="120" height="120" viewBox="0 0 120 120" role="img" aria-label={scoreAvailable ? `Skor ${lead.scoring.score} / 100` : `Skor yok, %${lead.scoring?.coverage || 0} kapsam`}>
            <circle cx="60" cy="60" r="52" fill="none" stroke="var(--line2)" strokeWidth="6" />
            <circle cx="60" cy="60" r="52" fill="none" stroke={scoreAvailable ? 'var(--accent)' : 'var(--muted)'} strokeWidth="6" strokeDasharray={RING} strokeDashoffset={scoreAvailable ? RING * (1 - lead.scoring.score / 100) : RING} transform="rotate(-90 60 60)" strokeLinecap="round" />
            <text x="60" y="60" textAnchor="middle" fontSize="32" fontWeight="600" fill="var(--tx)" fontFamily="Space Grotesk">{scoreAvailable ? lead.scoring.score : '—'}</text>
            <text x="60" y="80" textAnchor="middle" fontSize="11" fill="var(--muted)" fontFamily="Space Grotesk">{scoreAvailable ? '/100' : `%${lead.scoring?.coverage || 0} kapsam`}</text>
          </svg>
          <div className={styles.gradePill} aria-label={`Sınıf ${scoreAvailable ? lead.scoring.grade : 'yok'}`}>{scoreAvailable ? lead.scoring.grade : '?'}</div>
        </div>
      </section>

      {lead.next_action && (
        <div className={styles.nextAction}>
          <div>
            <div className={styles.naEyebrow}>SONRAKİ EN İYİ AKSİYON · ÖNCELİK {lead.sales_priority_score || '—'}</div>
            <div className={styles.naTitle}>{lead.next_action}</div>
            {lead.priority_reason && <div className={styles.naDesc}>{lead.priority_reason}</div>}
            <div className={styles.naHelper}>{primary.helper}</div>
            {feedback && <div className={styles.feedback}>{feedback}</div>}
          </div>
          <div className={styles.naActions}>
            <Button onClick={onNext} disabled={busy}>Atla</Button>
            <Button variant="primary" onClick={runPrimaryAction} busy={busy} busyLabel={primary.intent === 'generate_ai' ? 'Rapor hazırlanıyor…' : 'Kaydediliyor…'}>{primary.label} →</Button>
          </div>
        </div>
      )}

      <section className={styles.columns}>
        <div>
          <div className={`${styles.card} ${styles.statsCard}`}>
            <div className={styles.eyebrow}>SOSYAL SİNYALLER</div>
            <h2 className={styles.cardTitle}>Etkileşim ve büyüme</h2>
            <dl className={styles.stats}>
              {socialStats.map(([label, value]) => (
                <div key={label} className={styles.stat}>
                  <dt className={styles.statLabel}>{label}</dt>
                  <dd className={styles.statValue}>{value}</dd>
                </div>
              ))}
            </dl>
          </div>

          <ManualVerificationCard lead={lead} placesEnabled={placesEnabled} onFeedback={setFeedback} />

          <ResearchBriefCard brief={lead.research_brief_v2 || null} />

          {playbook.summary && (
            <section className={styles.card} aria-labelledby="playbook-title">
              <div className={`${styles.cardHeader} ${styles.cardHeaderRow}`}>
                <div>
                  <div className={styles.eyebrow}>SATIŞ REHBERİ</div>
                  <h2 id="playbook-title" className={styles.cardTitle}>Bu işletmeyle nasıl konuşacağız?</h2>
                </div>
                <span className={playbook.discovery_only ? styles.badgeDiscovery : styles.badgeVerified}>
                  {playbook.discovery_only ? 'Keşif görüşmesi' : 'Kanıta dayalı'}
                </span>
              </div>
              <div className={styles.salesSummary}>{playbook.summary}</div>
              {(playbook.evidence_points || []).length > 0 && (
                <div className={styles.salesEvidence}>
                  {(playbook.evidence_points as Array<{ title: string; evidence: string }>).slice(0, 3).map((item, itemIndex) => (
                    <div key={`${item.title}-${itemIndex}`} className={styles.salesEvidenceItem}>
                      <div className={styles.miniLabel}>KANIT {itemIndex + 1}</div>
                      <strong>{item.title}</strong>
                      <span>{item.evidence}</span>
                    </div>
                  ))}
                </div>
              )}
              <CommunicationCenter key={String(playbook.version ?? '')} lead={lead} playbook={playbook} onFeedback={setFeedback} />
              <div className={styles.scriptGrid}>
                <div>
                  <div className={styles.miniLabel}>GÖRÜŞMEDE SOR</div>
                  <ul className={styles.cleanList}>
                    {(playbook.discovery_questions || []).slice(0, 4).map((item: string, itemIndex: number) => <li key={itemIndex}>{item}</li>)}
                  </ul>
                </div>
                <div>
                  <div className={styles.miniLabel}>İTİRAZA HAZIRLIK</div>
                  {(playbook.objection_responses || []).slice(0, 3).map((item: { objection: string; response: string }, itemIndex: number) => (
                    <div key={itemIndex} className={styles.objectionRow}><strong>{item.objection}</strong><span>{item.response}</span></div>
                  ))}
                </div>
              </div>
            </section>
          )}

          {displayedServices.length > 0 ? (
            <div className={`${styles.card} ${styles.packCard}`}>
              <div className={styles.packTop}>
                <div>
                  <div className={styles.eyebrow}>{isDiscoveryOnly ? 'GÖRÜŞMEDE DOĞRULA' : 'BİRİNCİL HİZMET ÖNERİSİ'}</div>
                  <h3 className={styles.packTitle}>{pkg.primary_service || pkg.name}</h3>
                  <div className={styles.packDesc}>{pkg.summary || 'Öneri, doğrulanan tarama sinyallerine dayanır.'}</div>
                </div>
                <span className={pkg.requires_discovery ? styles.badgeDiscovery : styles.badgeVerified}>
                  {pkg.requires_discovery ? 'Görüşmede doğrula' : 'Kanıtlandı'}
                </span>
              </div>
              {(pkg.evidence || []).length > 0 && (
                <div className={styles.packTags}>
                  {(pkg.evidence as string[]).map((item, itemIndex) => <span key={itemIndex} className={styles.tagPrimary}>{item}</span>)}
                </div>
              )}
            </div>
          ) : (
            <div className={`${styles.card} ${styles.packCard} ${styles.packEmpty}`}>
              <div className={styles.eyebrow}>HİZMET ÖNERİSİ</div>
              <div className={styles.packEmptyText}>Henüz doğrudan satış iddiası oluşturacak bir açık doğrulanmadı. Sektöre uygun keşif sorularını kullan.</div>
            </div>
          )}

          {displayedServices.length > 0 && (
            <section className={styles.card} aria-labelledby="needs-title">
              <div className={`${styles.cardHeader} ${styles.cardHeaderRow}`}>
                <div>
                  <div className={styles.eyebrow}>{isDiscoveryOnly ? 'UYGUN OLABİLECEK HİZMETLER' : 'KANITLANAN İHTİYAÇLAR'}</div>
                  <h2 id="needs-title" className={styles.cardTitle}>Ne gördük, ne sunabiliriz?</h2>
                </div>
                <span className={styles.badgeCount}>{isDiscoveryOnly ? `${displayedServices.length} keşif başlığı` : `${serviceMatches.length} hizmet sinyali`}</span>
              </div>
              {displayedServices.slice(0, 4).map((service, serviceIndex) => (
                <div key={service.slug || serviceIndex} className={styles.opportunity}>
                  <div className={styles.opportunityTop}>
                    <div>
                      <div className={styles.opportunityIndex}>0{serviceIndex + 1} · {service.category || 'Hizmet'}</div>
                      <div className={styles.opportunityTitle}>{service.name}</div>
                      <div className={styles.opportunityDesc}>{service.desc}</div>
                    </div>
                    <span className={service.requires_discovery ? styles.badgeDiscovery : styles.badgeVerified}>
                      {service.requires_discovery ? 'Kontrol et' : `%${service.confidence || 0} güven`}
                    </span>
                  </div>
                  <div className={styles.opportunityColumns}>
                    {(service.evidence || []).length > 0 && (
                      <div>
                        <div className={styles.miniLabel}>TESPİT EDİLEN AÇIK</div>
                        <ul className={styles.evidenceList}>
                          {(service.evidence || []).map((item, itemIndex) => (
                            <li key={itemIndex} className={styles.evidenceItem}><span className={styles.evidenceDot} aria-hidden="true" />{item}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    <div>
                      <div className={styles.miniLabel}>BİZ NE TESLİM EDERİZ?</div>
                      <ul className={styles.cleanList}>
                        {(service.deliverables || []).slice(0, 3).map((item, itemIndex) => <li key={itemIndex}>{item}</li>)}
                      </ul>
                    </div>
                  </div>
                  {(service.discovery_questions || []).length > 0 && (
                    <div className={styles.discoveryBox}>
                      <div className={styles.miniLabel}>GÖRÜŞMEDE SOR</div>
                      <div className={styles.questions}>
                        {(service.discovery_questions || []).slice(0, 3).map((item, itemIndex) => <span key={itemIndex} className={styles.question}>{item}</span>)}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </section>
          )}

          <section className={styles.card} aria-labelledby="findings-title">
            <div className={`${styles.cardHeader} ${styles.cardHeaderRow}`}>
              <div>
                <div className={styles.eyebrow}>TARAMA BULGULARI VE FIRSATLAR</div>
                <h2 id="findings-title" className={styles.cardTitle}>
                  {findings.length > 0 ? `${findings.length - opportunityCount} açık · ${opportunityCount} büyüme fırsatı` : 'Kanıtlı açık yok'}
                </h2>
              </div>
              <span className={styles.badgeCount}>%{lead.scoring?.coverage || 0} kapsam · %{lead.scoring?.confidence || 0} güven</span>
            </div>
            {findings.length === 0 ? (
              <div className={styles.findingsEmpty}>Bu “sorun yok” anlamına gelmez. {unknownChecks.length} kontrol henüz güvenilir biçimde tamamlanamadı.</div>
            ) : findings.map((finding, findingIndex) => {
              const isOpportunity = finding.finding_type === 'opportunity';
              const severity = findingSeverity(finding);
              return (
                <div key={finding.code || findingIndex} className={styles.finding}>
                  <div className={`${styles.severity} ${isOpportunity ? styles.sevInfo : SEVERITY_CLASS[severity] || styles.sevInfo}`}>{isOpportunity ? 'Fırsat' : severity}</div>
                  <div className={styles.findingBody}>
                    <div className={styles.findingTitle}>{finding.title}</div>
                    <div className={styles.findingEvidence}><strong>Kanıt:</strong> {finding.evidence}</div>
                    <div className={styles.findingImpact}><strong>İş etkisi:</strong> {finding.impact}</div>
                    {finding.talking_point && <div className={styles.talkingPoint}>Görüşmede söyle: “{finding.talking_point}”</div>}
                    {finding.verification && <div className={styles.verifyText}>Teyit: {finding.verification}</div>}
                  </div>
                  <div className={styles.findingSide}>
                    <span className={styles.badgeCount}>%{finding.confidence || 0} güven</span>
                    <button type="button" className={styles.button} onClick={() => setFeedback(openFixContext(lead, finding))}>Kaynağı aç →</button>
                  </div>
                </div>
              );
            })}
          </section>

          {unknownChecks.length > 0 && (
            <section className={styles.card} aria-labelledby="unknown-title">
              <div className={styles.cardHeader}>
                <div className={styles.eyebrow}>DOĞRULANMAYAN KONTROLLER</div>
                <h2 id="unknown-title" className={styles.cardTitle}>{unknownChecks.length} başlık satış iddiası olarak kullanılmıyor</h2>
              </div>
              {unknownChecks.slice(0, 8).map((check, checkIndex) => (
                <div key={`${check.code}-${checkIndex}`} className={styles.unknownRow}>
                  <div>
                    <div className={styles.findingTitle}>{check.label}</div>
                    <div className={styles.findingEvidence}>{check.note}</div>
                  </div>
                  {check.source_url && <button type="button" className={styles.button} onClick={() => openExternal(check.source_url)}>Kontrol et →</button>}
                </div>
              ))}
            </section>
          )}

          {lead.ai_report && (
            <section className={styles.card}>
              <button type="button" className={styles.cardToggle} aria-expanded={showReport} onClick={() => setShowReport(open => !open)}>
                <div className={styles.eyebrow}>GÖRÜŞME HAZIRLIĞI</div>
                <div className={styles.cardTitle}>AI ihtiyaç özeti {showReport ? '▲' : '▼'}</div>
              </button>
              {showReport && lead.ai_state && AI_STATE_NOTES[lead.ai_state] && <div className={styles.warning}>{AI_STATE_NOTES[lead.ai_state]}</div>}
              {showReport && <div className={styles.reportText}>{lead.ai_report}</div>}
            </section>
          )}

          {lead.ai_email && (
            <section className={styles.card}>
              <button type="button" className={styles.cardToggle} aria-expanded={showEmail} onClick={() => setShowEmail(open => !open)}>
                <div className={styles.eyebrow}>ONAY BEKLEYEN TASLAK</div>
                <div className={styles.cardTitle}>E-posta taslağı {showEmail ? '▲' : '▼'}</div>
              </button>
              {showEmail && (
                <div>
                  <div className={styles.warning}>Göndermeden önce işletme bilgilerini, kanıtı ve önerilen hizmeti kontrol et.</div>
                  <div className={styles.cardBody}><button type="button" className={styles.button} onClick={copyEmail}>{copied ? '✓ Kopyalandı' : 'Kopyala'}</button></div>
                  <div className={styles.emailText}>{lead.ai_email}</div>
                </div>
              )}
            </section>
          )}
        </div>

        <aside className={styles.side} aria-label="Lead durumu">
          <div className={styles.sideCard}>
            <div className={styles.eyebrow}>HAZIRLIK</div>
            <h2 className={`${styles.cardTitle} ${styles.sideTitle}`}>Temas checklist</h2>
            <ul className={styles.readiness}>
              {readiness.map(item => (
                <li key={item.label} className={item.ready ? styles.ready : styles.notReady}>
                  <span>{item.ready ? 'Hazır' : 'Eksik'}</span>
                  <strong>{item.label}</strong>
                </li>
              ))}
            </ul>
          </div>

          <div className={styles.sideCard}>
            <div className={styles.eyebrow}>DURUM</div>
            <h2 className={`${styles.cardTitle} ${styles.sideTitle}`}>Pipeline konumu</h2>
            <div className={styles.statusButtons} role="group" aria-label="Pipeline durumu">
              {STATUS_OPTIONS.map(([key, label]) => (
                <button type="button" key={key} className={styles.button} aria-pressed={status === key} onClick={() => onStatusChange(key)}>{label}</button>
              ))}
            </div>
          </div>

          <div className={styles.sideCard}>
            <div className={styles.eyebrow}>AKTİVİTE</div>
            <h2 className={`${styles.cardTitle} ${styles.sideTitle}`}>Zaman çizelgesi</h2>
            {events[0] && (
              <div className={styles.lastEvent}>
                <div className={styles.miniLabel}>Son hareket</div>
                <div className={styles.lastEventText}>{actionMeta(events[0].action).label}</div>
              </div>
            )}
            <ol className={styles.timeline}>
              {events.map((event, eventIndex) => (
                <li key={`${event.ts}-${eventIndex}`} className={styles.timelineItem}>
                  <span className={styles.timelineDot} aria-hidden="true" />
                  <div>
                    <div className={styles.timelineKind}>{actionMeta(event.action).label}</div>
                    <div className={styles.timelineMeta}>
                      {fmtDate(event.date)}
                      {event.channelLabel ? ` · ${event.channelLabel}` : ''}
                      {event.outcomeLabel ? ` · ${event.outcomeLabel}` : ''}
                      {event.note ? ` · ${event.note}` : ''}
                      {event.followUpAt ? ` · Takip ${fmtShortDateTime(event.followUpAt)}` : ''}
                    </div>
                  </div>
                </li>
              ))}
              {lead.last_analyzed && (
                <li className={styles.timelineItem}>
                  <span className={styles.timelineDot} aria-hidden="true" />
                  <div>
                    <div className={styles.timelineKind}>Tarama tamamlandı</div>
                    <div className={styles.timelineMeta}>{fmtDate(lead.last_analyzed)} · {scoreAvailable ? `Skor ${lead.scoring.score}` : `%${lead.scoring?.coverage || 0} kapsam`}</div>
                  </div>
                </li>
              )}
              <li className={styles.timelineItem}>
                <span className={styles.timelineDot} aria-hidden="true" />
                <div>
                  <div className={styles.timelineKind}>Lead listesine eklendi</div>
                  <div className={styles.timelineMeta}>{lead.city || '—'}</div>
                </div>
              </li>
            </ol>
          </div>

          <div className={styles.sideCard}>
            <div className={styles.eyebrow}>NOT</div>
            <h2 className={`${styles.cardTitle} ${styles.sideTitle}`}><label htmlFor="lead-note">Hızlı not</label></h2>
            <textarea id="lead-note" className={styles.noteInput} value={note} onChange={event => setNote(event.target.value)} placeholder="Lead hakkında not ekle..." />
            <div className={styles.noteFooter}>
              <div className={styles.noteHint} role="status">{feedback || 'Kısa notu zaman çizelgesine ekler.'}</div>
              <button type="button" className={`${styles.saveButton} ${styles.saveSmall}`} onClick={saveNote} disabled={busy || !note.trim()}>
                {busy ? 'Kaydediliyor…' : 'Kaydet'}
              </button>
            </div>
          </div>
        </aside>
      </section>
    </main>
  );
}
