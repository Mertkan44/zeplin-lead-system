import { gradeColor } from '../../domain/catalog';
import styles from './shared.module.css';

export interface ScoreRingProps {
  score: number;
  grade: string;
  scoreStatus?: string;
  size?: number;
  stroke?: number;
}

/** Audit score as a ring; "—" when the audit is too thin to score. */
export function ScoreRing({ score, grade, scoreStatus = 'reliable', size = 56, stroke = 4 }: ScoreRingProps) {
  const available = scoreStatus !== 'insufficient';
  const r = (size - stroke) / 2;
  const circumference = 2 * Math.PI * r;
  const offset = available ? circumference * (1 - Math.min(Math.max(score || 0, 0), 100) / 100) : circumference;
  const fontSize = size >= 70 ? 22 : size >= 50 ? 15 : 13;
  return (
    <div className={styles.ring} style={{ width: size, height: size }} role="img" aria-label={available ? `Skor ${score} / 100` : 'Skor hesaplanamadı'}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--line2)" strokeWidth={stroke} />
        <circle
          className={styles.ringProgress}
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={available ? gradeColor(grade) : 'var(--muted)'}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
        />
      </svg>
      <span className={styles.ringValue} style={{ fontSize }} aria-hidden="true">{available ? score : '—'}</span>
    </div>
  );
}
