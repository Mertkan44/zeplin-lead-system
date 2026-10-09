// The signed-in shell: top bar, data banners, the screen the URL names, and the
// dialogs opened over it. Screens read CRM data from CrmContext.
import { useEffect, useMemo, useState } from 'react';

import { refreshWorkspace, setLeadStatus } from '../data/mutations';
import { buildCrm, CrmContext, useSession, useTeamUsers, useWorkspaceQuery } from '../data/workspace';
import type { Lead, LeadStatus } from '../data/types';
import { navigate, routeFor, useRoute, type View } from '../lib/router';
import { Banner, Button, EmptyState, ErrorState, LoadingState } from '../ui';
import { AdminView } from '../screens/admin/AdminView';
import { AnalyticsView } from '../screens/analytics/AnalyticsView';
import { ContactResultDialog } from '../screens/contact/ContactResultDialog';
import { LeadDetailView } from '../screens/lead/LeadDetailView';
import { LeadListView } from '../screens/leads/LeadListView';
import { PipelineView } from '../screens/pipeline/PipelineView';
import { ProfileView } from '../screens/profile/ProfileView';
import { ServicesView } from '../screens/services/ServicesView';
import { TodayView } from '../screens/today/TodayView';
import { WorkspaceView } from '../screens/workspace/WorkspaceView';
import { SearchDialog } from './SearchDialog';
import type { Theme } from './theme';
import { Topbar } from './Topbar';
import styles from './Dashboard.module.css';

export interface DashboardProps {
  theme: Theme;
  onToggleTheme: () => void;
}

export function Dashboard({ theme, onToggleTheme }: DashboardProps) {
  const { user, requestLogout } = useSession();
  const route = useRoute();
  const homeView: View = user.role === 'sales' ? 'today' : 'cockpit';
  const view = route.kind === 'lead' ? 'detail' : route.kind === 'view' ? route.view : homeView;

  const workspace = useWorkspaceQuery(user.email);
  const team = useTeamUsers(user);
  const crm = useMemo(() => (workspace.data ? buildCrm(workspace.data) : null), [workspace.data]);

  const [searchOpen, setSearchOpen] = useState(false);
  const [resultLeadName, setResultLeadName] = useState<string | null>(null);
  const [actionError, setActionError] = useState('');

  useEffect(() => {
    if (route.kind === 'unknown') navigate('/', { replace: true });
  }, [route.kind]);

  const leads = crm?.leads || [];
  const selectedIdx = route.kind === 'lead' ? leads.findIndex(item => Number(item.lead_id) === route.leadId) : -1;
  const resultLead = resultLeadName ? leads.find(item => item.name === resultLeadName) : undefined;

  function setView(next: View) {
    navigate(next === homeView ? '/' : routeFor({ view: next }));
  }

  function openLead(lead: Lead | undefined, options?: { replace?: boolean }) {
    if (lead && lead.lead_id != null) navigate(routeFor({ leadId: lead.lead_id }), options);
  }

  function changeStatus(name: string, status: LeadStatus) {
    setActionError('');
    setLeadStatus(name, status)
      .then(refreshWorkspace)
      .catch((err: Error) => setActionError(err.message));
  }

  function renderContent() {
    if (workspace.isPending) return <LoadingState label="Workspace yükleniyor." />;
    if (!crm) {
      return (
        <ErrorState
          eyebrow="BAĞLANTI"
          title="Veri alınamadı"
          message={workspace.error?.message || 'Sunucuya ulaşılamadı.'}
          onRetry={() => void workspace.refetch()}
          retrying={workspace.isFetching}
        />
      );
    }
    if (view === 'profile') {
      return <ProfileView user={user} users={team.data || [user]} summary={crm.summary} assignments={crm.assignments} onLogout={requestLogout} />;
    }
    if (view === 'admin') return <AdminView user={user} />;
    if (!leads.length) {
      return (
        <div className={styles.center}>
          <EmptyState title={user.role === 'sales' ? 'Sana atanmış aktif lead yok.' : 'Lead verisi bulunamadı.'}>
            {user.role === 'sales' ? 'Yöneticin sana lead atadığında burada görünecek.' : 'Yeni lead için Admin ekranından tarama başlat.'}
          </EmptyState>
        </div>
      );
    }
    switch (view) {
      case 'today':
        return <TodayView leads={leads} summary={crm.summary} user={user} onOpenResult={lead => setResultLeadName(lead.name)} />;
      case 'detail': {
        const lead = leads[selectedIdx];
        if (!lead) {
          return (
            <ErrorState
              eyebrow="LEAD"
              title="Lead bulunamadı"
              message="Bu lead silinmiş, birleştirilmiş ya da artık sana atanmamış olabilir."
              action={<Button variant="primary" size="lg" block onClick={() => setView(homeView)}>Ana ekrana dön</Button>}
            />
          );
        }
        return (
          // A new lead gets a fresh detail screen: no open panel carries over.
          <LeadDetailView
            key={lead.lead_id ?? lead.name}
            lead={lead}
            index={selectedIdx}
            total={leads.length}
            status={crm.statuses[lead.name] || 'yeni'}
            homePath="/"
            placesEnabled={Boolean(crm.integrations.google_places)}
            onStatusChange={status => changeStatus(lead.name, status)}
            onOpenResult={() => setResultLeadName(lead.name)}
            onPrev={() => openLead(leads[Math.max(0, selectedIdx - 1)], { replace: true })}
            onNext={() => openLead(leads[Math.min(leads.length - 1, selectedIdx + 1)], { replace: true })}
          />
        );
      }
      case 'pipeline':
        return <PipelineView leads={leads} />;
      case 'hizmetler':
        return <ServicesView leads={crm.rows} />;
      case 'raporlar':
        return <LeadListView leads={leads} />;
      case 'analytics':
        return <AnalyticsView leads={leads} />;
      default:
        return (
          <WorkspaceView
            leads={leads}
            user={user}
            summary={crm.summary}
            teamUsers={team.data || []}
            teamPerformance={crm.teamPerformance}
          />
        );
    }
  }

  const schema = crm?.schema;
  return (
    <CrmContext.Provider value={crm}>
      <div className={styles.root}>
        <Topbar
          view={view}
          homeView={homeView}
          user={user}
          leadCount={crm?.rows.length || 0}
          theme={theme}
          onToggleTheme={onToggleTheme}
          onOpenSearch={() => setSearchOpen(true)}
        />
        {schema && !schema.ready && (
          <Banner urgent>
            Veritabanı şeması bu sürümle uyumlu değil (kurulu: {schema.version || 'bilinmiyor'}, gereken: {schema.required_version}).
            {schema.failed_checks?.length ? ` Eksik: ${schema.failed_checks.join(', ')}.` : ''} Eksik migration'ları README'deki sırayla uygula.
          </Banner>
        )}
        {crm && workspace.isError && (
          <Banner actionLabel="Tekrar dene" onAction={() => void workspace.refetch()} actionBusy={workspace.isFetching}>
            Veriler güncellenemedi; son alınan veriler gösteriliyor. ({workspace.error.message})
          </Banner>
        )}
        {actionError && (
          <Banner tone="danger" urgent actionLabel="Kapat" onAction={() => setActionError('')}>{actionError}</Banner>
        )}
        <div className={styles.content}>{renderContent()}</div>
        {searchOpen && crm && <SearchDialog leads={leads} statuses={crm.statuses} onClose={() => setSearchOpen(false)} />}
        {resultLead && (
          <ContactResultDialog
            lead={resultLead}
            onClose={() => setResultLeadName(null)}
            onOpenLead={() => openLead(resultLead)}
            onSaved={() => {
              setResultLeadName(null);
              void refreshWorkspace();
            }}
            onRefreshLead={refreshWorkspace}
          />
        )}
      </div>
    </CrmContext.Provider>
  );
}
