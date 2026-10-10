// Recording a contact (review §12.7): a drawer on desktop, full screen on
// phones. Preparation is collapsible at the top; the form asks, in order,
// channel → outcome (never preselected) → follow-up when the outcome needs
// one → a short note, with the person and services as optional details.
// Each outcome says what saving it will do. Closing a form with unsaved
// input asks first. A failed save keeps everything; retrying the same form
// reuses its request id, so a save that reached the server is not stored twice.
import { useEffect, useRef, useState, type FormEvent } from 'react';

import { OutreachError, saveContactResult } from '../../data/mutations';
import type { Lead, ServiceMatch } from '../../data/types';
import { CONTACT_CHANNEL_OPTIONS, CONTACT_OUTCOME_OPTIONS, FOLLOW_UP_DELAYS } from '../../domain/catalog';
import { daysFromNowAtTen } from '../../domain/format';
import { followUpForOutcome } from '../../domain/lead';
import { telLink, whatsappLink } from '../../domain/phone';
import { copyText, newRequestId, openExternal } from '../../lib/browser';
import { Button, ConfirmDialog, Dialog, Field, Input, Textarea } from '../../ui';
import styles from './ContactResultDialog.module.css';

/** What saving each outcome does on the server (src/activity.py). */
const OUTCOME_EFFECTS: Record<string, string> = {
  reached_interested: 'Lead “Temasta” olur; 2 gün sonra 10:00 için takip görevi açılır.',
  proposal_requested: 'Lead “Temasta” olur; teklif hazırlığı için yarın 10:00 takip görevi açılır.',
  reached_later: 'Lead “Takipte” olur; seçtiğin tarihte takip görevi açılır.',
  no_answer: 'Lead “Takipte” kalır; yarın 10:00 için tekrar arama görevi açılır.',
  wrong_number: 'Lead “Veri eksik” olur ve doğrulama listesine düşer; takip görevi açılmaz.',
  not_interested: 'Lead kapanır (Kaybedildi) ve atama tamamlanır. Nedenini nota yaz.',
  won: 'Lead “Müşteri” olur ve atama tamamlanır.',
  lost: 'Lead kapanır (Kaybedildi) ve atama tamamlanır. Nedenini nota yaz.',
};

const QUICK_DATES: Array<[string, number]> = [['Yarın 10:00', 1], ['2 gün sonra', 2], ['Haftaya', 7]];

export interface ContactResultDialogProps {
  lead: Lead;
  onClose: () => void;
  onSaved: () => void;
  /** Opens the lead's detail screen (to finish its checks). */
  onOpenLead: () => void;
  /** Refetches the lead after a version conflict. */
  onRefreshLead: () => Promise<unknown>;
}

function initialChannel(lead: Lead): string {
  if (lead.phone) return 'phone';
  if (lead.social?.instagram_url) return 'instagram';
  return 'other';
}

export function ContactResultDialog({ lead, onClose, onSaved, onOpenLead, onRefreshLead }: ContactResultDialogProps) {
  const [channel, setChannel] = useState(() => initialChannel(lead));
  // No preselected outcome: an accidental submit must not record interest.
  const [outcome, setOutcome] = useState('');
  const [followUpAt, setFollowUpAt] = useState('');
  const [followUpTouched, setFollowUpTouched] = useState(false);
  const [contactName, setContactName] = useState('');
  const [note, setNote] = useState('');
  const [serviceSlugs, setServiceSlugs] = useState<string[]>([]);
  const [checkedQuestions, setCheckedQuestions] = useState<number[]>([]);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [errorCode, setErrorCode] = useState('');
  const [confirmClose, setConfirmClose] = useState(false);
  const requestIdRef = useRef<string | null>(null);

  const needsFollowUp = Object.prototype.hasOwnProperty.call(FOLLOW_UP_DELAYS, outcome);
  const workflow = lead.workflow || {};
  const ready = Boolean(workflow.ready_to_contact || workflow.latest_contact_at);
  const playbook = lead.sales_playbook || {};
  const brief = playbook.call_brief || {};
  const evidence: Array<{ title: string; evidence?: string }> = (playbook.evidence_points || []).slice(0, 3);
  const services: ServiceMatch[] = (playbook.services || lead.matched_services || lead.discovery_services || []).slice(0, 5);
  const questions: string[] = (playbook.discovery_questions || []).slice(0, 5);
  const objections: Array<{ objection: string; response: string }> = (playbook.objection_responses || []).slice(0, 4);
  const activeDraft = (playbook.channel_drafts || []).find((item: { channel: string }) => item.channel === channel);
  const instagramUrl = lead.manual_verification?.instagram?.url || lead.social?.instagram_url;
  const email = lead.email || (lead.research?.website?.emails || [])[0];
  const channelUrl: Record<string, string | null> = {
    phone: lead.phone ? telLink(lead.phone) : null,
    whatsapp: whatsappLink(lead.phone),
    instagram: instagramUrl || null,
    email: email ? `mailto:${email}` : null,
    other: null,
  };
  const dirty = Boolean(outcome || note.trim() || contactName.trim() || serviceSlugs.length || checkedQuestions.length || followUpTouched);

  useEffect(() => {
    setFollowUpAt(followUpForOutcome(outcome));
    setFollowUpTouched(false);
  }, [outcome]);

  // A changed form is a new submission; an unchanged retry keeps its id.
  useEffect(() => {
    requestIdRef.current = null;
  }, [channel, outcome, followUpAt, contactName, note, serviceSlugs, checkedQuestions, lead.revision]);

  function requestClose() {
    if (busy) return;
    if (dirty) setConfirmClose(true);
    else onClose();
  }

  function openChannel() {
    const url = channelUrl[channel];
    if (!url) return;
    if (url.startsWith('http')) openExternal(url);
    else window.location.href = url;
  }

  function toggle<T>(list: T[], item: T): T[] {
    return list.includes(item) ? list.filter(value => value !== item) : [...list, item];
  }

  function copyOpener() {
    if (!playbook.call_opener) return;
    void copyText(playbook.call_opener).then(ok => {
      if (!ok) return;
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    });
  }

  function pickDate(days: number) {
    setFollowUpAt(daysFromNowAtTen(days));
    setFollowUpTouched(true);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    if (!outcome) {
      setError('Görüşmenin sonucunu seç.');
      return;
    }
    if (needsFollowUp && !followUpAt) {
      setError('Takip tarihi seçmelisin.');
      return;
    }
    if (!requestIdRef.current) requestIdRef.current = newRequestId();
    setBusy(true);
    setError('');
    setErrorCode('');
    const discoveryNote = checkedQuestions.length
      ? `Sorulan keşif başlıkları: ${checkedQuestions.map(index => questions[index]).filter(Boolean).join(' | ')}`
      : '';
    saveContactResult(lead, {
      channel,
      outcome,
      followUpAt: needsFollowUp && followUpTouched ? new Date(followUpAt).toISOString() : null,
      contactName,
      note: [note, discoveryNote].filter(Boolean).join('\n'),
      serviceSlugs,
    }, requestIdRef.current)
      .then(() => onSaved())
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : 'Sonuç kaydedilemedi.');
        setErrorCode(err instanceof OutreachError ? err.code : '');
      })
      .finally(() => setBusy(false));
  }

  const context = [playbook.context || lead.category || lead.sector, lead.city, lead.phone].filter(Boolean).join(' · ');
  const quickDays = QUICK_DATES.find(([, days]) => followUpTouched && followUpAt === daysFromNowAtTen(days))?.[1];

  return (
    <Dialog eyebrow="GÖRÜŞME SONUCU" title={lead.name} size="lg" placement="right" onClose={requestClose} dismissible={!busy}>
      <div className={styles.context}>{context}</div>

      {!ready && (
        <div className={styles.gate}>
          <div>
            <strong>Bu lead henüz temasa hazır değil.</strong>
            <span>{(workflow.missing || []).join(', ') || 'Kaynak kontrolleri'} tamamlanmalı.</span>
          </div>
          <Button variant="primary" onClick={() => { onClose(); onOpenLead(); }}>Kontrol ekranına git</Button>
        </div>
      )}

      <details className={styles.prep} open={!workflow.latest_contact_at}>
        <summary>Görüşmeye hazırlan <span>{evidence.length} kanıt · {services.length} hizmet</span></summary>
        <div className={styles.prepBody}>
          {(brief.business_summary || playbook.summary) && <p className={styles.brief}>{brief.business_summary || playbook.summary}</p>}
          {brief.conversation_goal && <p className={styles.goal}><strong>Hedef:</strong> {brief.conversation_goal}</p>}
          <div>
            <span className={styles.label}>Açılış</span>
            <div className={styles.opener}>
              <span>{playbook.call_opener || 'Önce işletmenin hedefini sor; doğrulanmayan bir açığı kesinmiş gibi söyleme.'}</span>
              {playbook.call_opener && <button type="button" className={styles.mini} onClick={copyOpener}>{copied ? 'Kopyalandı' : 'Kopyala'}</button>}
            </div>
          </div>
          {evidence.length > 0 && (
            <div>
              <span className={styles.label}>Konuşulacak kanıtlar</span>
              <ol className={styles.evidence}>
                {evidence.map((item, index) => <li key={`${item.title}-${index}`}><strong>{item.title}</strong>{item.evidence ? ` — ${item.evidence}` : ''}</li>)}
              </ol>
            </div>
          )}
          {questions.length > 0 && (
            <fieldset className={styles.fieldset}>
              <legend className={styles.label}>Sorduklarını işaretle (nota eklenir)</legend>
              <div className={styles.questions}>
                {questions.map((question, index) => (
                  <label key={question} className={styles.question}>
                    <input type="checkbox" checked={checkedQuestions.includes(index)} onChange={() => setCheckedQuestions(current => toggle(current, index))} />
                    <span>{question}</span>
                  </label>
                ))}
              </div>
            </fieldset>
          )}
          {objections.length > 0 && (
            <div className={styles.objections}>
              <span className={styles.label}>İtiraz gelirse</span>
              {objections.map(item => (
                <details key={item.objection} className={styles.objection}>
                  <summary>{item.objection}</summary>
                  <p>{item.response}</p>
                </details>
              ))}
            </div>
          )}
        </div>
      </details>

      <form onSubmit={submit} className={styles.form} noValidate>
        <fieldset className={styles.fieldset} disabled={!ready || busy}>
          <legend className={styles.legend}><span className={styles.step}>1</span>Kanal</legend>
          <div className={styles.channels} role="group" aria-label="Kanal">
            {CONTACT_CHANNEL_OPTIONS.map(([key, label]) => (
              <button type="button" key={key} className={`${styles.option} ${styles.channelOption}`} aria-pressed={channel === key} onClick={() => setChannel(key)}>{label}</button>
            ))}
            {channelUrl[channel] && <Button onClick={openChannel}>Kanalı aç ↗</Button>}
          </div>
          {activeDraft?.body && (
            <details className={styles.draft}>
              <summary>{activeDraft.label} metnini göster</summary>
              <p>{activeDraft.body}</p>
            </details>
          )}
        </fieldset>

        <fieldset className={styles.fieldset} disabled={!ready || busy}>
          <legend className={styles.legend}><span className={styles.step}>2</span>Sonuç</legend>
          <div className={styles.options} role="group" aria-label="Görüşmenin sonucu">
            {CONTACT_OUTCOME_OPTIONS.map(([key, label]) => (
              <button type="button" key={key} className={styles.option} aria-pressed={outcome === key} onClick={() => setOutcome(key)}>{label}</button>
            ))}
          </div>
          <div aria-live="polite">{outcome && <p className={styles.effect}>{OUTCOME_EFFECTS[outcome]}</p>}</div>
        </fieldset>

        {needsFollowUp && (
          <fieldset className={styles.fieldset} disabled={!ready || busy}>
            <legend className={styles.legend}><span className={styles.step}>3</span>Takip</legend>
            <div className={styles.quick} role="group" aria-label="Hızlı tarih">
              {QUICK_DATES.map(([label, days]) => (
                <Button key={days} size="sm" aria-pressed={quickDays === days} onClick={() => pickDate(days)}>{label}</Button>
              ))}
            </div>
            <Field
              id="follow-up-at"
              label="Takip zamanı"
              hint={followUpTouched ? 'Seçtiğin zaman · kaydedince Bugün ekranına eklenir.' : `Varsayılan: ${FOLLOW_UP_DELAYS[outcome]} gün sonra 10:00 · kaydedince Bugün ekranına eklenir.`}
            >
              {control => <Input {...control} type="datetime-local" required value={followUpAt} onChange={event => { setFollowUpAt(event.target.value); setFollowUpTouched(true); }} />}
            </Field>
          </fieldset>
        )}

        <fieldset className={styles.fieldset} disabled={!ready || busy}>
          <legend className={styles.legend}><span className={styles.step}>{needsFollowUp ? 4 : 3}</span>Not</legend>
          <Field id="contact-note" label="Görüşme notu">
            {control => <Textarea {...control} value={note} onChange={event => setNote(event.target.value)} placeholder="Ne konuşuldu, ne istendi, karar verici kim?" />}
          </Field>
        </fieldset>

        <details className={styles.more}>
          <summary>Daha fazla ayrıntı (isteğe bağlı)</summary>
          <fieldset className={`${styles.fieldset} ${styles.moreBody}`} disabled={!ready || busy}>
            <Field id="contact-name" label="Görüşülen kişi">
              {control => <Input {...control} value={contactName} onChange={event => setContactName(event.target.value)} placeholder="Örn. Ayşe Hanım" />}
            </Field>
            {services.length > 0 && (
              <div>
                <span className={styles.label}>Konuşulan / ilgi duyulan hizmetler</span>
                <div className={styles.services}>
                  {services.map(service => (
                    <label key={service.slug} className={styles.service}>
                      <input type="checkbox" checked={serviceSlugs.includes(service.slug)} onChange={() => setServiceSlugs(current => toggle(current, service.slug))} />
                      <span>{service.name}</span>
                    </label>
                  ))}
                </div>
              </div>
            )}
          </fieldset>
        </details>

        {error && (
          <div role="alert" className={styles.error}>
            <span>{error}</span>
            {errorCode === 'LEAD_VERSION_CONFLICT' && <Button disabled={busy} onClick={() => { setBusy(true); onRefreshLead().finally(() => setBusy(false)); }}>Güncel veriyi al</Button>}
          </div>
        )}

        <div className={styles.footer}>
          <span className={styles.footerHint}>{outcome ? 'Tek kayıtta sonuç, not ve takip.' : 'Önce sonucu seç.'}</span>
          <div className={styles.footerButtons}>
            <Button onClick={requestClose} disabled={busy}>Vazgeç</Button>
            <Button type="submit" variant="primary" busy={busy} busyLabel="Kaydediliyor…" disabled={!ready}>Sonucu kaydet</Button>
          </div>
        </div>
      </form>

      {confirmClose && (
        <ConfirmDialog
          title="Sonuç kaydedilmedi"
          text="Seçtiğin sonuç ve yazdığın not kaydedilmedi. Kapatırsan silinecek."
          confirmLabel="Kaydetmeden kapat"
          cancelLabel="Forma dön"
          destructive
          onCancel={() => setConfirmClose(false)}
          onConfirm={() => { setConfirmClose(false); onClose(); }}
        />
      )}
    </Dialog>
  );
}
