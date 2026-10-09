import { useMemo, useState } from 'react';

import type { Lead, LeadStatus } from '../data/types';
import { searchLeads } from '../domain/lead';
import { followLink, routeFor } from '../lib/router';
import { Dialog, Input, StatusBadge } from '../ui';
import styles from './SearchDialog.module.css';

export interface SearchDialogProps {
  leads: Lead[];
  statuses: Record<string, LeadStatus>;
  onClose: () => void;
}

export function SearchDialog({ leads, statuses, onClose }: SearchDialogProps) {
  const [query, setQuery] = useState('');
  const results = useMemo(() => searchLeads(leads, query), [leads, query]);

  return (
    <Dialog eyebrow="HIZLI ERİŞİM" title="Lead ara" onClose={onClose}>
      <Input
        autoFocus
        size="lg"
        aria-label="Firma, ilçe, hizmet veya telefon"
        value={query}
        onChange={event => setQuery(event.target.value)}
        placeholder="Firma, ilçe, hizmet veya telefon"
      />
      <ul className={styles.results} aria-live="polite">
        {results.map(lead => {
          const path = lead.lead_id != null ? routeFor({ leadId: lead.lead_id }) : null;
          const body = (
            <>
              <span>
                <span className={styles.name}>{lead.name}</span>
                <span className={styles.meta}>{lead.city || 'Bölge yok'} · {lead.category || lead.sector || 'Kategori yok'}</span>
              </span>
              <StatusBadge status={statuses[lead.name]} />
            </>
          );
          return (
            <li key={lead.name}>
              {path
                ? <a href={path} className={styles.result} onClick={event => { followLink(event, path); if (event.defaultPrevented) onClose(); }}>{body}</a>
                : <div className={styles.result}>{body}</div>}
            </li>
          );
        })}
      </ul>
      {!results.length && <div className={styles.empty}>Bu aramayla eşleşen lead bulunamadı.</div>}
    </Dialog>
  );
}
