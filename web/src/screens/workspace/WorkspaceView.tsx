// The manager's home: pipeline KPIs, the assignment desk, and the lead list
// with the selected lead's summary beside it.
import { useEffect, useMemo, useState } from 'react';

import type { Lead, User, WorkspaceSummary } from '../../data/types';
import { useCrm } from '../../data/workspace';
import type { LeadFilter } from '../../domain/catalog';
import { fmt, fmtDate } from '../../domain/format';
import { computeWeekBuckets, filterLeads, mostCommonCity, scoreIsAvailable } from '../../domain/lead';
import { routeFor } from '../../lib/router';
import { EmptyState, GradeBadge, Link, StatusBadge } from '../../ui';
import { FilterPills } from '../shared/FilterPills';
import { IconCalendar, IconPlus, IconTrend } from '../shared/icons';
import { LeadSources } from '../shared/LeadSources';
import { ScoreRing } from '../shared/ScoreRing';
import { ManagerOperations } from './ManagerOperations';
import { SelectedPanel } from './SelectedPanel';
import styles from './WorkspaceView.module.css';

export interface WorkspaceViewProps {
  leads: Lead[];
  user: User;
  summary: WorkspaceSummary | null;
  teamUsers: User[];
  teamPerformance: Array<Record<string, any>>;
}

export function WorkspaceView({ leads, user, summary, teamUsers, teamPerformance }: WorkspaceViewProps) {
  const { statuses } = useCrm();
  const [filter, setFilter] = useState<LeadFilter>('hepsi');
  const [selectedName, setSelectedName] = useState(leads[0]?.name);

  useEffect(() => {
    if (!leads.some(lead => lead.name === selectedName)) setSelectedName(leads[0]?.name);
  }, [leads]);

  const filtered = useMemo(() => filterLeads(leads, filter), [leads, filter]);
  const selected = leads.find(lead => lead.name === selectedName) || leads[0];
  const isAdmin = user.role === 'admin';

  const totalValue = leads.reduce((sum, lead) => sum + (lead.estimated_value_tl || 0), 0);
  const gradeA = leads.filter(lead => lead.scoring.grade === 'A').length;
  const weekBuckets = useMemo(() => computeWeekBuckets(leads), [leads]);
  const weekMax = Math.max(...weekBuckets, 1);
  const topCity = useMemo(() => mostCommonCity(leads), [leads]);
  const today = useMemo(() => new Date().toLocaleDateString('tr-TR', { day: '2-digit', month: 'long', year: 'numeric' }), []);

  const kpis = [
    { label: isAdmin ? 'Atanan Lead' : 'Bana Atanan', value: summary?.assigned_count ?? leads.filter(lead => lead.assigned_to || lead.assigned_user_id).length, delta: `${leads.length} görünür kayıt`, dot: 'var(--accent)' },
    { label: 'Bugünkü Arama', value: summary?.today_call_count ?? 0, delta: 'gerçek aktivite', dot: '#ffcf4a' },
    { label: 'Takip Bekleyen', value: summary?.follow_up_count ?? 0, delta: 'yeniden temas', dot: '#7cc5ff' },
    { label: 'Kazanılan', value: summary?.won_count ?? leads.filter(lead => statuses[lead.name] === 'converted').length, delta: 'müşteri oldu', dot: '#b6f24a' },
  ];

  return (
    <main className={styles.main}>
      <div className={styles.head}>
        <div>
          <div className={styles.eyebrow}>{topCity || 'Genel'} · lead sahası</div>
          <h1 className={styles.title}>Lead Workspace</h1>
        </div>
        <div className={styles.headActions}>
          <div className={styles.dateChip}><IconCalendar /><span>{today}</span></div>
          {isAdmin && <Link to={routeFor({ view: 'admin' })} className={styles.cta}><IconPlus /> Yeni Tarama</Link>}
        </div>
      </div>

      <div className={styles.kpis}>
        <div className={styles.accentCard}>
          <div className={styles.accentTop}>
            <div>
              <div className={styles.accentLabel}>Tahmini Pipeline</div>
              <div className={styles.accentValue}>~{fmt(totalValue)} ₺</div>
              <div className={styles.accentSub}>{leads.length} aktif lead · {gradeA} A sınıfı</div>
            </div>
            <div className={styles.accentIcon}><IconTrend /></div>
          </div>
          <div className={styles.bars} role="img" aria-label={`Son 8 haftada analiz edilen lead: ${weekBuckets.join(', ')}`}>
            {weekBuckets.map((count, index) => (
              <div key={index} className={index === 7 ? `${styles.bar} ${styles.barCurrent}` : styles.bar} style={{ height: `${Math.max((count / weekMax) * 100, 8)}%` }} />
            ))}
          </div>
        </div>
        {kpis.map(kpi => (
          <div key={kpi.label} className={styles.kpi}>
            <div className={styles.kpiTop}>
              <span className={styles.kpiLabel}>{kpi.label}</span>
              <span className={styles.kpiDot} style={{ background: kpi.dot }} aria-hidden="true" />
            </div>
            <div>
              <div className={styles.kpiValue}>{kpi.value}</div>
              <div className={styles.kpiDelta}>{kpi.delta}</div>
            </div>
          </div>
        ))}
      </div>

      {isAdmin && <ManagerOperations leads={leads} teamUsers={teamUsers} teamPerformance={teamPerformance} summary={summary} />}

      <div className={styles.body}>
        <div>
          <FilterPills active={filter} onChange={setFilter} count={filtered.length} />
          {filtered.length === 0 ? (
            <EmptyState>Bu filtrede lead yok.</EmptyState>
          ) : (
            <ul className={styles.cards}>
              {filtered.map(lead => {
                const available = scoreIsAvailable(lead);
                const issues = (lead.audit_findings || []).slice(0, 2);
                const services = (lead.matched_services || []).slice(0, 2);
                return (
                  <li key={lead.name}>
                    <button type="button" className={styles.card} aria-pressed={selected?.name === lead.name} onClick={() => setSelectedName(lead.name)}>
                      <span className={styles.cardTop}>
                        <span className={styles.cardMain}>
                          <span className={styles.cardStatus}>
                            <StatusBadge status={statuses[lead.name]} />
                            <span className={styles.cardDate}>{fmtDate(lead.last_analyzed)}</span>
                          </span>
                          <span className={styles.cardName}>{lead.name}</span>
                          <span className={styles.cardSub}>
                            {lead.category || lead.sector || 'İşletme'} · {lead.city} · <strong>{(lead.estimated_value_tl || 0) > 0 ? `~${fmt(lead.estimated_value_tl)} ₺` : '—'}</strong>
                          </span>
                        </span>
                        <span className={styles.cardScore}>
                          <ScoreRing score={lead.scoring.score} grade={lead.scoring.grade} scoreStatus={lead.scoring.score_status} size={56} stroke={4} />
                          <GradeBadge grade={available ? lead.scoring.grade : null} label={available ? lead.scoring.grade : `%${lead.scoring?.coverage || 0}`} />
                        </span>
                      </span>
                      <span className={styles.cardSources}><LeadSources lead={lead} /></span>
                      {(issues.length > 0 || services.length > 0) && (
                        <span className={styles.tags}>
                          {issues.map((finding, index) => <span key={`i${index}`} className={styles.tagIssue}>{finding.title}</span>)}
                          {services.map(service => <span key={service.slug} className={styles.tagOpp}>{service.name}</span>)}
                        </span>
                      )}
                      <span className={styles.cardFoot}>
                        <span>Son analiz · {fmtDate(lead.last_analyzed) || '—'}</span>
                        <span className={styles.cardPriority}>Öncelik <strong>{lead.sales_priority_score || 0}</strong></span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <aside className={styles.panel} aria-label="Seçili lead">
          {selected && <SelectedPanel key={selected.name} lead={selected} />}
        </aside>
      </div>
    </main>
  );
}
