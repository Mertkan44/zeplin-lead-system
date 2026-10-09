// The manager's desk: assign the next lead and see today's team numbers.
import { useEffect, useState } from 'react';

import { refreshWorkspace, saveLeadAssignment } from '../../data/mutations';
import type { Lead, User, WorkspaceSummary } from '../../data/types';
import { roleLabel, SERVICES } from '../../domain/catalog';
import { daysFromNowAtTen, initialsFor } from '../../domain/format';
import { Button, Field, Input, Select } from '../../ui';
import styles from './ManagerOperations.module.css';

export interface ManagerOperationsProps {
  leads: Lead[];
  teamUsers: User[];
  teamPerformance: Array<Record<string, any>>;
  summary: WorkspaceSummary | null;
}

export function ManagerOperations({ leads, teamUsers, teamPerformance, summary }: ManagerOperationsProps) {
  const members = teamUsers.filter(item => item.active !== false && ['sales', 'admin'].includes(String(item.role)));
  const unassigned = leads.filter(lead => !lead.assigned_to && !['converted', 'lost'].includes(String(lead.status)));
  const [leadName, setLeadName] = useState(unassigned[0]?.name || '');
  const [userEmail, setUserEmail] = useState(members.find(item => item.role === 'sales')?.email || members[0]?.email || '');
  const [dueAt, setDueAt] = useState(() => daysFromNowAtTen(1));
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState('');

  // Keep a valid choice when the list changes (a lead got assigned).
  useEffect(() => {
    if (leadName && !unassigned.some(item => item.name === leadName)) setLeadName(unassigned[0]?.name || '');
  }, [leads.length, unassigned.length]);

  // The team list loads separately; pick someone once it arrives.
  useEffect(() => {
    if (!userEmail && members.length) setUserEmail(members.find(item => item.role === 'sales')?.email || members[0].email);
  }, [members.length]);

  function assign() {
    if (!leadName || !userEmail) return;
    setBusy(true);
    setFeedback('');
    saveLeadAssignment(leadName, userEmail, dueAt)
      .then(() => {
        setFeedback('Lead atandı.');
        return refreshWorkspace();
      })
      .catch((error: Error) => setFeedback(error.message))
      .finally(() => setBusy(false));
  }

  const rows = members.map(member => ({
    ...member,
    performance: teamPerformance.find(row => row.email === member.email) || {},
  }));

  return (
    <section className={styles.section} aria-labelledby="manager-desk-title">
      <div className={styles.head}>
        <div>
          <div className={styles.eyebrow}>PATRON MASASI</div>
          <h2 id="manager-desk-title" className={styles.title}>Atama ve ekip temposu</h2>
        </div>
        <div className={styles.summary}><strong>{unassigned.length}</strong><span>Atanmamış lead</span></div>
      </div>
      <div className={styles.stats}>
        <div className={styles.stat}><strong>{summary?.today_result_count || 0}</strong><span>Bugünkü temas</span></div>
        <div className={styles.stat}><strong>{summary?.today_interested_count || 0}</strong><span>İlgi / teklif</span></div>
        <div className={styles.stat}><strong>{summary?.today_no_answer_count || 0}</strong><span>Ulaşılamadı</span></div>
        <div className={`${styles.stat} ${styles.statWarn}`}><strong>{summary?.overdue_follow_up_count || 0}</strong><span>Geciken takip</span></div>
      </div>
      <div className={styles.columns}>
        <div className={styles.panel}>
          <div className={styles.panelHead}><strong>Sıradaki lead’i ata</strong><span>Çalışanın Bugünkü İşler ekranına düşer</span></div>
          <div className={styles.form}>
            <Field label="Lead">
              {control => (
                <Select {...control} value={leadName} onChange={event => setLeadName(event.target.value)}>
                  {!unassigned.length && <option value="">Atanmamış lead yok</option>}
                  {unassigned.map(lead => <option key={lead.name} value={lead.name}>{lead.name} · {lead.workflow?.stage_label || 'Bekliyor'}</option>)}
                </Select>
              )}
            </Field>
            <div className={styles.formRow}>
              <Field label="Çalışan">
                {control => (
                  <Select {...control} value={userEmail} onChange={event => setUserEmail(event.target.value)}>
                    {members.map(member => <option key={member.email} value={member.email}>{member.name} · {member.title || roleLabel(member.role)}</option>)}
                  </Select>
                )}
              </Field>
              <Field label="Son tarih">
                {control => <Input {...control} type="datetime-local" value={dueAt} onChange={event => setDueAt(event.target.value)} />}
              </Field>
            </div>
            {feedback && <div className={styles.feedback} role="status">{feedback}</div>}
            <Button variant="primary" size="lg" block busy={busy} busyLabel="Atanıyor…" disabled={!leadName || !userEmail} onClick={assign}>Lead’i ata</Button>
          </div>
        </div>
        <div className={styles.panel}>
          <div className={styles.panelHead}><strong>Bugünkü ekip performansı</strong><span>Yalnızca kaydedilen gerçek işlemler</span></div>
          <div className={styles.tableWrap}>
            <ul className={styles.table}>
              {rows.map(member => (
                <li key={member.email} className={styles.row}>
                  <div className={styles.member}>
                    <div className={styles.avatar} aria-hidden="true">{initialsFor(member.name || member.email)}</div>
                    <span><strong>{member.name}</strong><small>{member.title || member.email}</small></span>
                  </div>
                  <div className={styles.metric}><strong>{member.performance.active_assignments || 0}</strong><span>Aktif</span></div>
                  <div className={styles.metric}><strong>{member.performance.contacts_today || 0}</strong><span>Görüşme</span></div>
                  <div className={styles.metric}><strong>{member.performance.interested_today || 0}</strong><span>İlgili</span></div>
                  <div className={styles.metric}><strong>{member.performance.no_answer_today || 0}</strong><span>Ulaşılamadı</span></div>
                  <div className={styles.metric}><strong>{member.performance.overdue_follow_ups || 0}</strong><span>Geciken</span></div>
                </li>
              ))}
            </ul>
          </div>
          {!!summary?.service_interest?.length && (
            <div className={styles.interest}>
              <span>Hizmet ilgisi</span>
              {summary.service_interest.map(item => (
                <strong key={item.slug}>{SERVICES.find(row => row.slug === item.slug)?.name || item.slug} · {item.count}</strong>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
