// One lead (review §12.5). A sticky summary with the channels and the main
// action ("Sonuç kaydet"); tabs Özet / Araştırma / İletişim / Aktivite (the
// tab is in the URL); on the right the next task, stage, owner and offer.
// Phones get a two-button bar at the bottom. Render with key={lead id}.
import { useRef, type KeyboardEvent } from 'react';

import { recordCallStarted } from '../../data/leadActions';
import type { Lead, LeadStatus } from '../../data/types';
import { mergeEvents, useCrm, useLeadTimeline, useSession } from '../../data/workspace';
import { STATUS_OPTIONS } from '../../domain/catalog';
import { fmtDate } from '../../domain/format';
import { dataTrust, nextWork, opportunity, TRUST_LABELS } from '../../domain/leadList';
import { scoreIsAvailable, verifiedInstagram } from '../../domain/lead';
import { telLink, whatsappLink } from '../../domain/phone';
import { routeFor, useQueryParams } from '../../lib/router';
import { Button, Link, Select, StatusBadge } from '../../ui';
import { LeadActivityTab } from './LeadActivityTab';
import { LeadContactTab } from './LeadContactTab';
import { LeadResearchTab } from './LeadResearchTab';
import { LeadSummaryTab } from './LeadSummaryTab';
import styles from './LeadPage.module.css';

const TABS = [
  { key: 'ozet', label: 'Özet' },
  { key: 'arastirma', label: 'Araştırma' },
  { key: 'iletisim', label: 'İletişim' },
  { key: 'aktivite', label: 'Aktivite' },
] as const;

type TabKey = (typeof TABS)[number]['key'];

export interface LeadDetailViewProps {
  lead: Lead;
  index: number;
  total: number;
  status: LeadStatus;
  homePath: string;
  ownerName: string | null;
  placesEnabled: boolean;
  onStatusChange: (status: LeadStatus) => void;
  onPrev: () => void;
  onNext: () => void;
  onOpenResult: () => void;
}

export function LeadDetailView(props: LeadDetailViewProps) {
  const { lead, index, total, status, homePath, ownerName, placesEnabled, onStatusChange, onPrev, onNext, onOpenResult } = props;
  const crm = useCrm();
  const { user } = useSession();
  // The workspace carries the last 30 days of events; this adds the lead's full timeline.
  const timeline = useLeadTimeline(user.email, lead.name);
  const events = mergeEvents(crm.eventsFor(lead.name), timeline.data || []);
  const [params, setParams] = useQueryParams();
  const tab: TabKey = TABS.some(item => item.key === params.get('sekme')) ? (params.get('sekme') as TabKey) : 'ozet';
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  const workflow = lead.workflow || {};
  const ready = Boolean(workflow.ready_to_contact || workflow.latest_contact_at);
  const work = nextWork(lead);
  const offer = opportunity(lead);
  const trust = dataTrust(lead);
  const whatsapp = whatsappLink(lead.phone);
  const email = lead.email || (lead.research?.website?.emails || [])[0];
  const instagram = verifiedInstagram(lead) ? lead.social?.instagram_url : lead.manual_verification?.instagram?.url;
  const websiteUrl = lead.website?.website_url;
  const personEvents = events.filter(event => ['contact_result_recorded', 'note_added'].includes(event.action)).length;

  function selectTab(key: TabKey) {
    setParams({ sekme: key === 'ozet' ? null : key }, { replace: true });
  }

  // Arrow keys move between tabs (WAI-ARIA tabs pattern).
  function onTabKey(event: KeyboardEvent) {
    const order = TABS.map(item => item.key);
    const current = order.indexOf(tab);
    const next = event.key === 'ArrowRight' ? order[(current + 1) % order.length]
      : event.key === 'ArrowLeft' ? order[(current - 1 + order.length) % order.length]
        : event.key === 'Home' ? order[0] : event.key === 'End' ? order[order.length - 1] : null;
    if (!next) return;
    event.preventDefault();
    selectTab(next);
    tabRefs.current[next]?.focus();
  }

  const mainAction = ready
    ? <button type="button" className={styles.primary} onClick={onOpenResult}>Sonuç kaydet</button>
    : <button type="button" className={styles.primary} onClick={() => selectTab('arastirma')}>Kontrolleri tamamla ({workflow.completed_count || 0}/{workflow.required_count || 0})</button>;

  return (
    <main className={styles.root}>
      <header className={styles.summary}>
        <div className={styles.topLine}>
          <nav aria-label="Konum">
            <ol className={styles.crumbs}>
              <li><Link to={homePath}>{user.role === 'sales' ? 'Bugün' : 'Genel bakış'}</Link></li>
              <li aria-hidden="true">/</li>
              <li><Link to={routeFor({ view: 'raporlar' })}>Leadler</Link></li>
              <li aria-hidden="true">/</li>
              <li aria-current="page">{lead.name}</li>
            </ol>
          </nav>
          <div className={styles.stepper}>
            <Button size="sm" variant="quiet" onClick={onPrev} disabled={index === 0}>‹ Önceki</Button>
            <Button size="sm" variant="quiet" onClick={onNext} disabled={index === total - 1}>Sonraki ›</Button>
          </div>
        </div>
        <div className={styles.identity}>
          <div className={styles.titleBlock}>
            <h1 className={styles.title}>{lead.name}</h1>
            <div className={styles.meta}>
              <span>{[lead.category || lead.sector, lead.city].filter(Boolean).join(' · ')}</span>
              <StatusBadge status={status} />
              <span className={styles.metaItem}><span className={styles.metaLabel}>Sorumlu:</span> {ownerName || 'Atanmamış'}</span>
              <span className={`${styles.metaItem} ${styles[`trust-${trust}`]}`}><span className={styles.dot} aria-hidden="true" />Veri {TRUST_LABELS[trust].toLocaleLowerCase('tr-TR')}</span>
            </div>
            <div className={styles.nextMobile}>
              Sıradaki iş: <strong className={work.kind === 'overdue' ? styles.late : work.kind === 'due_today' ? styles.today : undefined}>{work.label === '—' ? 'Planlı iş yok' : work.label}</strong>{work.label === '—' ? '' : ` · ${work.detail}`}
            </div>
          </div>
          <div className={styles.actions}>
            {lead.phone && <a className={styles.channel} href={telLink(lead.phone)} onClick={() => recordCallStarted(lead)}>Ara</a>}
            {whatsapp && <a className={styles.channel} href={whatsapp} target="_blank" rel="noopener noreferrer">WhatsApp ↗</a>}
            {email && <a className={styles.channel} href={`mailto:${email}`}>E-posta</a>}
            {websiteUrl && <a className={styles.channel} href={websiteUrl} target="_blank" rel="noopener noreferrer">Website ↗</a>}
            {lead.maps_url && <a className={styles.channel} href={lead.maps_url} target="_blank" rel="noopener noreferrer">Maps ↗</a>}
            {instagram && <a className={styles.channel} href={instagram} target="_blank" rel="noopener noreferrer">Instagram ↗</a>}
            {mainAction}
          </div>
        </div>
      </header>

      <div className={styles.layout}>
        <div className={styles.mainCol}>
          <div className={styles.tabs} role="tablist" aria-label="Lead bölümleri" onKeyDown={onTabKey}>
            {TABS.map(item => (
              <button
                key={item.key}
                ref={node => { tabRefs.current[item.key] = node; }}
                type="button"
                role="tab"
                id={`tab-${item.key}`}
                aria-selected={tab === item.key}
                aria-controls={`panel-${item.key}`}
                tabIndex={tab === item.key ? 0 : -1}
                className={styles.tab}
                onClick={() => selectTab(item.key)}
              >
                {item.label}
                {item.key === 'aktivite' && personEvents > 0 && <span className={styles.tabCount}>{personEvents}</span>}
              </button>
            ))}
          </div>
          <section role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
            {tab === 'ozet' && <LeadSummaryTab lead={lead} events={events} />}
            {tab === 'arastirma' && <LeadResearchTab lead={lead} placesEnabled={placesEnabled} />}
            {tab === 'iletisim' && <LeadContactTab lead={lead} />}
            {tab === 'aktivite' && <LeadActivityTab lead={lead} events={events} />}
          </section>
        </div>

        <aside className={styles.rail} aria-label="Lead durumu">
          <div className={styles.railCard}>
            <div className={styles.railLabel}>Sıradaki iş</div>
            <div className={`${styles.railValue} ${work.kind === 'overdue' ? styles.late : work.kind === 'due_today' ? styles.today : ''}`}>{work.label === '—' ? 'Planlı iş yok' : work.label}</div>
            <div className={styles.railDetail}>{work.detail}</div>
            {workflow.follow_up_at && <div className={styles.railDetail}>Takip tarihi: {fmtDate(workflow.follow_up_at)}</div>}
          </div>
          <div className={styles.railCard}>
            <label className={styles.railLabel} htmlFor="lead-stage">Aşama</label>
            <div className={styles.stage}>
              <Select id="lead-stage" value={status} onChange={event => onStatusChange(event.target.value as LeadStatus)}>
                {STATUS_OPTIONS.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
              </Select>
            </div>
          </div>
          <div className={styles.railCard}>
            <div className={styles.railRow}><span>Sorumlu</span><strong>{ownerName || 'Atanmamış'}</strong></div>
            {lead.assignment_due_at && <div className={styles.railRow}><span>Atama tarihi</span><strong>{fmtDate(lead.assignment_due_at)}</strong></div>}
            <div className={styles.railRow}><span>Fırsat</span><strong>{offer.service}</strong></div>
            {offer.level !== 'none' && <div className={styles.railRow}><span>Kanıt</span><strong>{offer.level === 'proven' ? 'Kanıtlı' : 'Görüşmede doğrula'}</strong></div>}
            <div className={styles.railRow}>
              <span>Denetim skoru</span>
              <strong>{scoreIsAvailable(lead) ? `${lead.scoring.score}/100 · ${lead.scoring.grade}` : `Yetersiz (%${lead.scoring?.coverage || 0})`}</strong>
            </div>
          </div>
        </aside>
      </div>

      <div className={styles.phoneBar}>
        {lead.phone
          ? <a className={styles.channel} href={telLink(lead.phone)} onClick={() => recordCallStarted(lead)}>Ara</a>
          : <button type="button" className={styles.channel} onClick={() => selectTab('arastirma')}>Kaynaklar</button>}
        {mainAction}
      </div>
    </main>
  );
}
