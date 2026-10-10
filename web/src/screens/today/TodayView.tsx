// A sales user's day (review §12.3): overdue follow-ups, today's
// follow-ups, first contacts, then leads to verify. Each row: the business,
// why now, the previous result, one main action and "Detayı aç".
import { useMemo } from 'react';

import type { Lead, User, WorkspaceSummary } from '../../data/types';
import { fmtDate } from '../../domain/format';
import { contactedToday, groupTasks, lateness, SECTIONS, type TodayTask } from '../../domain/today';
import { routeFor } from '../../lib/router';
import { EmptyState, Link } from '../../ui';
import styles from './TodayView.module.css';

const clock = (date: Date) => date.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });

function When({ task }: { task: TodayTask }) {
  const { section, followUpAt, lead } = task;
  if (section === 'overdue' && followUpAt) {
    return <div className={`${styles.when} ${styles.late}`}><strong>{lateness(followUpAt)}</strong><span>{fmtDate(followUpAt.toISOString())}</span></div>;
  }
  if (section === 'due_today' && followUpAt) {
    return <div className={`${styles.when} ${styles.soon}`}><strong>{clock(followUpAt)}</strong><span>bugün</span></div>;
  }
  if (section === 'first_contact') {
    return task.assignmentLate
      ? <div className={`${styles.when} ${styles.late}`}><strong>Süre doldu</strong><span>atama tarihi</span></div>
      : <div className={styles.when}><strong>{lead.sales_priority_score || 0}</strong><span>öncelik</span></div>;
  }
  const workflow = lead.workflow || {};
  return <div className={styles.when}><strong>{workflow.completed_count || 0}/{workflow.required_count || 0}</strong><span>kontrol</span></div>;
}

function reasonFor(task: TodayTask): string {
  const workflow = task.lead.workflow || {};
  if (task.section === 'verification') {
    if (workflow.latest_outcome === 'wrong_number') return 'Numara yanlış çıktı; doğru iletişim bilgisini bul.';
    return `Eksik: ${(workflow.missing || []).join(', ') || 'kaynak kontrolü'}.`;
  }
  if (task.section === 'first_contact') {
    const evidence = (task.lead.sales_playbook?.evidence_points || [])[0];
    return evidence?.title ? `${evidence.title}` : task.lead.priority_reason || 'Kontrolleri tamam; ilk görüşmeyi yap.';
  }
  return workflow.latest_outcome_label ? `Önceki sonuç: ${workflow.latest_outcome_label}` : 'Takip görüşmesi.';
}

export interface TodayViewProps {
  leads: Lead[];
  user: User;
  summary: WorkspaceSummary | null;
  onOpenResult: (lead: Lead) => void;
}

export function TodayView({ leads, onOpenResult }: TodayViewProps) {
  const now = new Date();
  const groups = useMemo(() => groupTasks(leads), [leads]);
  const done = useMemo(() => contactedToday(leads), [leads]);
  const open = SECTIONS.reduce((sum, section) => sum + groups[section.key].length, 0);
  // Only the next task gets the accent button; the rest stay quiet (§11.3).
  const next = SECTIONS.map(section => groups[section.key][0]).find(Boolean)?.lead.name;

  return (
    <main className={styles.main}>
      <header className={styles.header}>
        <div>
          <div className={styles.date}>{now.toLocaleDateString('tr-TR', { weekday: 'long', day: 'numeric', month: 'long' })}</div>
          <h1 className={styles.title}>Bugün</h1>
        </div>
        <ul className={styles.summary} aria-label="Özet">
          {SECTIONS.map(section => (
            <li key={section.key} className={section.key === 'overdue' && groups.overdue.length ? `${styles.summaryItem} ${styles.summaryLate}` : styles.summaryItem}>
              <strong>{groups[section.key].length}</strong> {section.title.toLocaleLowerCase('tr-TR')}
            </li>
          ))}
        </ul>
      </header>

      {open === 0 && (
        <div className={styles.empty}>
          <EmptyState title="Bugün için açık iş yok.">Yeni lead atandığında veya bir takip zamanı geldiğinde burada görünür.</EmptyState>
        </div>
      )}

      {SECTIONS.filter(section => groups[section.key].length).map(section => (
        <section key={section.key} className={styles.section} aria-labelledby={`today-${section.key}`}>
          <div className={styles.sectionHead}>
            <h2 id={`today-${section.key}`} className={styles.sectionTitle}>{section.title}</h2>
            <span className={styles.sectionCount}>{groups[section.key].length}</span>
            <span className={styles.sectionHint}>{section.hint}</span>
          </div>
          <ul className={styles.list}>
            {groups[section.key].map(task => {
              const { lead } = task;
              const path = lead.lead_id != null ? routeFor({ leadId: lead.lead_id }) : null;
              const workflow = lead.workflow || {};
              const canContact = task.section !== 'verification';
              const main = lead.name === next ? styles.primary : styles.quiet;
              return (
                <li key={lead.name} className={styles.row}>
                  <When task={task} />
                  <div className={styles.body}>
                    <div className={styles.nameLine}>
                      <h3 className={styles.name}>{lead.name}</h3>
                      <span className={styles.place}>{[lead.category || lead.sector, lead.city].filter(Boolean).join(' · ')}</span>
                    </div>
                    <div className={styles.reason}>{reasonFor(task)}</div>
                    {workflow.latest_contact_at && task.section !== 'overdue' && task.section !== 'due_today' && (
                      <div className={styles.previous}>Son temas: {workflow.latest_outcome_label || 'kaydedildi'} · {fmtDate(workflow.latest_contact_at)}</div>
                    )}
                  </div>
                  <div className={styles.actions}>
                    {canContact
                      ? <button type="button" className={main} onClick={() => onOpenResult(lead)}>Görüşmeye başla</button>
                      : path && <Link to={path} className={main}>Kontrolü tamamla</Link>}
                    {path && <Link to={path} className={styles.secondary} aria-label={`${lead.name} detayını aç`}>Detayı aç</Link>}
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      ))}

      {done.length > 0 && (
        <details className={styles.done}>
          <summary>Bugün tamamlanan <span>{done.length}</span></summary>
          <ul className={styles.doneList}>
            {done.map(lead => (
              <li key={lead.name} className={styles.doneItem}>
                {lead.lead_id != null ? <Link to={routeFor({ leadId: lead.lead_id })}>{lead.name}</Link> : <span>{lead.name}</span>}
                <span>{lead.workflow?.latest_outcome_label || 'Sonuç kaydedildi'} · {clock(new Date(lead.workflow!.latest_contact_at!))}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </main>
  );
}
