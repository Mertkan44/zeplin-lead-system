import type { Lead } from '../../data/types';
import { verifiedInstagram, websiteHost } from '../../domain/lead';
import styles from './shared.module.css';

/** Website / Instagram / Maps presence as chips; dashed when not verified. */
export function LeadSources({ lead }: { lead: Lead }) {
  const website = lead.website || {};
  const webAbsent = (lead.audit_findings || []).some(f => ['website.absent', 'website.invalid_candidate'].includes(f.code || ''));
  const chips: Array<{ label: string; found: boolean }> = [
    website.has_website
      ? { label: websiteHost(website.website_url), found: true }
      : { label: webAbsent ? 'Web yok' : 'Web doğrulanmadı', found: false },
    verifiedInstagram(lead)
      ? { label: '@' + (lead.social?.instagram_username || 'instagram'), found: true }
      : { label: 'Instagram doğrulanmadı', found: false },
  ];
  if (lead.maps_url) chips.push({ label: 'Google Maps', found: true });
  return (
    <span className={styles.chips}>
      {chips.map(chip => (
        <span key={chip.label} className={chip.found ? styles.chip : `${styles.chip} ${styles.chipMissing}`}>
          {chip.found && <span className={styles.dot} aria-hidden="true" />}
          {chip.label}
        </span>
      ))}
    </span>
  );
}
