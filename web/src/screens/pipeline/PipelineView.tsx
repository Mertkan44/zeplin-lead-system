// The sales pipeline as columns. Cards move by drag and drop or, without a
// mouse, with the "Aşama" select on each card; a failed move says so.
import { useRef, useState, type DragEvent } from 'react';

import { startLeadAction, triggerQuickLeadAction } from '../../data/leadActions';
import { addOutreach, refreshWorkspace, setLeadStatus } from '../../data/mutations';
import type { Lead } from '../../data/types';
import { useCrm } from '../../data/workspace';
import { PIPE_STAGES, type PipelineStageKey } from '../../domain/catalog';
import { fmt } from '../../domain/format';
import { getPipelineStage, getPrimaryActionMeta } from '../../domain/lead';
import { routeFor } from '../../lib/router';
import { Banner, Link } from '../../ui';
import { PageHeader } from '../shared/PageHeader';
import styles from './PipelineView.module.css';

/** Records what moving a lead to `stage` means: an activity or a status. */
function moveToStage(leadName: string, stage: PipelineStageKey): Promise<void> {
  const now = new Date().toISOString().slice(0, 16);
  const action = PIPE_STAGES.find(item => item.key === stage)?.actions[0];
  if (action) return addOutreach(leadName, action, now, '');
  if (stage === 'new') return setLeadStatus(leadName, 'yeni');
  if (stage === 'contacted') return setLeadStatus(leadName, 'contacted');
  return Promise.resolve();
}

export function PipelineView({ leads }: { leads: Lead[] }) {
  const crm = useCrm();
  const [busyLead, setBusyLead] = useState('');
  const [error, setError] = useState('');
  const [dragging, setDragging] = useState('');
  const [dropTarget, setDropTarget] = useState<PipelineStageKey | null>(null);
  const dragRef = useRef('');

  const byStage = new Map<PipelineStageKey, Lead[]>(PIPE_STAGES.map(stage => [stage.key, []]));
  const stageOf = (lead: Lead) => getPipelineStage(crm.statuses[lead.name] || 'yeni', crm.eventsFor(lead.name));
  leads.forEach(lead => byStage.get(stageOf(lead))?.push(lead));
  const won = byStage.get('won')!.length;
  const active = (['draft', 'contacted', 'meeting'] as PipelineStageKey[]).reduce((sum, key) => sum + byStage.get(key)!.length, 0);

  function move(leadName: string, stage: PipelineStageKey) {
    setError('');
    moveToStage(leadName, stage)
      .then(() => refreshWorkspace())
      .catch(() => setError(`${leadName} taşınamadı; aşaması değişmedi. Bağlantını kontrol edip tekrar dene.`));
  }

  function runPrimary(lead: Lead) {
    setBusyLead(lead.name);
    setError('');
    startLeadAction(lead)
      .catch((err: Error) => setError(err.message || 'Aksiyon tamamlanamadı.'))
      .finally(() => {
        setBusyLead('');
        void refreshWorkspace();
      });
  }

  function onDrop(event: DragEvent, stage: PipelineStageKey) {
    event.preventDefault();
    setDropTarget(null);
    const name = dragRef.current;
    dragRef.current = '';
    if (name) move(name, stage);
  }

  return (
    <div className={styles.root}>
      <PageHeader eyebrow="PIPELINE" title="Satış kanalı" subtitle={`${leads.length} lead · ${won} kazanıldı · ${active} aktif temasta`} />
      {error && <div className={styles.error}><Banner tone="danger" urgent actionLabel="Kapat" onAction={() => setError('')}>{error}</Banner></div>}
      <div className={styles.board}>
        {PIPE_STAGES.map(stage => {
          const cards = byStage.get(stage.key)!;
          return (
            <section
              key={stage.key}
              aria-labelledby={`stage-${stage.key}`}
              className={dropTarget === stage.key ? `${styles.column} ${styles.dragOver}` : styles.column}
              onDragOver={event => { event.preventDefault(); setDropTarget(stage.key); }}
              onDragLeave={() => setDropTarget(current => (current === stage.key ? null : current))}
              onDrop={event => onDrop(event, stage.key)}
            >
              <div className={styles.columnHead}>
                <span className={styles.dot} style={{ background: stage.color }} aria-hidden="true" />
                <h2 id={`stage-${stage.key}`} className={styles.columnTitle}>{stage.label}</h2>
                <span className={styles.count}>{cards.length}</span>
              </div>
              {cards.length ? (
                <ul className={styles.cards}>
                  {cards.map(lead => {
                    const primary = getPrimaryActionMeta(lead);
                    const value = lead.estimated_value_tl || 0;
                    return (
                      <li
                        key={lead.name}
                        className={dragging === lead.name ? `${styles.card} ${styles.dragging}` : styles.card}
                        draggable
                        onDragStart={() => { dragRef.current = lead.name; setDragging(lead.name); }}
                        onDragEnd={() => setDragging('')}
                      >
                        {lead.lead_id != null
                          ? <Link to={routeFor({ leadId: lead.lead_id })} className={styles.cardName}>{lead.name}</Link>
                          : <span className={styles.cardName}>{lead.name}</span>}
                        <div className={styles.actionLabel}>{primary.label}</div>
                        <div className={styles.meta}>
                          <span className={styles.score} style={{ ['--stage' as string]: stage.color }}>{lead.scoring.grade} {lead.scoring.score}</span>
                          {value > 0 && <span className={styles.value}>~{fmt(value)} ₺</span>}
                        </div>
                        <div className={styles.actions}>
                          <button type="button" className={styles.primary} disabled={busyLead === lead.name} onClick={() => runPrimary(lead)}>
                            {busyLead === lead.name ? 'Kaydediliyor…' : primary.label}
                          </button>
                          <button type="button" className={styles.ghost} onClick={() => triggerQuickLeadAction(lead)}>Hızlı aç</button>
                        </div>
                        <select
                          className={styles.move}
                          aria-label={`${lead.name} aşaması`}
                          value={stage.key}
                          onChange={event => move(lead.name, event.target.value as PipelineStageKey)}
                        >
                          {PIPE_STAGES.map(option => <option key={option.key} value={option.key}>Aşama: {option.label}</option>)}
                        </select>
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <div className={styles.empty}>Buraya sürükle</div>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}
