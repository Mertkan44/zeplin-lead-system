// A sales user's work queue: follow-ups that are due first, then leads to
// verify, then leads ready to call.
import { useMemo, useState } from 'react';

import { recordCallStarted } from '../../data/leadActions';
import type { Lead, User, WorkspaceSummary } from '../../data/types';
import { useCrm } from '../../data/workspace';
import { taskMetaForLead, telHref, type TaskMeta } from '../../domain/lead';
import { routeFor } from '../../lib/router';
import { EmptyState, Link } from '../../ui';
import { IconCall } from '../shared/icons';
import styles from './TodayView.module.css';

type TaskFilter = 'open' | 'verification' | 'ready' | 'followup' | 'completed';

const isOpen = (meta: TaskMeta) => !meta.completedToday && meta.stage !== 'closed';
const isDone = (meta: TaskMeta) => meta.completedToday || ['contacted', 'closed'].includes(meta.stage);

const FILTERS: Array<[TaskFilter, string, (meta: TaskMeta) => boolean]> = [
  ['open', 'Açık işler', isOpen],
  ['verification', 'Kontrol', meta => meta.stage === 'verification_required'],
  ['ready', 'Aramaya hazır', meta => meta.stage === 'ready_to_contact'],
  ['followup', 'Takip', meta => meta.stage === 'follow_up_due'],
  ['completed', 'Tamamlanan', isDone],
];

export interface TodayViewProps {
  leads: Lead[];
  user: User;
  summary: WorkspaceSummary | null;
  onOpenResult: (lead: Lead) => void;
}

export function TodayView({ leads, user, summary, onOpenResult }: TodayViewProps) {
  const crm = useCrm();
  const [filter, setFilter] = useState<TaskFilter>('open');
  const tasks = useMemo(
    () => leads
      .filter(lead => !['converted', 'lost'].includes(crm.statuses[lead.name] || lead.status || ''))
      .map(lead => ({ lead, meta: taskMetaForLead(lead, crm.eventsFor(lead.name)) }))
      .sort((a, b) => b.meta.rank - a.meta.rank),
    [leads, crm],
  );
  const completed = leads.filter(lead => taskMetaForLead(lead, crm.eventsFor(lead.name)).completedToday).length;
  const now = new Date();
  const due = tasks.filter(item => item.meta.followUp && item.meta.followUp <= now).length;
  const matches = FILTERS.find(([key]) => key === filter)![2];
  const visible = tasks.filter(item => matches(item.meta));
  const firstName = (user.name || '').split(' ')[0] || 'ekip';

  function startCall(lead: Lead) {
    if (!lead.phone) return;
    recordCallStarted(lead);
    window.location.href = telHref(lead.phone);
  }

  return (
    <main className={styles.main}>
      <div className={styles.hero}>
        <div>
          <div className={styles.eyebrow}>SATIŞ MASASI · {now.toLocaleDateString('tr-TR', { day: '2-digit', month: 'long' })}</div>
          <h1 className={styles.title}>Bugünkü İşlerim</h1>
          <p className={styles.subtitle}>Merhaba {firstName}. Önce takipleri kapat, sonra en yüksek öncelikli yeni lead’lere geç.</p>
        </div>
        <div className={styles.heroStats}>
          <div className={styles.heroStat}><strong>{tasks.length}</strong><span>Açık iş</span></div>
          <div className={styles.heroStat}><strong>{due}</strong><span>Takip zamanı geldi</span></div>
          <div className={styles.heroStat}><strong>{completed}</strong><span>Bugün tamamlandı</span></div>
        </div>
      </div>

      <section className={styles.queueSection} aria-labelledby="today-queue-title">
        <div className={styles.sectionHead}>
          <div>
            <div className={styles.sectionEyebrow}>ÖNCELİK SIRASI</div>
            <h2 id="today-queue-title" className={styles.sectionTitle}>Sıradaki temaslar</h2>
          </div>
          <span className={styles.quiet}>{summary?.today_result_count || completed} sonuç bugün kaydedildi</span>
        </div>

        <div className={styles.tabs} role="group" aria-label="İş filtresi">
          {FILTERS.map(([key, label, test]) => (
            <button type="button" key={key} className={styles.tab} aria-pressed={filter === key} onClick={() => setFilter(key)}>
              {label} <span>{tasks.filter(item => test(item.meta)).length}</span>
            </button>
          ))}
        </div>

        {visible.length ? (
          <ol className={styles.queue}>
            {visible.map(({ lead, meta }, index) => {
              const playbook = lead.sales_playbook || {};
              const service = (playbook.services || [])[0];
              const evidence = (playbook.evidence_points || [])[0];
              const leadPath = lead.lead_id != null ? routeFor({ leadId: lead.lead_id }) : null;
              return (
                <li key={lead.name} className={styles.card}>
                  <div className={styles.order} aria-hidden="true">{String(index + 1).padStart(2, '0')}</div>
                  <div className={styles.body}>
                    <div className={styles.top}>
                      <div>
                        <div className={styles.flags}>
                          <span className={meta.rank >= 100 ? `${styles.flag} ${styles.flagHot}` : styles.flag}>{meta.label}</span>
                          <span className={styles.priority}>Öncelik {lead.sales_priority_score || 0}</span>
                        </div>
                        <h3 className={styles.name}>{lead.name}</h3>
                        <div className={styles.meta}>{lead.category || lead.sector || 'İşletme'} · {lead.city || 'Konum yok'}{service?.name ? ` · ${service.name}` : ''}</div>
                      </div>
                      <div className={styles.actions}>
                        {meta.ready && lead.phone && (
                          <button type="button" className={`${styles.action} ${styles.call}`} onClick={() => startCall(lead)}><IconCall /> Ara</button>
                        )}
                        {meta.ready
                          ? <button type="button" className={`${styles.action} ${styles.result}`} onClick={() => onOpenResult(lead)}>Temas ekranı</button>
                          : leadPath && <Link to={leadPath} className={`${styles.action} ${styles.result}`}>Kontrolü tamamla</Link>}
                        {leadPath && <Link to={leadPath} className={`${styles.action} ${styles.detail}`} aria-label={`${lead.name} detayı`}>Detay</Link>}
                      </div>
                    </div>
                    <div className={styles.context}>
                      <div>
                        <div className={styles.contextLabel}>NEDEN ŞİMDİ?</div>
                        <div className={styles.contextText}>{meta.detail}</div>
                        {evidence && <div className={styles.evidence}><strong>Kanıt:</strong> {evidence.title} · {evidence.evidence}</div>}
                      </div>
                      <div className={styles.opener}>
                        <div className={styles.contextLabel}>{meta.ready ? 'ARAMAYA BÖYLE BAŞLA' : 'HAZIRLIK DURUMU'}</div>
                        <div className={styles.openerText}>
                          {meta.ready
                            ? `“${playbook.call_opener || 'İşletmenin dijital hedeflerini öğrenerek görüşmeye başla.'}”`
                            : `${lead.workflow?.completed_count || 0}/${lead.workflow?.required_count || 0} kontrol tamamlandı. Temastan önce eksikleri kapat.`}
                        </div>
                      </div>
                    </div>
                  </div>
                </li>
              );
            })}
          </ol>
        ) : (
          <EmptyState>Bu bölümde bekleyen iş yok.</EmptyState>
        )}
      </section>
    </main>
  );
}
