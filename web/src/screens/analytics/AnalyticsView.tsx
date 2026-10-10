// Reports (review §10, §12.9). Sales performance in the chosen period,
// follow-ups and the status distribution as they are now, research quality,
// and the last eight weeks. Every number comes from the server
// (src/metrics.py) with the definition shown under it; "0" and "not measured"
// look different, and an empty bar is empty.
import type { CSSProperties } from 'react';

import { useMetrics, type CountItem, type Metric, type Metrics, type Period } from '../../data/metrics';
import type { User } from '../../data/types';
import { GRADE_COLORS } from '../../domain/catalog';
import { csvCell } from '../../domain/leadList';
import { downloadFile } from '../../lib/browser';
import { routeFor, useQueryParams } from '../../lib/router';
import { Button, ErrorState, Link, LoadingState } from '../../ui';
import styles from './AnalyticsView.module.css';

const PERIODS: Array<[Period, string]> = [['7', '7 gün'], ['30', '30 gün'], ['90', '90 gün'], ['all', 'Tümü']];
const vars = (values: Record<string, string>) => values as CSSProperties;
const leadsPath = (query: string) => `${routeFor({ view: 'raporlar' })}?${query}`;

function Kpi({ metric, to, late = false }: { metric: Metric; to?: string; late?: boolean }) {
  const body = (
    <>
      <span className={metric.value === null ? `${styles.kpiValue} ${styles.none}` : styles.kpiValue}>
        {metric.value === null ? 'Ölçülemedi' : metric.value}
      </span>
      <span className={styles.kpiLabel}>{metric.label}</span>
      <span className={styles.kpiDefinition}>
        {metric.definition}
        {metric.sample !== undefined && ` ${metric.sample} lead üzerinden${metric.excluded ? `; ${metric.excluded} lead hariç` : ''}.`}
      </span>
    </>
  );
  const className = late && metric.value ? `${styles.kpi} ${styles.kpiLate}` : styles.kpi;
  return <li>{to ? <Link to={to} className={className}>{body}</Link> : <div className={className}>{body}</div>}</li>;
}

function Bars({ items, color, link }: { items: Array<CountItem & { name: string }>; color?: (item: CountItem) => string; link?: (item: CountItem) => string | null }) {
  const max = Math.max(0, ...items.map(item => item.count));
  return (
    <ul className={styles.bars}>
      {items.map(item => {
        const href = link?.(item);
        return (
          <li key={item.name} className={styles.bar}>
            {href ? <Link to={href}>{item.name}</Link> : <span>{item.name}</span>}
            <span className={styles.track} aria-hidden="true">
              <span className={styles.fill} style={vars({ '--pct': max ? `${(item.count / max) * 100}%` : '0%', ...(color ? { '--fill': color(item) } : {}) })} />
            </span>
            <span className={styles.count}>{item.count}</span>
          </li>
        );
      })}
    </ul>
  );
}

function exportSummary(metrics: Metrics) {
  const rows: Array<[string, string, unknown]> = [];
  const add = (section: string, metric: Metric) => rows.push([section, metric.label, metric.value ?? '']);
  Object.values(metrics.sales).forEach(value => { if (!Array.isArray(value)) add('Satış', value); });
  metrics.sales.outcomes.forEach(item => rows.push(['Görüşme sonucu', item.label || '', item.count]));
  Object.values(metrics.tasks).forEach(metric => add('Takip (şu an)', metric));
  metrics.statuses.items.forEach(item => rows.push(['Durum (şu an)', item.label || '', item.count]));
  [metrics.research.new_leads, metrics.research.analyzed_leads, metrics.research.average_score, metrics.research.average_coverage].forEach(metric => add('Araştırma', metric));
  metrics.research.sectors.items.forEach(item => rows.push(['Sektör', item.label || '', item.count]));
  const csv = [['Bölüm', 'Metrik', 'Değer'], ...rows].map(row => row.map(csvCell).join(',')).join('\r\n');
  downloadFile(`zeplin-rapor-${metrics.period.key}.csv`, '\ufeff' + `${csvCell(metrics.period.label)}\r\n` + csv, 'text/csv;charset=utf-8;');
}

export function AnalyticsView({ user }: { user: User }) {
  const [params, setParams] = useQueryParams();
  const period = (PERIODS.some(([key]) => key === params.get('donem')) ? params.get('donem') : '30') as Period;
  const query = useMetrics(user.email, period);
  const metrics = query.data;

  if (query.isPending) return <LoadingState label="Raporlar hazırlanıyor…" />;
  if (!metrics) {
    return <ErrorState eyebrow="RAPORLAR" title="Raporlar alınamadı" message={query.error?.message || 'Sunucuya ulaşılamadı.'} onRetry={() => void query.refetch()} retrying={query.isFetching} />;
  }

  const { sales, tasks, statuses, research, weekly } = metrics;
  const weekMax = Math.max(0, ...weekly.new_leads, ...weekly.contact_results);

  return (
    <main className={styles.root} aria-busy={query.isFetching}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>Raporlar</h1>
          <div className={styles.scope}>{metrics.period.label} · İstanbul saati · {metrics.lead_count} lead{user.role === 'sales' ? ' (sana atananlar)' : ''}</div>
        </div>
        <div className={styles.headerActions}>
          <div className={styles.periods} role="group" aria-label="Dönem">
            {PERIODS.map(([key, label]) => (
              <button type="button" key={key} className={styles.period} aria-pressed={period === key} onClick={() => setParams({ donem: key === '30' ? null : key })}>{label}</button>
            ))}
          </div>
          <Button onClick={() => exportSummary(metrics)}>Özeti indir (CSV)</Button>
        </div>
      </div>

      <section className={styles.section} aria-labelledby="sales-title">
        <div className={styles.sectionHead}>
          <h2 id="sales-title" className={styles.sectionTitle}>Satış performansı</h2>
          <span className={styles.sectionNote}>{metrics.period.label}; görüşme sonucunun kaydedildiği tarihe göre</span>
        </div>
        <ul className={styles.kpis}>
          <Kpi metric={sales.contacted_businesses} />
          <Kpi metric={sales.contact_results} />
          <Kpi metric={sales.interested_businesses} />
          <Kpi metric={sales.proposal_businesses} />
          <Kpi metric={sales.won_businesses} />
          <Kpi metric={sales.lost_businesses} />
        </ul>
      </section>

      <section className={styles.section} aria-labelledby="tasks-title">
        <div className={styles.sectionHead}>
          <h2 id="tasks-title" className={styles.sectionTitle}>Takipler</h2>
          <span className={styles.sectionNote}>Şu an; dönem seçiminden etkilenmez</span>
        </div>
        <ul className={styles.kpis}>
          <Kpi metric={tasks.overdue} to={leadsPath('is=overdue')} late />
          <Kpi metric={tasks.due_today} to={leadsPath('is=due_today')} />
          <Kpi metric={tasks.upcoming} to={leadsPath('is=scheduled')} />
        </ul>
      </section>

      <section className={styles.section}>
        <div className={styles.panels}>
          <div className={styles.panel}>
            <h2 className={styles.panelTitle}>Görüşme sonuçları</h2>
            <p className={styles.panelNote}>{metrics.period.label}; her kayıt ayrı sayılır.</p>
            {sales.contact_results.value
              ? <Bars items={sales.outcomes.map(item => ({ ...item, name: item.label || '' }))} />
              : <p className={styles.empty}>Bu dönemde kaydedilmiş görüşme sonucu yok.</p>}
          </div>
          <div className={styles.panel}>
            <h2 className={styles.panelTitle}>{statuses.label}</h2>
            <p className={styles.panelNote}>{statuses.definition}</p>
            <Bars items={statuses.items.map(item => ({ ...item, name: item.label || '' }))} link={item => leadsPath(`asama=${item.key}`)} />
          </div>
        </div>
      </section>

      <section className={styles.section} aria-labelledby="research-title">
        <div className={styles.sectionHead}>
          <h2 id="research-title" className={styles.sectionTitle}>Araştırma kalitesi</h2>
          <span className={styles.sectionNote}>Yeni ve analiz edilen lead seçilen döneme göre; skorlar şu an</span>
        </div>
        <ul className={`${styles.kpis} ${styles.kpis4}`}>
          <Kpi metric={research.new_leads} />
          <Kpi metric={research.analyzed_leads} />
          <Kpi metric={research.average_score} />
          <Kpi metric={research.average_coverage} />
        </ul>
        <div className={`${styles.panels} ${styles.spaced}`}>
          <div className={styles.panel}>
            <h3 className={styles.panelTitle}>Dijital skor sınıfı</h3>
            <p className={styles.panelNote}>{research.grades.definition} Skoru hesaplanamayan: {research.grades.unscored}.</p>
            <Bars items={research.grades.items.map(item => ({ ...item, name: `Sınıf ${item.key}` }))} color={item => GRADE_COLORS[item.key || ''] || 'var(--text-secondary)'} />
          </div>
          <div className={styles.panel}>
            <h3 className={styles.panelTitle}>Sektör dağılımı</h3>
            <p className={styles.panelNote}>{research.sectors.definition} Toplam {research.sectors.total} lead.</p>
            {research.sectors.items.length
              ? <Bars items={research.sectors.items.map(item => ({ ...item, name: item.label || '' }))} />
              : <p className={styles.empty}>Henüz lead yok.</p>}
          </div>
        </div>
      </section>

      <section className={styles.section} aria-labelledby="weekly-title">
        <div className={styles.sectionHead}>
          <h2 id="weekly-title" className={styles.sectionTitle}>Son 8 hafta</h2>
          <span className={styles.sectionNote}>{weekly.definition}</span>
        </div>
        <div className={styles.panel}>
          <div className={styles.weeksWrap}>
            <table className={styles.weeks}>
              <thead>
                <tr>
                  <th scope="col">Hafta (pazartesi)</th>
                  <th scope="col">Yeni lead</th>
                  <th scope="col">Görüşme sonucu</th>
                </tr>
              </thead>
              <tbody>
                {weekly.weeks.map((week, index) => (
                  <tr key={week}>
                    <th scope="row">{new Date(`${week}T12:00:00`).toLocaleDateString('tr-TR', { day: 'numeric', month: 'long' })}{index === weekly.weeks.length - 1 ? ' (bu hafta)' : ''}</th>
                    {([[weekly.new_leads[index], 'var(--info-tx)'], [weekly.contact_results[index], 'var(--accent-text)']] as Array<[number, string]>).map(([value, fill], column) => (
                      <td key={column}>
                        <span className={styles.spark} style={vars({ '--w': weekMax ? `${Math.round((value / weekMax) * 100)}%` : '0%', '--fill': fill })} aria-hidden="true" />
                        <span className={styles.sparkValue}>{value}</span>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </main>
  );
}
