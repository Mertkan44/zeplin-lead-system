import { useRef, useState, type DragEvent } from 'react';
import { cachedWorkspace, refreshWorkspace } from '../../data/mutations';
import { useOpportunities, type Opportunity, type OpportunityStage } from '../../data/opportunities';
import type { Lead } from '../../data/types';
import { useSession } from '../../data/workspace';
import { SERVICES } from '../../domain/catalog';
import { OPPORTUNITY_STAGES, opportunityDate, opportunityMoney, stageLabel } from '../../domain/opportunities';
import { routeFor } from '../../lib/router';
import { Badge, Banner, Button, EmptyState, Link, LoadingState, Select } from '../../ui';
import { PageHeader } from '../shared/PageHeader';
import { OpportunityDialog } from './OpportunityDialog';
import { OpportunityHistoryDialog } from './OpportunityHistoryDialog';
import styles from './PipelineView.module.css';

interface Pending { lead: Lead; opportunity: Opportunity; stage: OpportunityStage }

function OpportunityCard({ opportunity: item, lead, onMove, onHistory, onDrag }: {
  opportunity: Opportunity; lead?: Lead;
  onMove: (stage: OpportunityStage) => void; onHistory: () => void; onDrag: () => void;
}) {
  const age = Math.max(0, Math.floor((Date.now() - new Date(item.stage_entered_at).getTime()) / 86_400_000));
  const service = SERVICES.find(row => row.slug === item.service_slug)?.name || 'Hizmet henüz seçilmedi';
  return <li className={`${styles.card} ${styles[item.stage]}`} draggable={item.can_write} onDragStart={event => { event.dataTransfer.setData('text/plain', String(item.id)); event.dataTransfer.effectAllowed = 'move'; onDrag(); }}>
    <Link to={routeFor({ leadId: item.lead_id })} className={styles.cardName}>{item.lead_name}</Link>
    <div className={styles.service}>{service}</div>
    <div className={styles.meta}><Badge>{stageLabel(item.stage)}</Badge><Badge tone={lead?.workflow?.ready_to_contact ? 'success' : 'warning'}>{lead?.workflow?.ready_to_contact ? 'Temasa hazır' : 'Kontrol gerekiyor'}</Badge><span>{age} gündür bu aşamada</span></div>
    <dl className={styles.facts}>
      <div><dt>Sorumlu</dt><dd>{item.owner_email || 'Atanmamış'}</dd></div>
      <div><dt>Son temas</dt><dd>{item.last_contact_at ? opportunityDate(item.last_contact_at) : 'Henüz yok'}</dd></div>
      <div><dt>Takip</dt><dd>{item.due_at ? opportunityDate(item.due_at) : 'Planlanmadı'}</dd></div>
      <div><dt>Tutar</dt><dd>{item.amount == null ? 'Henüz bilinmiyor' : opportunityMoney(item.amount)}</dd></div>
    </dl>
    {item.stage === 'lost' && <p className={styles.lostReason}>Neden: {item.lost_reason || 'Belirtilmedi'}</p>}
    <div className={styles.actions}>
      {item.can_write && <Select aria-label={`${item.lead_name} aşaması`} value={item.stage} onChange={event => onMove(event.target.value as OpportunityStage)}>{OPPORTUNITY_STAGES.map(option => <option key={option.key} value={option.key}>{option.label}</option>)}</Select>}
      {item.can_write && <Button size="sm" onClick={() => onMove(item.stage)}>Düzenle</Button>}
      <Button size="sm" onClick={onHistory}>Geçmiş</Button>
    </div>
  </li>;
}

export function PipelineView({ leads }: { leads: Lead[] }) {
  const { user } = useSession();
  const query = useOpportunities(user.email);
  const [mode, setMode] = useState<'board' | 'list'>(() => window.matchMedia('(max-width: 760px)').matches ? 'list' : 'board');
  const [filter, setFilter] = useState<OpportunityStage | 'all'>('all');
  const [pending, setPending] = useState<Pending | null>(null);
  const [creating, setCreating] = useState(false);
  const [history, setHistory] = useState<Opportunity | null>(null);
  const [dropTarget, setDropTarget] = useState<OpportunityStage | null>(null);
  const dragRef = useRef<number | null>(null);
  const items = query.data || [];
  const leadMap = new Map(leads.map(lead => [lead.lead_id, lead]));
  const registered = new Set(items.map(item => item.lead_id));
  const candidates = leads.filter(lead => lead.lead_id && !registered.has(lead.lead_id) && !['converted', 'lost'].includes(lead.status || '') && (user.role === 'admin' || lead.assigned_to?.toLowerCase() === user.email.toLowerCase()));
  const open = items.filter(item => !['won', 'lost'].includes(item.stage));
  const known = open.filter(item => item.amount != null);
  const total = known.reduce((sum, item) => sum + Number(item.amount), 0);
  const filtered = filter === 'all' ? items : items.filter(item => item.stage === filter);

  function move(item: Opportunity, stage: OpportunityStage) {
    const lead = leadMap.get(item.lead_id);
    if (lead && item.can_write) setPending({ lead, opportunity: item, stage });
  }
  function onDrop(event: DragEvent, stage: OpportunityStage) {
    event.preventDefault(); setDropTarget(null);
    const item = items.find(row => row.id === dragRef.current);
    dragRef.current = null;
    if (item && item.stage !== stage) move(item, stage);
  }
  async function refresh(leadId: number) {
    const [result] = await Promise.all([query.refetch(), refreshWorkspace()]);
    const lead = cachedWorkspace()?.leads.find(row => row.lead_id === leadId);
    if (result.isError || !lead) return undefined;
    return { lead, opportunity: result.data?.find(row => row.lead_id === leadId) };
  }
  function saved() { setPending(null); setCreating(false); void refreshWorkspace(); }
  function card(item: Opportunity) {
    return <OpportunityCard key={item.id} opportunity={item} lead={leadMap.get(item.lead_id)} onMove={stage => move(item, stage)} onHistory={() => setHistory(item)} onDrag={() => { dragRef.current = item.id; }} />;
  }

  return <div className={styles.root}>
    <PageHeader eyebrow="PIPELINE" title="Satış kanalı" subtitle={query.isPending ? 'Fırsatlar yükleniyor…' : query.isError && !query.data ? 'Fırsatlar alınamadı' : `${items.length} fırsat · ${open.length} açık · ${items.filter(item => item.stage === 'won').length} kazanıldı`} actions={<Button variant="primary" disabled={!candidates.length || query.isPending || query.isError} onClick={() => setCreating(true)}>Fırsat oluştur</Button>} />
    <div className={styles.toolbar}>
      <div className={styles.modes} role="group" aria-label="Pipeline görünümü"><Button aria-pressed={mode === 'board'} onClick={() => setMode('board')}>Pano</Button><Button aria-pressed={mode === 'list'} onClick={() => setMode('list')}>Liste</Button></div>
      <Select aria-label="Aşamaya göre filtrele" value={filter} onChange={event => setFilter(event.target.value as OpportunityStage | 'all')}><option value="all">Tüm aşamalar</option>{OPPORTUNITY_STAGES.map(stage => <option key={stage.key} value={stage.key}>{stage.label} ({items.filter(item => item.stage === stage.key).length})</option>)}</Select>
      {!query.isPending && (query.data || !query.isError) && <div className={styles.total}>{known.length ? `${opportunityMoney(total)} bilinen açık fırsat tutarı` : 'Bilinen açık fırsat tutarı yok'} · {open.length - known.length} tutar eksik</div>}
    </div>
    {query.isError && <div className={styles.error}><Banner tone="danger" urgent actionLabel="Tekrar dene" onAction={() => void query.refetch()}>Fırsatlar alınamadı. Gösterilen kayıtlar eski olabilir.</Banner></div>}
    <p className={styles.scope}>Yalnızca oluşturulmuş satış fırsatları. Araştırma hazırlığı aşamadan ayrı gösterilir; eski lead’lere otomatik aşama atanmaz.</p>
    {query.isPending ? <LoadingState label="Fırsatlar yükleniyor…" /> : !items.length && !query.isError ? <div className={styles.emptyWrap}><EmptyState title="Henüz satış fırsatı yok">İşletme seçip “Fırsat oluştur” ile başla. Yeni bir görüşme sonucu da fırsat oluşturabilir.</EmptyState></div> : mode === 'list' ? <ul className={styles.list}>{filtered.map(card)}{!filtered.length && <li><EmptyState title="Bu aşamada fırsat yok">Diğer aşamaları seçebilirsin.</EmptyState></li>}</ul> : <div className={styles.board}>
      {OPPORTUNITY_STAGES.filter(stage => filter === 'all' || stage.key === filter).map(stage => <section key={stage.key} aria-labelledby={`stage-${stage.key}`} className={`${styles.column} ${styles[stage.key]} ${dropTarget === stage.key ? styles.dragOver : ''}`} onDragOver={event => { event.preventDefault(); setDropTarget(stage.key); }} onDragLeave={() => setDropTarget(null)} onDrop={event => onDrop(event, stage.key)}>
        <div className={styles.columnHead}><span className={styles.dot} aria-hidden="true" /><h2 id={`stage-${stage.key}`}>{stage.label}</h2><span className={styles.count}>{items.filter(item => item.stage === stage.key).length}</span></div>
        <ul className={styles.cards}>{items.filter(item => item.stage === stage.key).map(card)}</ul>
        {!items.some(item => item.stage === stage.key) && <div className={styles.empty}>Bu aşamada fırsat yok</div>}
      </section>)}
    </div>}
    {(pending || creating) && <OpportunityDialog key={pending?.opportunity.id || 'create'} lead={pending?.lead} opportunity={pending?.opportunity} candidates={candidates} stage={pending?.stage || 'new'} onClose={() => { setPending(null); setCreating(false); }} onSaved={saved} onRefresh={refresh} />}
    {history && <OpportunityHistoryDialog opportunity={history} onClose={() => setHistory(null)} />}
  </div>;
}
