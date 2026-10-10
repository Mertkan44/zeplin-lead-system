// Every lead the user can see (review §12.4): search, filters and sorting in
// the URL, 25 per page, a table on wide screens and cards on phones, and an
// export of exactly the filtered rows.
import { useEffect, useMemo, useState } from 'react';

import type { Lead, User } from '../../data/types';
import { useCrm } from '../../data/workspace';
import { SERVICES, statusMeta } from '../../domain/catalog';
import { fmtDate, initialsFor } from '../../domain/format';
import {
  applyFilters,
  dataTrust,
  FILTER_KEYS,
  lastContact,
  leadsToCsv,
  NEXT_WORK_OPTIONS,
  nextWork,
  opportunity,
  SORT_OPTIONS,
  sortLeads,
  STAGE_OPTIONS,
  TRUST_LABELS,
  type ListFilters,
  type SortKey,
  type Trust,
} from '../../domain/leadList';
import { downloadFile } from '../../lib/browser';
import { routeFor, useQueryParams } from '../../lib/router';
import { Button, Dialog, EmptyState, Field, Input, Link, Select, StatusBadge } from '../../ui';
import styles from './LeadListView.module.css';

const PAGE_SIZE = 25;
const TRUST_OPTIONS: Array<[Trust, string]> = (Object.keys(TRUST_LABELS) as Trust[]).map(key => [key, TRUST_LABELS[key]]);

export interface LeadListViewProps {
  leads: Lead[];
  user: User;
  teamUsers: User[];
  onOpenResult: (lead: Lead) => void;
}

export function LeadListView({ leads, user, teamUsers, onOpenResult }: LeadListViewProps) {
  const { statuses } = useCrm();
  const [params, setParams] = useQueryParams();
  const [filtersOpen, setFiltersOpen] = useState(false);
  const isAdmin = user.role === 'admin';

  const filters = Object.fromEntries(FILTER_KEYS.map(key => [key, params.get(key) || ''])) as unknown as ListFilters;
  const sort = (SORT_OPTIONS.some(([key]) => key === params.get('sirala')) ? params.get('sirala') : 'oncelik') as SortKey;
  const page = Math.max(1, Number(params.get('sayfa')) || 1);

  // Typing updates the URL after a pause, replacing the entry (no history per key).
  const [query, setQuery] = useState(filters.q);
  useEffect(() => setQuery(filters.q), [filters.q]);
  useEffect(() => {
    if (query === filters.q) return undefined;
    const timer = setTimeout(() => setParams({ q: query, sayfa: null }, { replace: true }), 250);
    return () => clearTimeout(timer);
  }, [query]);

  const ownerName = useMemo(() => {
    const names = new Map(teamUsers.map(member => [member.email, member.name || member.email]));
    return (email: string) => names.get(email) || email;
  }, [teamUsers]);

  const now = new Date();
  const filtered = useMemo(() => sortLeads(applyFilters(leads, filters, statuses), sort), [leads, statuses, params.toString()]);
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const current = Math.min(page, pages);
  const rows = filtered.slice((current - 1) * PAGE_SIZE, current * PAGE_SIZE);

  const cities = useMemo(() => [...new Set(leads.map(lead => lead.city).filter((city): city is string => Boolean(city)))].sort((a, b) => a.localeCompare(b, 'tr')), [leads]);
  const owners = useMemo(() => [...new Set(leads.map(lead => lead.assigned_to).filter((email): email is string => Boolean(email)))], [leads]);

  const labelFor: Record<Exclude<keyof ListFilters, 'q'>, [string, (value: string) => string]> = {
    asama: ['Aşama', value => statusMeta(value).label],
    is: ['Sonraki iş', value => NEXT_WORK_OPTIONS.find(([key]) => key === value)?.[1] || value],
    sorumlu: ['Sorumlu', value => (value === 'yok' ? 'Atanmamış' : ownerName(value))],
    sehir: ['Şehir', value => value],
    hizmet: ['Hizmet', value => SERVICES.find(service => service.slug === value)?.name || value],
    guven: ['Veri güveni', value => TRUST_LABELS[value as Trust] || value],
  };
  const active = (Object.keys(labelFor) as Array<keyof typeof labelFor>).filter(key => filters[key]);
  const anyFilter = active.length > 0 || Boolean(filters.q);

  function setFilter(key: keyof ListFilters, value: string) {
    setParams({ [key]: value, sayfa: null });
  }

  function clearAll() {
    setQuery('');
    setParams({ ...Object.fromEntries(FILTER_KEYS.map(key => [key, null])), sayfa: null });
  }

  function exportCsv() {
    const csv = leadsToCsv(filtered, ownerName, lead => statusMeta(statuses[lead.name]).label);
    downloadFile('zeplin-leadler.csv', '\ufeff' + csv, 'text/csv;charset=utf-8;');
  }

  return (
    <main className={styles.root}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>Leadler</h1>
          <div className={styles.count} aria-live="polite">
            {anyFilter ? `${filtered.length} / ${leads.length} lead` : `${leads.length} lead`}
          </div>
        </div>
        <Button onClick={exportCsv} disabled={!filtered.length}>Dışa aktar (CSV)</Button>
      </div>

      <div className={styles.toolbar}>
        <div className={styles.search}>
          <Input type="search" aria-label="Leadlerde ara" placeholder="İsim, ilçe, telefon veya hizmet" value={query} onChange={event => setQuery(event.target.value)} />
        </div>
        <div className={styles.toolbarRight}>
          <Button onClick={() => setFiltersOpen(true)} aria-haspopup="dialog">
            Filtreler {active.length > 0 && <span className={styles.filterCount}>{active.length}</span>}
          </Button>
          <label className={styles.sort}>
            Sırala
            <Select value={sort} onChange={event => setParams({ sirala: event.target.value === 'oncelik' ? null : event.target.value, sayfa: null })}>
              {SORT_OPTIONS.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </Select>
          </label>
        </div>
      </div>

      {active.length > 0 && (
        <ul className={styles.chips} aria-label="Aktif filtreler">
          {active.map(key => (
            <li key={key} className={styles.chip}>
              <span>{labelFor[key][0]}:</span> {labelFor[key][1](filters[key])}
              <button type="button" className={styles.chipRemove} aria-label={`${labelFor[key][0]} filtresini kaldır`} onClick={() => setFilter(key, '')}>×</button>
            </li>
          ))}
          <li><button type="button" className={styles.clear} onClick={clearAll}>Temizle</button></li>
        </ul>
      )}

      {rows.length === 0 ? (
        <div className={styles.empty}>
          <EmptyState
            title={anyFilter ? 'Bu filtrelerle eşleşen lead yok.' : 'Henüz lead yok.'}
            action={anyFilter ? <Button onClick={clearAll}>Filtreleri temizle</Button> : undefined}
          >
            {anyFilter ? 'Filtreleri gevşet veya aramayı değiştir.' : 'Yeni lead için tarama başlatıldığında burada görünür.'}
          </EmptyState>
        </div>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">İşletme</th>
                <th scope="col">Sonraki iş</th>
                <th scope="col">Aşama</th>
                {isAdmin && <th scope="col">Sorumlu</th>}
                <th scope="col" className={styles.colOpportunity}>Fırsat</th>
                <th scope="col" className={styles.colContact}>Son temas</th>
                <th scope="col" className={styles.colTrust}>Veri güveni</th>
                <th scope="col"><span className="visually-hidden">İşlem</span></th>
              </tr>
            </thead>
            <tbody>
              {rows.map(lead => {
                const work = nextWork(lead, now);
                const offer = opportunity(lead);
                const contact = lastContact(lead);
                const trust = dataTrust(lead);
                const ready = Boolean(lead.workflow?.ready_to_contact || lead.workflow?.latest_contact_at);
                const workClass = work.kind === 'overdue' ? styles.workOverdue : work.kind === 'due_today' ? styles.workToday : '';
                return (
                  <tr key={lead.name}>
                    <td className={styles.cellBusiness}>
                      {lead.lead_id != null
                        ? <Link to={routeFor({ leadId: lead.lead_id })} className={styles.name}>{lead.name}</Link>
                        : <span className={styles.name}>{lead.name}</span>}
                      <span className={styles.sub}>{[lead.category || lead.sector, lead.city].filter(Boolean).join(' · ')}</span>
                    </td>
                    <td data-label="Sonraki iş" className={workClass}>
                      <span className={styles.strong}>{work.label}</span>
                      <span className={styles.sub}>{work.detail}</span>
                    </td>
                    <td data-label="Aşama"><StatusBadge status={statuses[lead.name]} /></td>
                    {isAdmin && (
                      <td data-label="Sorumlu">
                        {lead.assigned_to
                          ? <span className={styles.owner}><span className={styles.avatar} aria-hidden="true">{initialsFor(ownerName(lead.assigned_to))}</span>{ownerName(lead.assigned_to).split(' ')[0]}</span>
                          : <span className={styles.muted}>Atanmamış</span>}
                      </td>
                    )}
                    <td data-label="Fırsat" className={styles.colOpportunity}>
                      <span className={styles.strong}>{offer.service}</span>
                      {offer.level !== 'none' && <span className={`${styles.level} ${offer.level === 'proven' ? styles.proven : styles.discovery}`}>{offer.level === 'proven' ? 'Kanıtlı' : 'Görüşmede doğrula'}</span>}
                    </td>
                    <td data-label="Son temas" className={styles.colContact}>
                      {contact
                        ? <><span className={styles.strong}>{contact.outcome}</span><span className={styles.sub}>{fmtDate(contact.at)}</span></>
                        : <span className={styles.muted}>Henüz yok</span>}
                    </td>
                    <td data-label="Veri güveni" className={styles.colTrust}>
                      <span className={`${styles.trust} ${styles[`trust-${trust}`]}`}><span className={styles.trustDot} aria-hidden="true" />{TRUST_LABELS[trust]}</span>
                    </td>
                    <td className={styles.cellAction}>
                      {ready && <button type="button" className={styles.action} onClick={() => onOpenResult(lead)} aria-label={`${lead.name} için sonuç kaydet`}>Sonuç kaydet</button>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {filtered.length > PAGE_SIZE && (
        <nav className={styles.pager} aria-label="Sayfalar">
          <span>{(current - 1) * PAGE_SIZE + 1}–{Math.min(current * PAGE_SIZE, filtered.length)} / {filtered.length}</span>
          <div className={styles.pagerButtons}>
            <Button disabled={current <= 1} onClick={() => setParams({ sayfa: current - 1 > 1 ? String(current - 1) : null })}>← Önceki</Button>
            <Button disabled={current >= pages} onClick={() => setParams({ sayfa: String(current + 1) })}>Sonraki →</Button>
          </div>
        </nav>
      )}

      {filtersOpen && (
        <Dialog title="Filtreler" placement="right" size="md" onClose={() => setFiltersOpen(false)}>
          <div className={styles.filters}>
            <Field label="Aşama">
              {control => (
                <Select {...control} value={filters.asama} onChange={event => setFilter('asama', event.target.value)}>
                  <option value="">Hepsi</option>
                  {STAGE_OPTIONS.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                </Select>
              )}
            </Field>
            <Field label="Sonraki iş">
              {control => (
                <Select {...control} value={filters.is} onChange={event => setFilter('is', event.target.value)}>
                  <option value="">Hepsi</option>
                  {NEXT_WORK_OPTIONS.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                </Select>
              )}
            </Field>
            {isAdmin && (
              <Field label="Sorumlu">
                {control => (
                  <Select {...control} value={filters.sorumlu} onChange={event => setFilter('sorumlu', event.target.value)}>
                    <option value="">Hepsi</option>
                    <option value="yok">Atanmamış</option>
                    {owners.map(email => <option key={email} value={email}>{ownerName(email)}</option>)}
                  </Select>
                )}
              </Field>
            )}
            <Field label="Şehir">
              {control => (
                <Select {...control} value={filters.sehir} onChange={event => setFilter('sehir', event.target.value)}>
                  <option value="">Hepsi</option>
                  {cities.map(city => <option key={city} value={city}>{city}</option>)}
                </Select>
              )}
            </Field>
            <Field label="Kanıtlı hizmet">
              {control => (
                <Select {...control} value={filters.hizmet} onChange={event => setFilter('hizmet', event.target.value)}>
                  <option value="">Hepsi</option>
                  {SERVICES.map(service => <option key={service.slug} value={service.slug}>{service.name}</option>)}
                </Select>
              )}
            </Field>
            <Field label="Veri güveni">
              {control => (
                <Select {...control} value={filters.guven} onChange={event => setFilter('guven', event.target.value)}>
                  <option value="">Hepsi</option>
                  {TRUST_OPTIONS.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                </Select>
              )}
            </Field>
            <div className={styles.filterFooter}>
              <Button onClick={clearAll} disabled={!anyFilter}>Temizle</Button>
              <Button variant="primary" onClick={() => setFiltersOpen(false)}>{filtered.length} sonucu göster</Button>
            </div>
          </div>
        </Dialog>
      )}
    </main>
  );
}
