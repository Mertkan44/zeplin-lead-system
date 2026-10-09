// Every lead the user can see, filterable, each row a link to the lead.
import { useMemo, useState } from 'react';

import { exportLeadsCSV } from '../../data/leadActions';
import type { Lead } from '../../data/types';
import { useCrm } from '../../data/workspace';
import { gradeColor, type LeadFilter } from '../../domain/catalog';
import { fmt } from '../../domain/format';
import { filterLeads } from '../../domain/lead';
import { routeFor } from '../../lib/router';
import { GradeBadge, Link, StatusBadge } from '../../ui';
import { FilterPills } from '../shared/FilterPills';
import { IconDownload } from '../shared/icons';
import { PageHeader } from '../shared/PageHeader';
import styles from './LeadListView.module.css';

export function LeadListView({ leads }: { leads: Lead[] }) {
  const { statuses } = useCrm();
  const [filter, setFilter] = useState<LeadFilter>('hepsi');
  const filtered = useMemo(() => filterLeads(leads, filter), [leads, filter]);

  return (
    <div className={styles.root}>
      <PageHeader
        eyebrow="TÜM İŞLETMELER · VERİTABANI"
        title="Leadler"
        actions={<button type="button" className={styles.export} onClick={() => exportLeadsCSV(leads)}><IconDownload /> Dışa Aktar</button>}
      />
      <div className={styles.filters}>
        <FilterPills active={filter} onChange={setFilter} count={filtered.length} />
      </div>
      <div className={styles.tableWrap}>
        <div className={`${styles.columns} ${styles.headRow}`} aria-hidden="true">
          <span>İşletme</span><span>Skor</span><span>Durum</span><span>Değer</span><span>Öncelik</span>
        </div>
        {filtered.length ? (
          <ul className={styles.rows} aria-label="Leadler">
            {filtered.map(lead => {
              const color = gradeColor(lead.scoring.grade);
              const body = (
                <>
                  <span className={styles.business}>
                    <span className={styles.gradeDot} style={{ background: color }} aria-hidden="true" />
                    <span className={styles.nameBlock}>
                      <span className={styles.name}>{lead.name}</span>
                      <span className={styles.sub}>{lead.category || lead.sector || 'İşletme'} · {lead.city}</span>
                    </span>
                  </span>
                  <span className={styles.score}>
                    <span className={styles.scoreValue} style={{ color }}>{lead.scoring.score}</span>
                    <GradeBadge grade={lead.scoring.grade} />
                  </span>
                  <span><StatusBadge status={statuses[lead.name]} /></span>
                  <span className={styles.value}>{(lead.estimated_value_tl || 0) > 0 ? `~${fmt(lead.estimated_value_tl)} ₺` : '—'}</span>
                  <span className={styles.priority}>
                    <span className={styles.track} aria-hidden="true"><span className={styles.fill} style={{ width: `${lead.sales_priority_score || 0}%` }} /></span>
                    <span className={styles.priorityValue}>{lead.sales_priority_score || 0}</span>
                  </span>
                </>
              );
              return (
                <li key={lead.name}>
                  {lead.lead_id != null
                    ? <Link to={routeFor({ leadId: lead.lead_id })} className={`${styles.columns} ${styles.row}`}>{body}</Link>
                    : <div className={`${styles.columns} ${styles.row}`}>{body}</div>}
                </li>
              );
            })}
          </ul>
        ) : (
          <div className={styles.empty}>Bu filtrede lead yok.</div>
        )}
      </div>
    </div>
  );
}
