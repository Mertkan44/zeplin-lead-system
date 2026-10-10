import { useRef, useState, type FormEvent } from 'react';
import { OpportunityError, saveOpportunity, type Opportunity, type OpportunityStage } from '../../data/opportunities';
import type { Lead } from '../../data/types';
import { SERVICES } from '../../domain/catalog';
import { OPPORTUNITY_STAGES, stageRank } from '../../domain/opportunities';
import { newRequestId } from '../../lib/browser';
import { Button, ConfirmDialog, Dialog, Field, Input, Select, Textarea } from '../../ui';
import styles from './PipelineView.module.css';

interface Snapshot { lead: Lead; opportunity?: Opportunity }
interface Props {
  lead?: Lead;
  opportunity?: Opportunity;
  candidates: Lead[];
  stage: OpportunityStage;
  onClose: () => void;
  onSaved: () => void;
  onRefresh: (leadId: number) => Promise<Snapshot | undefined>;
}

export function OpportunityDialog({ lead, opportunity, candidates, stage: initialStage, onClose, onSaved, onRefresh }: Props) {
  const [snapshot, setSnapshot] = useState<Snapshot | undefined>(() => lead ? { lead, opportunity } : undefined);
  const [stage, setStage] = useState(initialStage);
  const initialNote = initialStage === 'lost' && opportunity?.stage === 'lost' ? opportunity.lost_reason || '' : '';
  const [note, setNote] = useState(initialNote);
  const [amount, setAmount] = useState(opportunity?.amount != null ? String(opportunity.amount) : '');
  const [unknown, setUnknown] = useState(opportunity?.amount == null && initialStage !== 'won');
  const [service, setService] = useState(opportunity?.service_slug || '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [conflict, setConflict] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);
  const request = useRef<{ body: string; id: string } | null>(null);
  const oldStage = snapshot?.opportunity?.stage;
  const reasonRequired = stage === 'lost' || (oldStage && stageRank(stage) < stageRank(oldStage));
  const closing = stage === 'won' || stage === 'lost';
  const dirty = Boolean(note !== initialNote || amount !== (opportunity?.amount != null ? String(opportunity.amount) : '') || service !== (opportunity?.service_slug || '') || unknown !== (opportunity?.amount == null && initialStage !== 'won') || stage !== (opportunity?.stage || 'new') || (!lead && snapshot));

  function close() {
    if (busy) return;
    if (dirty) setConfirmClose(true);
    else onClose();
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    const selected = snapshot?.lead;
    if (!selected?.lead_id) { setError('İşletme seç.'); return; }
    if (reasonRequired && !note.trim()) { setError('Bu geçişin nedenini yaz.'); return; }
    if (!unknown && (!amount || !Number.isFinite(Number(amount)) || Number(amount) <= 0)) { setError('Tutarı veya “henüz bilinmiyor” seçeneğini belirt.'); return; }
    const fields = {
      lead_id: selected.lead_id,
      expected_lead_revision: snapshot?.opportunity?.lead_revision ?? selected.revision ?? 0,
      expected_opportunity_revision: snapshot?.opportunity?.revision ?? 0,
      stage, note, amount: unknown ? null : amount, amount_unknown: unknown, service_slug: service || null,
    };
    const body = JSON.stringify(fields);
    if (request.current?.body !== body) request.current = { body, id: newRequestId() };
    setBusy(true); setError(''); setConflict(false);
    try {
      await saveOpportunity({ ...fields, idempotency_key: request.current!.id });
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Fırsat kaydedilemedi.');
      setConflict(err instanceof OpportunityError && ['OPPORTUNITY_VERSION_CONFLICT', 'LEAD_VERSION_CONFLICT'].includes(err.code || ''));
    } finally { setBusy(false); }
  }

  async function refresh() {
    if (!snapshot?.lead.lead_id || busy) return;
    setBusy(true);
    try {
      const next = await onRefresh(snapshot.lead.lead_id);
      if (!next) { setError('İşletme artık görünür değil; atamanı kontrol et.'); return; }
      setSnapshot(next); request.current = null; setConflict(false);
      setError('Güncel bilgiler alındı. Seçtiğin aşamayı ve alanları kontrol edip tekrar kaydet.');
    } catch { setError('Güncel bilgiler alınamadı; formun korunuyor.'); }
    finally { setBusy(false); }
  }

  return <Dialog eyebrow="SATIŞ FIRSATI" title={snapshot?.lead.name || 'Fırsat oluştur'} onClose={close} dismissible={!busy} placement="right">
    <form className={styles.form} onSubmit={submit} noValidate>
      <fieldset className={styles.fields} disabled={busy}>
        {!lead && <Field label="İşletme">{control => <Select {...control} value={snapshot?.lead.lead_id || ''} onChange={event => { const row = candidates.find(item => item.lead_id === Number(event.target.value)); setSnapshot(row ? { lead: row } : undefined); }}>
          <option value="">İşletme seç</option>{candidates.map(item => <option key={item.lead_id} value={item.lead_id!}>{item.name}</option>)}
        </Select>}</Field>}
        <Field label="Satış aşaması" hint="Aşama değişikliği görüşme veya gönderilmiş mesaj kaydı oluşturmaz.">{control => <Select {...control} value={stage} onChange={event => { const next = event.target.value as OpportunityStage; setStage(next); if (next === 'won' && !amount) setUnknown(false); }}>
          {OPPORTUNITY_STAGES.map(item => <option key={item.key} value={item.key}>{item.label}</option>)}
        </Select>}</Field>
        <Field label="Ana hizmet">{control => <Select {...control} value={service} onChange={event => setService(event.target.value)}>
          <option value="">Henüz seçilmedi</option>{SERVICES.map(item => <option key={item.slug} value={item.slug}>{item.name}</option>)}
        </Select>}</Field>
        <Field label="Fırsat tutarı (TL)" hint="Gerçek teklif/anlaşma tutarı. Araştırma tahmini bu alana eklenmez.">{control => <Input {...control} type="number" min="0.01" max="1000000000" step="0.01" inputMode="decimal" value={amount} disabled={unknown} onChange={event => setAmount(event.target.value)} />}</Field>
        <label className={styles.check}><input type="checkbox" checked={unknown} onChange={event => setUnknown(event.target.checked)} /> Tutar henüz bilinmiyor</label>
        <Field label={stage === 'lost' ? 'Kaybetme nedeni' : reasonRequired ? 'Geri dönme / yeniden açma nedeni' : 'Geçiş notu (isteğe bağlı)'}>{control => <Textarea {...control} maxLength={2000} required={Boolean(reasonRequired)} value={note} onChange={event => setNote(event.target.value)} />}</Field>
      </fieldset>
      {closing && <p className={styles.notice}>Kaydedince açık takip kapanır ve atama tamamlanır.{stage === 'won' && unknown ? ' Kazanım tutarı eksik olarak gösterilir.' : ''}</p>}
      {oldStage && ['won', 'lost'].includes(oldStage) && stage === 'new' && <p className={styles.notice}>Yeniden açmak için yönetici ve neden gerekir. Sonraki takip ve atama ayrıca planlanır.</p>}
      {error && <div role="alert" className={styles.formError}>{error}{conflict && <Button disabled={busy} onClick={() => void refresh()}>Güncel bilgileri al</Button>}</div>}
      <div className={styles.formActions}><Button disabled={busy} onClick={close}>Vazgeç</Button><Button type="submit" variant="primary" busy={busy} busyLabel="Kaydediliyor…">{opportunity ? 'Fırsatı kaydet' : 'Fırsatı oluştur'}</Button></div>
    </form>
    {confirmClose && <ConfirmDialog title="Değişiklik kaydedilmedi" text="Alanları kapatırsan değişiklikler silinecek." confirmLabel="Kaydetmeden kapat" cancelLabel="Forma dön" destructive onCancel={() => setConfirmClose(false)} onConfirm={onClose} />}
  </Dialog>;
}
