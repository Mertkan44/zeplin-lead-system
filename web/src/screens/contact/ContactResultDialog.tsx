// The contact center: call preparation on the left, the outcome form on the
// right. One submit records the outcome, the note and the follow-up task.
// A failed save keeps everything typed; retrying the same form reuses its
// request id, so a save that did reach the server is not stored twice.
import { useEffect, useRef, useState, type FormEvent } from 'react';

import { OutreachError, saveContactResult } from '../../data/mutations';
import type { Lead, ServiceMatch } from '../../data/types';
import { CONTACT_CHANNEL_OPTIONS, CONTACT_OUTCOME_OPTIONS, FOLLOW_UP_DELAYS } from '../../domain/catalog';
import { followUpForOutcome } from '../../domain/lead';
import { copyText, newRequestId, openExternal } from '../../lib/browser';
import { Button, Dialog, Field, Input, Textarea } from '../../ui';
import styles from './ContactResultDialog.module.css';

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
  const requestIdRef = useRef<string | null>(null);

  const needsFollowUp = Object.prototype.hasOwnProperty.call(FOLLOW_UP_DELAYS, outcome);
  const workflow = lead.workflow || {};
  const ready = Boolean(workflow.ready_to_contact || workflow.latest_contact_at);
  const playbook = lead.sales_playbook || {};
  const brief = playbook.call_brief || {};
  const evidence: Array<Record<string, any>> = (playbook.evidence_points || []).slice(0, 3);
  const services: ServiceMatch[] = (playbook.services || lead.matched_services || lead.discovery_services || []).slice(0, 5);
  const questions: string[] = (playbook.discovery_questions || []).slice(0, 5);
  const objections: Array<{ objection: string; response: string }> = (playbook.objection_responses || []).slice(0, 4);
  const activeDraft = (playbook.channel_drafts || []).find((item: { channel: string }) => item.channel === channel);
  const instagramUrl = lead.manual_verification?.instagram?.url || lead.social?.instagram_url;

  useEffect(() => {
    setFollowUpAt(followUpForOutcome(outcome));
    setFollowUpTouched(false);
  }, [outcome]);

  // A changed form is a new submission; an unchanged retry keeps its id.
  useEffect(() => {
    requestIdRef.current = null;
  }, [channel, outcome, followUpAt, contactName, note, serviceSlugs, checkedQuestions, lead.revision]);

  function openChannel() {
    if (!ready) return;
    const phone = String(lead.phone || '').replace(/\D/g, '');
    const email = lead.email || (lead.research?.website?.emails || [])[0];
    if (channel === 'phone' && phone) window.location.href = `tel:${phone}`;
    else if (channel === 'whatsapp' && phone) openExternal(`https://wa.me/${phone}`);
    else if (channel === 'instagram' && instagramUrl) openExternal(instagramUrl);
    else if (channel === 'email' && email) window.location.href = `mailto:${email}`;
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

  function refreshLead() {
    setBusy(true);
    onRefreshLead().finally(() => setBusy(false));
  }

  function submit(event: FormEvent) {
    event.preventDefault();
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

  return (
    <Dialog eyebrow="TEMAS MERKEZİ" title={lead.name} size="xl" onClose={onClose} dismissible={!busy}>
      <div className={styles.subtitle}>{playbook.context || lead.category || lead.sector || 'İşletme'} · {brief.duration_label || 'Görüşmeye hazırlan'}</div>

      {!ready && (
        <div className={styles.gate}>
          <div>
            <strong>Bu lead henüz temasa hazır değil.</strong>
            <span>{(workflow.missing || []).join(', ') || 'Kaynak kontrolleri'} tamamlanmalı.</span>
          </div>
          <Button variant="primary" size="lg" onClick={() => { onClose(); onOpenLead(); }}>Kontrol ekranına git</Button>
        </div>
      )}

      <form onSubmit={submit} className={styles.grid} noValidate>
        <section className={styles.prep} aria-label="Görüşme hazırlığı">
          <div className={styles.brief}>
            <div className={styles.briefHead}>
              <span>30 SANİYELİK HAZIRLIK</span>
              <strong>{brief.evidence_count || evidence.length} kanıt · {brief.service_count || services.length} hizmet</strong>
            </div>
            <p className={styles.briefText}>{brief.business_summary || playbook.summary || 'İşletmenin hedefini öğren; doğrulanmayan bir açığı kesin bilgi gibi sunma.'}</p>
            <div className={styles.briefGoal}>
              <span>Bu görüşmenin hedefi</span>
              <strong>{brief.conversation_goal || 'İhtiyacı doğrula ve sonraki adımı netleştir.'}</strong>
            </div>
          </div>

          <div className={styles.section}>
            <div className={styles.sectionHead}>
              <div><span className={styles.eyebrow}>KANITLI AÇIKLAR</span><h3 className={styles.sectionTitle}>Neyi konuşacağız?</h3></div>
              <div className={styles.sources}>
                {lead.maps_url && <button type="button" className={styles.mini} onClick={() => openExternal(lead.maps_url)}>Maps ↗</button>}
                {instagramUrl && <button type="button" className={styles.mini} onClick={() => openExternal(instagramUrl)}>Instagram ↗</button>}
                {lead.website?.website_url && <button type="button" className={styles.mini} onClick={() => openExternal(lead.website?.website_url)}>Website ↗</button>}
              </div>
            </div>
            {evidence.length ? (
              <ol className={styles.evidenceList}>
                {evidence.map((item, index) => (
                  <li key={`${item.title}-${index}`} className={styles.evidenceRow}>
                    <span className={styles.evidenceIndex} aria-hidden="true">{index + 1}</span>
                    <div><strong>{item.title}</strong><p>{item.evidence}</p><small>{item.impact || 'Görüşmede işletmeye etkisini doğrula.'}</small></div>
                    {item.source_url && <button type="button" className={styles.mini} onClick={() => openExternal(item.source_url)}>{item.source_label || 'Kaynak'} ↗</button>}
                  </li>
                ))}
              </ol>
            ) : (
              <div className={styles.emptyPrep}>Kesinleşmiş açık yok. Aşağıdaki keşif sorularıyla ihtiyacı öğren.</div>
            )}
          </div>

          <div className={styles.section}>
            <div className={styles.sectionHead}>
              <div><span className={styles.eyebrow}>ÖNERİLEBİLECEK HİZMETLER</span><h3 className={styles.sectionTitle}>Biz ne sunabiliriz?</h3></div>
            </div>
            <div className={styles.services}>
              {services.map(service => (
                <div key={service.slug} className={styles.service}>
                  <strong>{service.name}</strong>
                  <span>{service.why || 'İhtiyaç görüşmede doğrulanmalı.'}</span>
                  <small>{(service.deliverables || []).join(' · ')}</small>
                </div>
              ))}
            </div>
          </div>

          <div className={styles.section}>
            <div className={styles.sectionHead}>
              <div><span className={styles.eyebrow}>ARAMA AKIŞI</span><h3 className={styles.sectionTitle}>Açılış ve keşif</h3></div>
              <button type="button" className={styles.mini} onClick={copyOpener}>{copied ? 'Kopyalandı' : 'Metni kopyala'}</button>
            </div>
            <div className={styles.script}>{playbook.call_opener || 'Önce işletmenin hedefini sor; doğrulanmayan bir açığı kesinmiş gibi söyleme.'}</div>
            {(playbook.call_steps || []).length > 0 && (
              <ol className={styles.steps}>
                {(playbook.call_steps as Array<{ key?: string; label: string; instruction: string }>).map((step, index) => (
                  <li key={step.key || index} className={styles.step}>
                    <span aria-hidden="true">{index + 1}</span>
                    <div><strong>{step.label}</strong><small>{step.instruction}</small></div>
                  </li>
                ))}
              </ol>
            )}
            {questions.length > 0 && (
              <fieldset className={styles.fieldset}>
                <legend className={`${styles.label} ${styles.legend}`}>Görüşmede sor</legend>
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
                {objections.map(item => (
                  <details key={item.objection} className={styles.objection}>
                    <summary>{item.objection}</summary>
                    <p>{item.response}</p>
                  </details>
                ))}
              </div>
            )}
          </div>
        </section>

        <aside className={styles.resultColumn} aria-label="Görüşme sonucu">
          <div className={styles.resultCard}>
            <div className={styles.resultHead}><span className={styles.eyebrow}>GÖRÜŞME SONUCU</span><strong>Tek seferde kaydet</strong></div>
            {(workflow.checks || []).length > 0 && (
              <ul className={styles.checks}>
                {(workflow.checks || []).map(item => (
                  <li key={item.key} className={item.complete ? `${styles.check} ${styles.checkDone}` : styles.check}>
                    <strong>{item.complete ? '✓' : '○'} {item.label}</strong>
                  </li>
                ))}
              </ul>
            )}

            <fieldset className={styles.fieldset} disabled={!ready || busy}>
              <fieldset className={styles.fieldset}>
                <legend className={`${styles.label} ${styles.legend}`}>Kanal</legend>
                <div className={styles.options}>
                  {CONTACT_CHANNEL_OPTIONS.map(([key, label]) => (
                    <button type="button" key={key} className={styles.option} aria-pressed={channel === key} onClick={() => setChannel(key)}>{label}</button>
                  ))}
                </div>
                <Button variant="primary" size="lg" className={styles.openChannel} onClick={openChannel}>Kanalı aç ↗</Button>
              </fieldset>
              {activeDraft?.body && <div className={styles.draft}><strong>{activeDraft.label} metni</strong><span>{activeDraft.body}</span></div>}

              <fieldset className={styles.fieldset}>
                <legend className={`${styles.label} ${styles.legend}`}>Görüşmenin sonucu</legend>
                <div className={styles.options}>
                  {CONTACT_OUTCOME_OPTIONS.map(([key, label]) => (
                    <button type="button" key={key} className={styles.option} aria-pressed={outcome === key} onClick={() => setOutcome(key)}>{label}</button>
                  ))}
                </div>
              </fieldset>

              <div className={styles.fields}>
                {needsFollowUp && (
                  <Field
                    id="follow-up-at"
                    label="Otomatik takip görevi"
                    hint={`${followUpTouched ? 'Seçtiğin tarih' : `Varsayılan: ${FOLLOW_UP_DELAYS[outcome]} gün sonra 10:00 (İstanbul)`} · kaydedince Bugünkü İşler listesine eklenir.`}
                  >
                    {control => (
                      <Input {...control} type="datetime-local" required value={followUpAt} onChange={event => { setFollowUpAt(event.target.value); setFollowUpTouched(true); }} />
                    )}
                  </Field>
                )}

                {services.length > 0 && (
                  <fieldset className={styles.fieldset}>
                    <legend className={`${styles.label} ${styles.legend}`}>Konuşulan / ilgi duyulan hizmetler</legend>
                    <div className={styles.serviceOptions}>
                      {services.map(service => (
                        <label key={service.slug} className={styles.serviceOption}>
                          <input type="checkbox" checked={serviceSlugs.includes(service.slug)} onChange={() => setServiceSlugs(current => toggle(current, service.slug))} />
                          <span>{service.name}</span>
                        </label>
                      ))}
                    </div>
                  </fieldset>
                )}

                <Field id="contact-name" label="Görüşülen kişi">
                  {control => <Input {...control} value={contactName} onChange={event => setContactName(event.target.value)} placeholder="Örn. Ayşe Hanım" />}
                </Field>
                <Field id="contact-note" label="Görüşme notu">
                  {control => <Textarea {...control} value={note} onChange={event => setNote(event.target.value)} placeholder="Ne konuşuldu, ne istendi, karar verici kim?" />}
                </Field>
              </div>
            </fieldset>

            {error && (
              <div role="alert" className={styles.error}>
                <span>{error}</span>
                {errorCode === 'LEAD_VERSION_CONFLICT' && <Button disabled={busy} onClick={refreshLead}>Güncel veriyi al</Button>}
              </div>
            )}
            <div className={styles.footer}>
              <Button onClick={onClose} disabled={busy}>Vazgeç</Button>
              <Button type="submit" variant="primary" size="lg" busy={busy} busyLabel="Kaydediliyor…" disabled={!ready}>Sonucu ve görevi kaydet</Button>
            </div>
          </div>
        </aside>
      </form>
    </Dialog>
  );
}
