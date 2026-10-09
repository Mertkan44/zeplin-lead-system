// The signed-in account, the team and the logout button.
import { useMemo } from 'react';

import type { Assignment, User, WorkspaceSummary } from '../../data/types';
import { roleLabel } from '../../domain/catalog';
import { initialsFor } from '../../domain/format';
import { Button } from '../../ui';
import { PageHeader } from '../shared/PageHeader';
import styles from './ProfileView.module.css';

function RolePill({ role }: { role?: string | null }) {
  return <span className={role === 'admin' ? `${styles.pill} ${styles.pillAdmin}` : styles.pill}>{roleLabel(role)}</span>;
}

function Avatar({ user }: { user: User }) {
  return user.avatar_url
    ? <img src={user.avatar_url} alt={user.name || user.email} className={styles.photo} />
    : <div className={styles.initials} aria-hidden="true">{initialsFor(user.name || user.email)}</div>;
}

export interface ProfileViewProps {
  user: User;
  users: User[];
  summary: WorkspaceSummary | null;
  assignments: Assignment[];
  onLogout: () => void;
}

export function ProfileView({ user, users, summary, assignments, onLogout }: ProfileViewProps) {
  // Admins first, then by name; the signed-in user is always listed.
  const team = useMemo(() => {
    const byEmail = new Map<string, User>();
    users.forEach(item => { if (item?.email) byEmail.set(item.email, item); });
    if (!byEmail.has(user.email)) byEmail.set(user.email, user);
    return [...byEmail.values()].sort((a, b) => {
      const rank = (member: User) => (member.role === 'admin' ? 0 : 1);
      if (rank(a) !== rank(b)) return rank(a) - rank(b);
      return String(a.name || a.email).localeCompare(String(b.name || b.email), 'tr');
    });
  }, [users, user]);

  const assignmentCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    assignments.forEach(item => {
      if (item.status === 'active') counts[item.user_email] = (counts[item.user_email] || 0) + 1;
    });
    return counts;
  }, [assignments]);

  const isAdmin = user.role === 'admin';
  const current = team.find(item => item.email === user.email) || user;
  const currentCount = summary?.assigned_count
    ?? (isAdmin ? Object.values(assignmentCounts).reduce((sum, value) => sum + value, 0) : assignmentCounts[user.email] ?? 0);

  return (
    <div className={styles.root}>
      <PageHeader
        eyebrow="PROFİL"
        title="Ekip ve hesap"
        subtitle="Aktif oturum, ekip rolleri ve profil fotoğrafları."
        actions={<Button onClick={onLogout}>Çıkış yap</Button>}
      />

      <section className={styles.hero} aria-label="Bu hesap">
        <div className={styles.heroPhoto}><Avatar user={current} /></div>
        <div className={styles.heroText}>
          <div className={styles.heroEyebrow}>Şu an bu hesaptasın</div>
          <div className={styles.heroName}>{current.name || current.email}</div>
          <div className={styles.heroMeta}>
            <span>{current.email}</span>
            <span aria-hidden="true">·</span>
            <span>{current.title || roleLabel(current.role)}</span>
          </div>
          <div className={styles.pills}>
            <RolePill role={current.role} />
            <span className={styles.pill}>{current.active === false ? 'Pasif' : 'Aktif hesap'}</span>
            <span className={styles.pill}>{currentCount} atanmış lead</span>
          </div>
        </div>
        <dl className={styles.heroStats}>
          <div className={styles.stat}><dt>Toplam kişi</dt><dd>{team.length}</dd></div>
          <div className={styles.stat}><dt>Aktif</dt><dd>{team.filter(item => item.active !== false).length}</dd></div>
          <div className={styles.stat}><dt>Patron</dt><dd>{team.filter(item => item.role === 'admin').length}</dd></div>
          <div className={styles.stat}><dt>Çalışan</dt><dd>{team.filter(item => item.role === 'sales').length}</dd></div>
        </dl>
      </section>

      <div className={styles.sectionHead}>
        <div>
          <div className={styles.eyebrow}>EKİP</div>
          <h2 className={styles.sectionTitle}>Zeplin kullanıcıları</h2>
        </div>
        <div className={styles.sectionHint}>Fotoğraflar canlı profilden geliyor.</div>
      </div>

      <ul className={styles.team}>
        {team.map(member => {
          const isMe = member.email === user.email;
          return (
            <li key={member.email} className={isMe ? `${styles.member} ${styles.memberMe}` : styles.member}>
              <div className={styles.memberPhoto}>
                <Avatar user={member} />
                {isMe && <span className={styles.meBadge}>Bu hesap</span>}
              </div>
              <div className={styles.memberBody}>
                <div className={styles.memberName}>{member.name || member.email}</div>
                <div className={styles.memberEmail} title={member.email}>{member.email}</div>
                <div className={styles.memberPills}>
                  <RolePill role={member.role} />
                  <span className={styles.pill}>{member.title || roleLabel(member.role)}</span>
                  <span className={member.active === false ? `${styles.pill} ${styles.pillPassive}` : styles.pill}>{member.active === false ? 'Pasif' : 'Aktif'}</span>
                </div>
              </div>
              <div className={styles.memberFooter}>
                <span>Atanmış lead</span>
                <strong>{isAdmin || isMe ? assignmentCounts[member.email] || 0 : '—'}</strong>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
