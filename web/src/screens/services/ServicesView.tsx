// The approved service catalog, with how many leads show a signal for each.
import type { Lead, ServiceMatch } from '../../data/types';
import { SERVICES } from '../../domain/catalog';
import { PageHeader } from '../shared/PageHeader';
import styles from './ServicesView.module.css';

const TYPE_LABELS: Record<string, string> = { monthly: 'Aylık', project: 'Proje', project_or_monthly: 'Proje / Aylık' };

export function ServicesView({ leads }: { leads: Lead[] }) {
  const matchesBySlug = new Map<string, ServiceMatch[]>();
  leads.forEach(lead => (lead.matched_services || []).forEach(match => {
    matchesBySlug.set(match.slug, [...(matchesBySlug.get(match.slug) || []), match]);
  }));

  const entries = SERVICES.map(service => {
    const matches = matchesBySlug.get(service.slug) || [];
    return {
      service,
      total: matches.length,
      confirmed: matches.filter(match => match.match_type === 'confirmed_gap').length,
      toVerify: matches.filter(match => ['conditional_gap', 'qualified_opportunity'].includes(match.match_type || '')).length,
    };
  }).sort((a, b) => b.total - a.total);
  const signals = entries.reduce((sum, entry) => sum + entry.total, 0);

  return (
    <div className={styles.root}>
      <PageHeader
        eyebrow="HİZMETLER"
        title="Zeplin Media Hizmetleri"
        subtitle={`${entries.length} onaylı hizmet · ${signals} ölçülebilir hizmet sinyali · Kesin açık ve görüşme fırsatı ayrı gösterilir`}
      />
      <ul className={styles.grid}>
        {entries.map(({ service, total, confirmed, toVerify }) => (
          <li key={service.slug} className={styles.card}>
            <div className={styles.tags}>
              <span className={`${styles.tag} ${service.monthly ? styles.tagMonthly : styles.tagProject}`}>{TYPE_LABELS[service.service_type] || 'Kapsamlanacak'}</span>
              <span className={styles.tag}>{service.category || 'Genel'}</span>
            </div>
            <h2 className={styles.name}>{service.name}</h2>
            {service.desc && <div className={styles.desc}>{service.desc}</div>}
            {service.detects && <div className={styles.detects}><strong>Bot tespit eder:</strong> {service.detects}</div>}
            <dl className={styles.stats}>
              <div><dt className={styles.statLabel}>Toplam Sinyal</dt><dd className={styles.statValue}>{total}</dd></div>
              <div><dt className={styles.statLabel}>Kesin Açık</dt><dd className={`${styles.statValue} ${styles.statConfirmed}`}>{confirmed}</dd></div>
              <div><dt className={styles.statLabel}>Görüşmede Doğrula</dt><dd className={`${styles.statValue} ${styles.statDiscovery}`}>{toVerify}</dd></div>
            </dl>
            <div className={styles.price}>Fiyat ve kapsam görüşme sonrasında yönetim onayıyla belirlenir.</div>
          </li>
        ))}
      </ul>
    </div>
  );
}
