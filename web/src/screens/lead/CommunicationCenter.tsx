// Per-channel drafts (e-mail, WhatsApp, Instagram, call): edit, copy, approve.
// Nothing is sent from here; approval is recorded as an activity.
import { useState } from 'react';

import { refreshWorkspace, saveDraftReview } from '../../data/mutations';
import type { Lead } from '../../data/types';
import { copyText } from '../../lib/browser';
import styles from './LeadDetail.module.css';

interface ChannelDraft {
  channel: string;
  label: string;
  subject?: string;
  body?: string;
  recipient?: string;
  recipient_available?: boolean;
  review_note?: string;
}

export interface CommunicationCenterProps {
  lead: Lead;
  playbook: Record<string, any>;
  onFeedback: (message: string) => void;
}

/** Render with key={lead + playbook version}: a new playbook starts fresh drafts. */
export function CommunicationCenter({ lead, playbook, onFeedback }: CommunicationCenterProps) {
  const sourceDrafts: ChannelDraft[] = playbook.channel_drafts || [];
  const [activeChannel, setActiveChannel] = useState(
    () => sourceDrafts.find(item => item.recipient_available)?.channel || sourceDrafts[0]?.channel || 'phone',
  );
  const [drafts, setDrafts] = useState<Record<string, ChannelDraft>>(
    () => Object.fromEntries(sourceDrafts.map(item => [item.channel, { ...item }])),
  );
  const [approved, setApproved] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);

  const draft = drafts[activeChannel];
  if (!draft) return null;
  const hasBody = Boolean(draft.body?.trim());

  function updateDraft(field: 'subject' | 'body', value: string) {
    setDrafts(current => ({ ...current, [activeChannel]: { ...current[activeChannel], [field]: value } }));
    setApproved(current => ({ ...current, [activeChannel]: false }));
  }

  function copyDraft() {
    const text = draft.subject ? `Konu: ${draft.subject}\n\n${draft.body}` : draft.body || '';
    void copyText(text).then(ok => { if (ok) onFeedback(`${draft.label} taslağı kopyalandı.`); });
  }

  function approveDraft() {
    if (!hasBody) return;
    setBusy(true);
    saveDraftReview(lead, draft)
      .then(() => {
        setApproved(current => ({ ...current, [activeChannel]: true }));
        onFeedback(`${draft.label} taslağı onaylandı; henüz gönderilmedi.`);
        void refreshWorkspace();
      })
      .catch(() => onFeedback('Taslak onayı kaydedilemedi.'))
      .finally(() => setBusy(false));
  }

  return (
    <div className={styles.comms}>
      <div className={styles.commsHead}>
        <div>
          <div className={styles.miniLabel}>İLETİŞİM MERKEZİ</div>
          <strong>Metni kontrol et, düzenle ve onayla</strong>
        </div>
        <span className={styles.notSent}>Otomatik gönderilmez</span>
      </div>
      <div className={styles.channelTabs} role="tablist" aria-label="Kanal">
        {sourceDrafts.map(item => (
          <button
            type="button"
            role="tab"
            key={item.channel}
            className={styles.channelTab}
            aria-selected={activeChannel === item.channel}
            onClick={() => setActiveChannel(item.channel)}
          >
            <span className={item.recipient_available ? `${styles.channelDot} ${styles.channelReady}` : styles.channelDot} aria-hidden="true" />
            {item.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" aria-label={`${draft.label} taslağı`}>
        <div className={styles.draftMeta}>
          <span>{draft.recipient_available ? draft.recipient || 'İletişim kanalı hazır' : 'Alıcı/kanal bilgisi eksik'}</span>
          <span>{playbook.discovery_only ? 'Keşif dili' : 'Kanıta dayalı dil'}</span>
        </div>
        {draft.subject !== undefined && (
          <input aria-label="E-posta konusu" className={styles.draftSubject} value={draft.subject || ''} onChange={event => updateDraft('subject', event.target.value)} />
        )}
        <textarea aria-label={`${draft.label} taslağı`} className={styles.draftEditor} value={draft.body || ''} onChange={event => updateDraft('body', event.target.value)} />
        {draft.review_note && <div className={styles.draftReview}><strong>Göndermeden önce:</strong> {draft.review_note}</div>}
        <div className={styles.draftFooter}>
          <span>{(draft.body || '').length} karakter</span>
          <div className={styles.draftButtons}>
            <button type="button" className={styles.button} onClick={copyDraft}>Kopyala</button>
            <button type="button" className={`${styles.saveButton} ${styles.saveSmall}`} onClick={approveDraft} disabled={busy || !hasBody}>
              {approved[activeChannel] ? 'Onaylandı' : busy ? 'Kaydediliyor…' : 'Taslağı onayla'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
