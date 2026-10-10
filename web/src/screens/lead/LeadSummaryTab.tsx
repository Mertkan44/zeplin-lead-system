// Özet tab (review §12.5): the 30-second picture. Why we call, at most three
// strong pieces of evidence, the service to offer with one question to ask,
// the last conversation, and the suggested next step.
import { useState } from 'react';

import { startLeadAction } from '../../data/leadActions';
import { refreshWorkspace } from '../../data/mutations';
import type { Lead, OutreachEvent } from '../../data/types';
import { AI_STATE_NOTES } from '../../domain/catalog';
import { fmtDate } from '../../domain/format';
import { getPrimaryActionMeta } from '../../domain/lead';
import { openExternal } from '../../lib/browser';
import { Button } from '../../ui';
import styles from './LeadPage.module.css';

interface Evidence {
  title: string;
  evidence?: string;
  source_url?: string;
  source_label?: string;
}

export function LeadSummaryTab({ lead, events }: { lead: Lead; events: OutreachEvent[] }) {
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState('');
  const playbook = lead.sales_playbook || {};
  const brief = playbook.call_brief || {};
  const evidence: Evidence[] = (playbook.evidence_points || []).slice(0, 3);
  const pkg = lead.recommended_package || {};
  const service = pkg.primary_service || pkg.name || (lead.matched_services || [])[0]?.name || (lead.discovery_services || [])[0]?.name;
  const question = (playbook.discovery_questions || [])[0] || (pkg.discovery_questions || [])[0];
  const lastResult = events.find(event => event.action === 'contact_result_recorded');
  const step = getPrimaryActionMeta(lead);
  const summary = brief.business_summary || playbook.summary;

  function runStep() {
    setBusy(true);
    setFeedback('');
    startLeadAction(lead)
      .then(result => {
        setFeedback(result.feedback);
        void refreshWorkspace();
      })
      .catch((error: Error) => setFeedback(error?.message || 'Aksiyon tamamlanamadı. Lütfen tekrar dene.'))
      .finally(() => setBusy(false));
  }

  return (
    <div className={styles.stack}>
      <section className={styles.card} aria-labelledby="summary-title">
        <h2 id="summary-title" className={styles.cardTitle}>30 saniyede bu işletme</h2>
        {summary ? <p className={styles.lead}>{summary}</p> : <p className={styles.empty}>Henüz özet yok; araştırma tamamlanınca burada görünür.</p>}
        <div className={styles.why}>
          {lead.next_action && <span><strong>Neden şimdi:</strong> {lead.next_action}</span>}
          {lead.priority_reason && <span>{lead.priority_reason}</span>}
          {brief.conversation_goal && <span><strong>Görüşmenin hedefi:</strong> {brief.conversation_goal}</span>}
        </div>
      </section>

      <section className={styles.card} aria-labelledby="evidence-title">
        <h2 id="evidence-title" className={styles.cardTitle}>Güçlü kanıtlar</h2>
        <p className={styles.cardHint}>Müşteriye söylenebilecek, doğrulanmış bulgular.</p>
        {evidence.length ? (
          <ol className={styles.evidence}>
            {evidence.map((item, index) => (
              <li key={`${item.title}-${index}`} className={styles.evidenceItem}>
                <span className={styles.evidenceIndex} aria-hidden="true">{index + 1}</span>
                <div>
                  <div className={styles.evidenceTitle}>{item.title}</div>
                  {item.evidence && <div className={styles.evidenceText}>{item.evidence}</div>}
                </div>
                {item.source_url && <button type="button" className={styles.sourceLink} onClick={() => openExternal(item.source_url)}>{item.source_label || 'Kaynak'} ↗</button>}
              </li>
            ))}
          </ol>
        ) : (
          <p className={styles.empty}>Kesinleşmiş açık yok. Satış iddiası yerine keşif sorusuyla başla.</p>
        )}
      </section>

      <div className={styles.split}>
        <section className={styles.card} aria-labelledby="offer-title">
          <h2 id="offer-title" className={styles.cardTitle}>Önerilecek hizmet</h2>
          {service ? <div className={styles.kv}><strong>{service}</strong>{pkg.summary && <span>{pkg.summary}</span>}</div> : <p className={styles.empty}>Henüz doğrudan önerilecek hizmet yok.</p>}
          {question && <div className={styles.question}>Sor: “{question}”</div>}
        </section>
        <section className={styles.card} aria-labelledby="last-title">
          <h2 id="last-title" className={styles.cardTitle}>Son görüşme</h2>
          {lastResult ? (
            <div className={styles.kv}>
              <strong>{lastResult.outcomeLabel || 'Sonuç kaydedildi'}</strong>
              <span>{fmtDate(lastResult.date)}{lastResult.channelLabel ? ` · ${lastResult.channelLabel}` : ''}{lastResult.contactName ? ` · ${lastResult.contactName}` : ''}</span>
              {lastResult.note && <span>{lastResult.note}</span>}
            </div>
          ) : <p className={styles.empty}>Henüz görüşme kaydı yok.</p>}
        </section>
      </div>

      <section className={`${styles.card} ${styles.stepCard}`} aria-labelledby="step-title">
        <div>
          <h2 id="step-title" className={styles.cardTitle}>Önerilen adım: {step.label}</h2>
          <p className={styles.cardHint}>{step.helper}</p>
          {feedback && <p className={styles.feedback} role="status">{feedback}</p>}
        </div>
        <Button onClick={runStep} busy={busy} busyLabel={step.intent === 'generate_ai' ? 'Rapor hazırlanıyor…' : 'Kaydediliyor…'}>{step.label}</Button>
      </section>

      {lead.ai_report && (
        <details className={`${styles.card} ${styles.details}`}>
          <summary>AI ihtiyaç özeti</summary>
          {lead.ai_state && AI_STATE_NOTES[lead.ai_state] && <div className={styles.warning}>{AI_STATE_NOTES[lead.ai_state]}</div>}
          <div className={styles.prose}>{lead.ai_report}</div>
        </details>
      )}
    </div>
  );
}
