// Aktivite tab: a quick note, then the timeline grouped by day. Activity by
// people is shown by default; system events (sources opened, drafts copied)
// on request. An unsaved note stays with its lead (lib/drafts.ts).
import { useRef, useState } from 'react';

import { addOutreach, refreshWorkspace } from '../../data/mutations';
import type { Lead, OutreachEvent } from '../../data/types';
import { actionMeta } from '../../domain/catalog';
import { fmtDate } from '../../domain/format';
import { newRequestId } from '../../lib/browser';
import { useDraft } from '../../lib/drafts';
import { Button, Field, Textarea } from '../../ui';
import styles from './LeadPage.module.css';

/** Recorded by the app on the way, not a person's result or note. */
const SYSTEM_ACTIONS = new Set(['data_enrichment_started', 'email_drafted', 'outreach_review_started', 'call_started', 'proposal_created']);

const dayKey = (date: Date) => date.toISOString().slice(0, 10);

function dayTitle(date: Date): string {
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  if (dayKey(date) === dayKey(today)) return 'Bugün';
  if (dayKey(date) === dayKey(yesterday)) return 'Dün';
  return date.toLocaleDateString('tr-TR', { day: 'numeric', month: 'long', year: 'numeric' });
}

export function LeadActivityTab({ lead, events }: { lead: Lead; events: OutreachEvent[] }) {
  const [note, setNote] = useDraft(`note:${lead.lead_id ?? lead.name}`);
  const noteRequestRef = useRef<{ text: string; id: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState('');
  const [showSystem, setShowSystem] = useState(false);

  const visible = events.filter(event => showSystem || !SYSTEM_ACTIONS.has(event.action));
  const days = new Map<string, { title: string; items: OutreachEvent[] }>();
  visible.forEach(event => {
    const date = new Date(event.date);
    const key = Number.isNaN(date.getTime()) ? 'unknown' : dayKey(date);
    if (!days.has(key)) days.set(key, { title: Number.isNaN(date.getTime()) ? 'Tarihsiz' : dayTitle(date), items: [] });
    days.get(key)!.items.push(event);
  });

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

  return (
    <div className={styles.stack}>
      <section className={styles.card}>
        <div className={styles.composer}>
          <Field label="Not">
            {control => <Textarea {...control} value={note} onChange={event => setNote(event.target.value)} placeholder="Lead hakkında kısa not…" />}
          </Field>
          <div className={styles.composerFoot}>
            <span role="status">{feedback || 'Not zaman çizelgesine eklenir.'}</span>
            <Button variant="primary" onClick={saveNote} busy={busy} busyLabel="Kaydediliyor…" disabled={!note.trim()}>Notu kaydet</Button>
          </div>
        </div>
      </section>

      <section className={styles.card} aria-labelledby="timeline-title">
        <div className={styles.timelineHead}>
          <h2 id="timeline-title" className={styles.cardTitle}>Zaman çizelgesi</h2>
          <label className={styles.toggle}>
            <input type="checkbox" checked={showSystem} onChange={event => setShowSystem(event.target.checked)} />
            Sistem olaylarını göster
          </label>
        </div>
        {days.size === 0 && <p className={styles.empty}>Henüz kayıtlı hareket yok.</p>}
        {[...days.entries()].map(([key, day]) => (
          <div key={key} className={styles.day}>
            <h3 className={styles.dayTitle}>{day.title}</h3>
            <ol className={styles.events}>
              {day.items.map((event, index) => {
                const date = new Date(event.date);
                return (
                  <li key={`${event.ts}-${index}`} className={SYSTEM_ACTIONS.has(event.action) ? styles.event : `${styles.event} ${styles.eventPerson}`}>
                    <div className={styles.eventTitle}>
                      <span>{event.outcomeLabel || actionMeta(event.action).label}</span>
                      {!Number.isNaN(date.getTime()) && <time dateTime={event.date}>{date.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' })}</time>}
                    </div>
                    <div className={styles.eventMeta}>
                      {[
                        event.channelLabel,
                        event.contactName,
                        event.note,
                        event.followUpAt ? `Takip: ${fmtDate(event.followUpAt)}` : '',
                      ].filter(Boolean).join(' · ')}
                    </div>
                  </li>
                );
              })}
            </ol>
          </div>
        ))}
        {lead.last_analyzed && <p className={styles.empty}>Tarama: {fmtDate(lead.last_analyzed)}</p>}
      </section>
    </div>
  );
}
