// The sales user's work queue (review §12.3): what to do today, in order.
// The server's workflow (src/workflow.py) decides the stage; this only sorts
// it into sections.
import type { Lead } from '../data/types';

export type TodaySection = 'overdue' | 'due_today' | 'first_contact' | 'verification';

export const SECTIONS: Array<{ key: TodaySection; title: string; hint: string }> = [
  { key: 'overdue', title: 'Geciken', hint: 'Takip tarihi geçmiş görüşmeler' },
  { key: 'due_today', title: 'Bugün takip', hint: 'Bugün yeniden aranacaklar' },
  { key: 'first_contact', title: 'İlk temas', hint: 'Kontrolleri tamam, henüz aranmadı' },
  { key: 'verification', title: 'Doğrulama gerekiyor', hint: 'Aramadan önce kaynakları kontrol et' },
];

export interface TodayTask {
  lead: Lead;
  section: TodaySection;
  followUpAt: Date | null;
  /** Assignment due date already passed (first contact only). */
  assignmentLate: boolean;
}

function startOfDay(date: Date): Date {
  const copy = new Date(date);
  copy.setHours(0, 0, 0, 0);
  return copy;
}

function sameDay(a: Date, b: Date): boolean {
  return startOfDay(a).getTime() === startOfDay(b).getTime();
}

/** The section a lead belongs to today, or null when there is nothing to do. */
export function todayTask(lead: Lead, now = new Date()): TodayTask | null {
  const workflow = lead.workflow || {};
  if (workflow.stage === 'closed' || ['converted', 'lost'].includes(String(lead.status))) return null;
  const followUpAt = workflow.follow_up_at ? new Date(workflow.follow_up_at) : null;
  const base = { lead, followUpAt, assignmentLate: false };
  if (workflow.stage === 'verification_required') return { ...base, section: 'verification' };
  if (followUpAt) {
    if (followUpAt < startOfDay(now)) return { ...base, section: 'overdue' };
    if (sameDay(followUpAt, now)) return { ...base, section: 'due_today' };
    return null; // a follow-up planned for a later day
  }
  if (workflow.latest_contact_at) return null; // contacted, nothing planned
  if (workflow.ready_to_contact) {
    const due = lead.assignment_due_at ? new Date(lead.assignment_due_at) : null;
    return { ...base, section: 'first_contact', assignmentLate: Boolean(due && due <= now) };
  }
  return { ...base, section: 'verification' };
}

const priority = (task: TodayTask) => Number(task.lead.sales_priority_score || 0);
const time = (task: TodayTask) => task.followUpAt?.getTime() ?? 0;

/** Overdue and today's follow-ups by time (oldest first); the rest by priority. */
export function compareTasks(a: TodayTask, b: TodayTask): number {
  if (a.section === 'overdue' || a.section === 'due_today') return time(a) - time(b) || priority(b) - priority(a);
  if (a.assignmentLate !== b.assignmentLate) return a.assignmentLate ? -1 : 1;
  return priority(b) - priority(a) || a.lead.name.localeCompare(b.lead.name, 'tr');
}

export function groupTasks(leads: Lead[], now = new Date()): Record<TodaySection, TodayTask[]> {
  const groups: Record<TodaySection, TodayTask[]> = { overdue: [], due_today: [], first_contact: [], verification: [] };
  leads.forEach(lead => {
    const task = todayTask(lead, now);
    if (task) groups[task.section].push(task);
  });
  (Object.keys(groups) as TodaySection[]).forEach(key => groups[key].sort(compareTasks));
  return groups;
}

/** Leads with a contact result recorded today, latest first. */
export function contactedToday(leads: Lead[], now = new Date()): Lead[] {
  return leads
    .filter(lead => lead.workflow?.latest_contact_at && sameDay(new Date(lead.workflow.latest_contact_at), now))
    .sort((a, b) => String(b.workflow?.latest_contact_at).localeCompare(String(a.workflow?.latest_contact_at)));
}

/** "2 gün gecikti", "dün", for an overdue follow-up. */
export function lateness(followUpAt: Date, now = new Date()): string {
  const days = Math.round((startOfDay(now).getTime() - startOfDay(followUpAt).getTime()) / 86400000);
  return days <= 1 ? 'Dünden kaldı' : `${days} gün gecikti`;
}
