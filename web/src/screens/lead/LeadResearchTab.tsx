// Araştırma tab: what the team checked, what the research found, which
// services fit, and the audit findings behind them.
import { useState } from 'react';

import { openFixContext } from '../../data/leadActions';
import type { AuditCheck, Lead, ServiceMatch } from '../../data/types';
import { findingSeverity, getLeadReadiness, verifiedInstagram } from '../../domain/lead';
import { openExternal } from '../../lib/browser';
import { ManualVerificationCard } from './ManualVerificationCard';
import { ResearchBriefCard } from './ResearchBriefCard';
import styles from './LeadDetail.module.css';

const SEVERITY_CLASS: Record<string, string> = {
  Kritik: styles.sevCritical,
  Yüksek: styles.sevHigh,
  Orta: styles.sevMedium,
  Düşük: styles.sevLow,
};

export function LeadResearchTab({ lead, placesEnabled }: { lead: Lead; placesEnabled: boolean }) {
  const [feedback, setFeedback] = useState('');
  const findings = lead.audit_findings || [];
  const opportunityCount = findings.filter(finding => finding.finding_type === 'opportunity').length;
  const unknownChecks: AuditCheck[] = (lead.audit_checks || []).filter(check => check.status === 'unknown');
  const serviceMatches = lead.matched_services || [];
  const displayedServices: ServiceMatch[] = serviceMatches.length > 0 ? serviceMatches : lead.discovery_services || [];
  const isDiscoveryOnly = serviceMatches.length === 0;
  const pkg = lead.recommended_package || {};
  const readiness = getLeadReadiness(lead);
  const socialVerified = verifiedInstagram(lead);
  const manualInstagram = lead.manual_verification?.instagram?.checked ? lead.manual_verification.instagram : null;
  const stats = socialVerified && lead.social?.stats?.lookup_status === 'found' ? lead.social.stats : null;
  const shown = (value: unknown) => (value !== null && value !== undefined ? String(value) : null);
  const socialStats: Array<[string, string]> = [
    ['Instagram', manualInstagram ? 'Ekip kontrol etti' : socialVerified ? 'Doğrulandı' : 'Doğrulanmadı'],
    ['Takipçi', shown(manualInstagram?.followers) ?? shown(stats?.followers) ?? '—'],
    ['Gönderi', shown(manualInstagram?.post_count) ?? shown(stats?.post_count) ?? '—'],
    ['Ort. beğeni', shown(stats?.avg_likes) ?? '—'],
    ['Etkileşim', stats?.engagement_rate !== null && stats?.engagement_rate !== undefined ? `%${stats.engagement_rate}` : '—'],
  ];

  return (
    <div>
      {feedback && <div className={styles.inlineNotice} role="status">{feedback}</div>}
      <section className={`${styles.card} ${styles.cardBody}`} aria-labelledby="readiness-title">
        <div className={styles.eyebrow}>HAZIRLIK</div>
        <h2 id="readiness-title" className={`${styles.cardTitle} ${styles.sideTitle}`}>Temas için gerekenler</h2>
        <ul className={styles.readiness}>
          {readiness.map(item => (
            <li key={item.label} className={item.ready ? styles.ready : styles.notReady}>
              <span>{item.ready ? 'Hazır' : 'Eksik'}</span>
              <strong>{item.label}</strong>
            </li>
          ))}
        </ul>
      </section>

      <ManualVerificationCard lead={lead} placesEnabled={placesEnabled} onFeedback={setFeedback} />

      <ResearchBriefCard brief={lead.research_brief_v2 || null} />

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
    </div>
  );
}
