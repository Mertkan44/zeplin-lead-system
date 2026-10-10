import { useInfiniteQuery } from '@tanstack/react-query';
import { fetchOpportunityHistory, opportunityKeys, type Opportunity } from '../../data/opportunities';
import { useSession } from '../../data/workspace';
import { opportunityDate, opportunityMoney, stageLabel } from '../../domain/opportunities';
import { SERVICES } from '../../domain/catalog';
import { Button, Dialog, EmptyState, Banner } from '../../ui';
import styles from './PipelineView.module.css';

const SOURCE_LABELS: Record<string, string> = { pipeline: 'Pipeline', contact_result: 'Görüşme sonucu', legacy_status: 'Eski durum işlemi' };

export function OpportunityHistoryDialog({ opportunity, onClose }: { opportunity: Opportunity; onClose: () => void }) {
  const { user } = useSession();
  const query = useInfiniteQuery({
    queryKey: [...opportunityKeys.historyRoot, user.email, opportunity.lead_id],
    initialPageParam: null as number | null,
    queryFn: ({ pageParam, signal }) => fetchOpportunityHistory(opportunity.lead_id, pageParam, signal),
    getNextPageParam: page => page.next_before ?? undefined,
  });
  const items = query.data?.pages.flatMap(page => page.items) || [];
  return <Dialog title={opportunity.lead_name} eyebrow="FIRSAT GEÇMİŞİ" placement="right" onClose={onClose}>
    <div className={styles.history}>
      <p className={styles.notice}>Aşama, tutar ve hizmet değişiklikleri · Saatler İstanbul saatidir.</p>
      {query.isPending && <p role="status">Geçmiş yükleniyor…</p>}
      {query.isError && <Banner tone="danger" urgent actionLabel="Tekrar dene" onAction={() => void query.refetch()}>Geçmiş alınamadı. Gösterilen kayıtlar eski olabilir.</Banner>}
      {!query.isPending && !query.isError && !items.length && <EmptyState title="Geçiş kaydı yok">Eski kayıtlardan satış aşaması geçmişi üretilmez.</EmptyState>}
      <ol className={styles.historyList}>{items.map(item => <li key={item.id}>
        <strong>{item.from_stage ? `${stageLabel(item.from_stage)} → ` : 'Fırsat oluşturuldu → '}{stageLabel(item.to_stage)}</strong>
        <div>{opportunityDate(item.happened_at)} · {SOURCE_LABELS[item.source] || 'İşlem'} · {item.actor_email || 'Sistem'}</div>
        <div>{item.amount == null ? 'Tutar bilinmiyor' : opportunityMoney(item.amount)}</div>
        <div>{SERVICES.find(service => service.slug === item.service_slug)?.name || 'Hizmet henüz seçilmedi'}</div>
        {item.note && <p>{item.note}</p>}
      </li>)}</ol>
      {query.hasNextPage && <Button busy={query.isFetchingNextPage} busyLabel="Yükleniyor…" onClick={() => void query.fetchNextPage()}>Daha eski kayıtlar</Button>}
    </div>
  </Dialog>;
}
