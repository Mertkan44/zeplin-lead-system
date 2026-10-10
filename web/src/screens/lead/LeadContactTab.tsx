// İletişim tab: per-channel drafts to edit and approve, the AI e-mail draft,
// what to ask and how to answer objections, and the call-prep note.
import { useState } from 'react';

import { copyEmailDraft, createProposal } from '../../data/leadActions';
import type { Lead } from '../../data/types';
import { CommunicationCenter } from './CommunicationCenter';
import styles from './LeadDetail.module.css';

export function LeadContactTab({ lead }: { lead: Lead }) {
  const [feedback, setFeedback] = useState('');
  const [copied, setCopied] = useState(false);
  const [showEmail, setShowEmail] = useState(true);
  const playbook = lead.sales_playbook || {};
  const hasPlaybook = Boolean(playbook.summary || (playbook.channel_drafts || []).length);

  function copyEmail() {
    copyEmailDraft(lead).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }).catch(() => setFeedback('Taslak kopyalandı ama kaydedilemedi.'));
  }

  return (
    <div>
      {feedback && <div className={styles.inlineNotice} role="status">{feedback}</div>}
        {hasPlaybook && (
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

      {!hasPlaybook && !lead.ai_email && (
        <div className={`${styles.card} ${styles.cardBody}`}>
          <div className={styles.findingsEmpty}>Bu lead için hazırlanmış mesaj taslağı yok. Önce araştırmayı tamamla; kanıt yeterliyse taslaklar burada görünür.</div>
        </div>
      )}

      <div className={`${styles.card} ${styles.cardBody} ${styles.cardHeaderRow}`}>
        <div>
          <div className={styles.eyebrow}>GÖRÜŞME NOTU</div>
          <div className={styles.findingEvidence}>Kanıtlar, sunulabilecek işler ve sorulacak sorular tek dosyada; müşteriye gönderilmez.</div>
        </div>
        <button type="button" className={styles.button} onClick={() => { createProposal(lead).catch(() => setFeedback('Not indirildi ama kaydedilemedi.')); }}>Görüşme notunu indir</button>
      </div>
    </div>
  );
}
