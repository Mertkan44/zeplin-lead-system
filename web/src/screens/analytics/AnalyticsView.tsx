// Reports over the leads analysed in the chosen period: grades, funnel,
// average score, weekly volume, sectors and contact readiness. Every chart
// also states its numbers as text.
import { useState, type CSSProperties } from 'react';

import type { Lead } from '../../data/types';
import { useCrm } from '../../data/workspace';
import { GRADE_COLORS } from '../../domain/catalog';
import { canonicalSector, computeReadinessBuckets, computeTabCounts, computeWeekBuckets } from '../../domain/lead';
import { PageHeader } from '../shared/PageHeader';
import styles from './AnalyticsView.module.css';

type Period = 7 | 30 | 90 | 'all';

const PERIODS: Array<[Period, string]> = [[7, '7g'], [30, '30g'], [90, 'Çeyrek'], ['all', 'Tümü']];
const SECTOR_COLORS = ['#b6f24a', '#ffcf4a', '#ff8f4a', '#7cc5ff', '#a78bfa'];
const GAUGE = 389.6;

const vars = (values: Record<string, string>) => values as CSSProperties;

function inPeriod(lead: Lead, cutoff: number | null): boolean {
  if (cutoff === null) return true;
  if (!lead.last_analyzed) return false;
  const stamp = new Date(lead.last_analyzed.replace(' ', 'T')).getTime();
  return !Number.isNaN(stamp) && stamp >= cutoff;
}

export function AnalyticsView({ leads }: { leads: Lead[] }) {
  const { statuses } = useCrm();
  const [period, setPeriod] = useState<Period>('all');
  const cutoff = period === 'all' ? null : Date.now() - period * 86400000;
  const periodLeads = leads.filter(lead => inPeriod(lead, cutoff));
  const actualTotal = periodLeads.length;
  const total = actualTotal || 1;

  const gradeCounts: Record<string, number> = { A: 0, B: 0, C: 0, D: 0 };
  periodLeads.forEach(lead => { if (lead.scoring?.grade in gradeCounts) gradeCounts[lead.scoring.grade] += 1; });
  const gradeMax = Math.max(...Object.values(gradeCounts), 1);

  const counts = computeTabCounts(periodLeads, statuses);
  const funnel = [
    { label: 'Toplam', count: actualTotal, className: styles.stepTotal },
    { label: 'Yeni', count: counts.yeni, className: styles.stepNew },
    { label: 'Temasta', count: counts.contacted, className: styles.stepContacted },
    { label: 'Kazanıldı', count: counts.converted, className: styles.stepWon },
  ];

  const avgScore = Math.round(periodLeads.reduce((sum, lead) => sum + (lead.scoring?.score || 0), 0) / total);
  const weekBuckets = computeWeekBuckets(periodLeads);
  const weekMax = Math.max(...weekBuckets, 1);
  const weeklyTotal = weekBuckets.reduce((sum, value) => sum + value, 0);

  const sectorCounts = new Map<string, number>();
  periodLeads.forEach(lead => {
    const sector = canonicalSector(lead);
    sectorCounts.set(sector, (sectorCounts.get(sector) || 0) + 1);
  });
  const sectors = [...sectorCounts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5)
    .map(([name, count], index) => ({ name, pct: Math.round((count / total) * 100), color: SECTOR_COLORS[index] }));

  const readiness = computeReadinessBuckets(periodLeads);

  return (
    <div className={styles.root}>
      <PageHeader
        eyebrow={period === 'all' ? 'PERFORMANS · TÜM ZAMANLAR' : `PERFORMANS · SON ${period} GÜN`}
        title="Raporlar"
        actions={(
          <div className={styles.periods} role="group" aria-label="Dönem">
            {PERIODS.map(([value, label]) => (
              <button type="button" key={value} className={styles.period} aria-pressed={period === value} onClick={() => setPeriod(value)}>{label}</button>
            ))}
          </div>
        )}
      />

      <div className={styles.grid}>
        <section className={styles.card} aria-labelledby="grades-title">
          <h2 id="grades-title" className={styles.cardTitle}>Not Dağılımı</h2>
          <div className={styles.cardSub}>{actualTotal} lead sınıflandırıldı</div>
          <ul className={styles.stack}>
            {['A', 'B', 'C', 'D'].map(grade => (
              <li key={grade} style={vars({ '--fill': GRADE_COLORS[grade], '--pct': `${(gradeCounts[grade] / gradeMax) * 100}%` })}>
                <div className={styles.rowHead}><span className={styles.gradeLabel}>Sınıf {grade}</span><span className={styles.num}>{gradeCounts[grade]}</span></div>
                <div className={styles.track} aria-hidden="true"><span className={styles.fill} /></div>
              </li>
            ))}
          </ul>
        </section>

        <section className={styles.card} aria-labelledby="funnel-title">
          <h2 id="funnel-title" className={styles.cardTitle}>Dönüşüm Hunisi</h2>
          <div className={styles.cardSub}>Yeni → Müşteri · %{Math.round((counts.converted / total) * 100)}</div>
          <ol className={styles.funnel}>
            {funnel.map(step => (
              <li key={step.label} className={`${styles.step} ${step.className}`} style={vars({ '--pct': `${40 + (step.count / total) * 60}%` })}>
                <span>{step.label}</span>
                <strong>{step.count}</strong>
              </li>
            ))}
          </ol>
        </section>

        <section className={`${styles.card} ${styles.gaugeCard}`} aria-labelledby="score-title">
          <h2 id="score-title" className={styles.cardTitle}>Ortalama Skor</h2>
          <div className={styles.cardSub}>tüm aktif leadler</div>
          <div className={styles.gauge}>
            <svg width="150" height="150" viewBox="0 0 150 150" aria-hidden="true">
              <circle cx="75" cy="75" r="62" fill="none" stroke="var(--line2)" strokeWidth="11" />
              <circle className={styles.gaugeProgress} cx="75" cy="75" r="62" fill="none" stroke="var(--accent)" strokeWidth="11" strokeLinecap="round" strokeDasharray={GAUGE} strokeDashoffset={GAUGE * (1 - Math.min(avgScore, 100) / 100)} />
            </svg>
            <div className={styles.gaugeValue}><strong>{avgScore}</strong><span>/ 100</span></div>
          </div>
        </section>

        <section className={`${styles.card} ${styles.wide}`} aria-labelledby="weekly-title">
          <div className={styles.weeklyHead}>
            <div>
              <h2 id="weekly-title" className={styles.cardTitle}>Haftalık Yeni Lead</h2>
              <div className={styles.cardSub}>tarama hacmi · 8 hafta</div>
            </div>
            <div className={styles.weeklyTotal}>{weeklyTotal}<span> toplam</span></div>
          </div>
          <ol className={styles.weeks}>
            {weekBuckets.map((value, index) => (
              <li key={index} className={styles.week}>
                <span className={styles.weekCount}>{value}</span>
                <span className={styles.weekBar} style={vars({ '--pct': `${Math.max((value / weekMax) * 100, 4)}%` })} aria-hidden="true" />
                <span className={styles.weekLabel}>{index === 7 ? 'Bu hafta' : `-${7 - index}h`}</span>
              </li>
            ))}
          </ol>
        </section>

        <section className={styles.card} aria-labelledby="sectors-title">
          <h2 id="sectors-title" className={styles.cardTitle}>Sektör Dağılımı</h2>
          <div className={styles.cardSub}>seçili dönemdeki {actualTotal} lead · benzer kategoriler birleştirildi</div>
          <ul className={styles.stack}>
            {sectors.map(sector => (
              <li key={sector.name} style={vars({ '--fill': sector.color, '--pct': `${sector.pct}%` })}>
                <div className={styles.rowHead}><span>{sector.name}</span><span className={styles.num}>{sector.pct}%</span></div>
                <div className={`${styles.track} ${styles.trackThin}`} aria-hidden="true"><span className={styles.fill} /></div>
              </li>
            ))}
          </ul>
        </section>

        <section className={`${styles.card} ${styles.full}`} aria-label="Temas hazırlığı">
          {[
            { label: 'Hazır arama', value: readiness.readyToCall, sub: 'telefon bilgisi tamam' },
            { label: 'Veri tamamlama', value: readiness.needsData, sub: 'telefon / adres eksik' },
            { label: 'Temasa hazır', value: readiness.proposalReady, sub: 'kanıt + hizmet + onaylı taslak' },
          ].map(item => (
            <div key={item.label} className={styles.readiness}>
              <strong>{item.value}</strong>
              <div className={styles.readinessLabel}>{item.label}</div>
              <div className={styles.readinessSub}>{item.sub}</div>
            </div>
          ))}
        </section>
      </div>
    </div>
  );
}
