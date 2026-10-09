import { FILTER_DEFS, type LeadFilter } from '../../domain/catalog';
import styles from './shared.module.css';

export interface FilterPillsProps {
  active: LeadFilter;
  onChange: (filter: LeadFilter) => void;
  count: number;
}

export function FilterPills({ active, onChange, count }: FilterPillsProps) {
  return (
    <div className={styles.filters}>
      <div className={styles.pills} role="group" aria-label="Lead filtresi">
        {FILTER_DEFS.map(([key, label]) => (
          <button type="button" key={key} className={styles.pill} aria-pressed={active === key} onClick={() => onChange(key)}>{label}</button>
        ))}
      </div>
      <span className={styles.count} aria-live="polite">{count} işletme</span>
    </div>
  );
}
