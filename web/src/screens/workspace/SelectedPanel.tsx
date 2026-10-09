// The lead picked in the workspace list: audit summary, matched services,
// AI report and the quick actions.
import { useState } from 'react';

import { createProposal, recordCallStarted } from '../../data/leadActions';
import { addOutreach } from '../../data/mutations';
import type { AuditCheck, Lead } from '../../data/types';
import { AI_STATE_NOTES } from '../../domain/catalog';
import { scoreIsAvailable, telHref } from '../../domain/lead';
import { copyText } from '../../lib/browser';
import { routeFor } from '../../lib/router';
import { GradeBadge, Link } from '../../ui';
import { IconCall, IconDots, IconMail, IconStar } from '../shared/icons';
import { ScoreRing } from '../shared/ScoreRing';
import styles from './SelectedPanel.module.css';

const AUDIT_ORDER = [
  'website.presence',
  'identity.website_name',
  'website.https',
  'website.viewport',
  'seo.indexable',
  'seo.schema',
  'social.instagram_presence',
  'maps.reputation',
];

const MARKS: Record<string, { mark: string; className: string; label: string }> = {
  pass: { mark: '✓', className: styles.pass, label: 'Geçti' },
  fail: { mark: '✕', className: styles.fail, label: 'Eksik' },
  unknown: { mark: '?', className: styles.unknown, label: 'Bilinmiyor' },
};

function auditRows(lead: Lead): AuditCheck[] {
  const checks = lead.audit_checks || [];
  return AUDIT_ORDER
    .map(code => checks.find(check => check.code === code))
    .filter((check): check is AuditCheck => Boolean(check))
    .slice(0, 6);
}

/** Render with key={lead} so open panels reset when another lead is picked. */
export function SelectedPanel({ lead }: { lead: Lead }) {
  const [reportOpen, setReportOpen] = useState(true);
  const [emailOpen, setEmailOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const detailPath = lead.lead_id != null ? routeFor({ leadId: lead.lead_id }) : null;
  const pkg = lead.recommended_package;
  const hasPackage = Boolean(pkg) && (lead.matched_services || []).length > 0;
  const available = scoreIsAvailable(lead);

  function copyEmail() {
    if (!lead.ai_email) return;
    void copyText(lead.ai_email);
    addOutreach(lead.name, 'email_drafted', new Date().toISOString(), 'Taslak panoya kopyalandı').catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className={styles.inner}>
      <div className={styles.head}>
        <div className={styles.headText}>
          <div className={styles.eyebrow}>Seçili Lead</div>
          {detailPath ? <Link to={detailPath} className={styles.name}>{lead.name}</Link> : <span className={styles.name}>{lead.name}</span>}
          <div className={styles.sub}>{lead.category || lead.sector || 'İşletme'} · {lead.city}</div>
        </div>
        <div className={styles.score}>
          <ScoreRing score={lead.scoring.score} grade={lead.scoring.grade} scoreStatus={lead.scoring.score_status} size={78} stroke={5} />
          <GradeBadge grade={available ? lead.scoring.grade : null} label={available ? `Sınıf ${lead.scoring.grade}` : 'Eksik denetim'} />
        </div>
      </div>

      <div className={styles.metrics}>
        <div className={styles.metric}>
          <div className={styles.metricLabel}>Tahmini Değer</div>
          <div className={styles.metricValue}>{lead.scoring?.coverage ?? 0}%</div>
          <div className={styles.metricNote}>Denetim kapsamı</div>
        </div>
        <div className={styles.metric}>
          <div className={styles.metricLabel}>Satış Önceliği</div>
          <div className={`${styles.metricValue} ${styles.metricAccent}`}>{lead.sales_priority_score || 0}<small>/100</small></div>
        </div>
      </div>

      <div>
        <div className={styles.sectionLabel}>Dijital Denetim</div>
        <ul className={styles.audit}>
          {auditRows(lead).map(check => {
            const mark = MARKS[check.status] || MARKS.unknown;
            return (
              <li key={check.code} className={styles.auditRow}>
                <span className={`${styles.auditMark} ${mark.className}`} role="img" aria-label={mark.label}>{mark.mark}</span>
                <div className={styles.auditText}>
                  <div className={styles.auditLabel}>{check.label}</div>
                  <div className={styles.auditNote} title={check.note}>{check.note}</div>
                </div>
              </li>
            );
          })}
        </ul>
      </div>

      {(lead.matched_services || []).length > 0 && (
        <div>
          <div className={styles.sectionLabel}>Eşleşen Hizmetler</div>
          <div className={styles.services}>
            {(lead.matched_services || []).map(service => <span key={service.slug} className={styles.service}>{service.name}</span>)}
          </div>
        </div>
      )}

      {hasPackage && pkg ? (
        <div className={styles.pkg}>
          <div className={styles.pkgTop}>
            <span className={styles.pkgEyebrow}>Önerilen Hizmet</span>
            {pkg.stage && <span className={styles.pkgStage}>{pkg.stage}</span>}
          </div>
          <div className={styles.pkgBottom}>
            <div className={styles.pkgText}>
              <div className={styles.pkgName}>{pkg.name}</div>
              <div className={styles.pkgMeta}>{pkg.stage || 'Keşif'}{pkg.confidence ? ` · %${pkg.confidence} güven` : ''}</div>
            </div>
            <button type="button" className={styles.pkgButton} onClick={() => { createProposal(lead).catch(() => {}); }}>Görüşme Notu</button>
          </div>
        </div>
      ) : (
        <div className={`${styles.pkg} ${styles.pkgEmpty}`}>
          <span className={styles.pkgEyebrow}>Önerilen Hizmet</span>
          <div className={styles.pkgEmptyText}>Satış iddiası oluşturacak kanıt yok. Aşağıdaki keşif başlıklarını görüşmede doğrula.</div>
        </div>
      )}

      {lead.ai_report && (
        <div>
          <button type="button" className={styles.toggle} aria-expanded={reportOpen} onClick={() => setReportOpen(open => !open)}>
            <span className={styles.toggleLabel}><IconStar /> AI Raporu</span>
            <span className={styles.toggleSign} aria-hidden="true">{reportOpen ? '−' : '+'}</span>
          </button>
          {reportOpen && (
            <div className={styles.togglePanel}>
              {lead.ai_state && AI_STATE_NOTES[lead.ai_state] ? `${AI_STATE_NOTES[lead.ai_state]}\n\n` : ''}{lead.ai_report}
            </div>
          )}
        </div>
      )}

      {lead.ai_email && (
        <div>
          <button type="button" className={styles.toggle} aria-expanded={emailOpen} onClick={() => setEmailOpen(open => !open)}>
            <span className={styles.toggleLabel}><IconMail /> Satış Maili</span>
            <span className={styles.toggleSign} aria-hidden="true">{emailOpen ? '−' : '+'}</span>
          </button>
          {emailOpen && <div className={styles.togglePanel}>{lead.ai_email}</div>}
        </div>
      )}

      <div className={styles.actions}>
        {lead.phone
          ? <a href={telHref(lead.phone)} onClick={() => recordCallStarted(lead)} className={styles.actionCall}><IconCall /> Ara</a>
          : <span className={`${styles.actionCall} ${styles.actionOff}`} aria-disabled="true"><IconCall /> Ara</span>}
        {lead.ai_email
          ? <button type="button" className={styles.actionMail} onClick={copyEmail}><IconMail /> {copied ? 'Kopyalandı' : 'Taslağı Kopyala'}</button>
          : <span className={`${styles.actionMail} ${styles.actionOff}`} aria-disabled="true"><IconMail /> Taslak Yok</span>}
        {detailPath && (
          <Link to={detailPath} className={styles.more} aria-label="Detaylı görünüm" title="Detaylı görünüm"><IconDots /></Link>
        )}
      </div>
    </div>
  );
}
