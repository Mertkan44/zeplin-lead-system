// Dashboard screens still on legacy inline styles, moved unchanged from the
// runtime-compiled template. Data comes from the query cache (data/), rules
// from domain/; each screen moves to a typed module with CSS, then leaves
// this file (WP09 stage 2).
import * as React from 'react';

import { fetchAdminJSON } from '../lib/api';
import { GRADE_COLORS, PIPE_STAGES, SERVICES as services, roleLabel } from '../domain/catalog';
import { fmt, initialsFor } from '../domain/format';
import { canonicalSector, computeReadinessBuckets, computeTabCounts, getPipelineStage, getPrimaryActionMeta } from '../domain/lead';
import { startLeadAction, triggerQuickLeadAction } from '../data/leadActions';
import { addOutreach, setLeadStatus } from '../data/mutations';
import { useCrm } from '../data/workspace';

function roleTone(role) {
  return role === 'admin'
    ? { bg: 'var(--accent)', fg: 'var(--accent-ink)', bd: 'transparent' }
    : { bg: 'var(--raised)', fg: 'var(--sub)', bd: 'var(--line)' };
}

// Shared bits of the old lead-detail styles the remaining screens still use.
const ld = {
  btnGhost:    { padding: '8px 14px', background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 8, fontSize: 12.5, color: 'var(--sub)', cursor: 'pointer' },
  eyebrow:     { fontSize: 11, fontFamily: "'Space Grotesk'", textTransform: 'uppercase', letterSpacing: 1.2, color: 'var(--muted)' },
  cardTitle:   { fontFamily: "'Space Grotesk'", fontSize: 20, fontWeight: 600, letterSpacing: -0.4, marginTop: 6, color: 'var(--tx)' },
};

// ── Pipeline View ──────────────────────────────────────────────────────────

function PipelineView({ leads, onSelect, onDataChange }) {
  const crm = useCrm();
  const [tick, setTick] = React.useState(0);
  const [busyLead, setBusyLead] = React.useState('');
  const dragRef = React.useRef('');

  function refresh() { setTick(t => t + 1); }

  const byStage = {};
  PIPE_STAGES.forEach(s => { byStage[s.key] = []; });
  leads.forEach(l => { const stage = getPipelineStage(crm.statuses[l.name] || 'yeni', crm.eventsFor(l.name)); (byStage[stage] = byStage[stage] || []).push(l); });

  const won = byStage['won'].length;
  const active = ['draft','contacted','meeting'].reduce((a, k) => a + (byStage[k]||[]).length, 0);

  function runCardAction(lead, event) {
    event.stopPropagation();
    setBusyLead(lead.name);
    startLeadAction(lead)
      .finally(() => {
        setBusyLead('');
        if (onDataChange) onDataChange();
        refresh();
      });
  }

  function handleDrop(e, stageKey) {
    e.preventDefault();
    e.currentTarget.classList.remove('drag-over');
    const name = dragRef.current;
    if (!name) return;
    const stageObj = PIPE_STAGES.find(s => s.key === stageKey);
    if (!stageObj) return;
    let operation;
    if (stageObj.actions.length) {
      operation = addOutreach(name, stageObj.actions[0], new Date().toISOString().slice(0,16), '');
    } else if (stageKey === 'new') {
      operation = setLeadStatus(name, 'yeni');
    } else if (stageKey === 'contacted') {
      operation = setLeadStatus(name, 'contacted');
    } else if (stageKey === 'won') {
      operation = addOutreach(name, 'deal_won', new Date().toISOString().slice(0,16), '');
    } else if (stageKey === 'lost') {
      operation = addOutreach(name, 'deal_lost', new Date().toISOString().slice(0,16), '');
    }
    dragRef.current = '';
    Promise.resolve(operation).then(() => {
      if (onDataChange) onDataChange();
      refresh();
    }).catch(err => console.error('Pipeline update failed:', err));
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, background: 'var(--bg)' }}>
      <div style={pv.header}>
        <div>
          <div style={pv.pageEyebrow}>PIPELINE</div>
          <h1 style={pv.pageTitle}>Satış kanalı</h1>
          <p style={pv.pageSub}>{leads.length} lead · {won} kazanıldı · {active} aktif temasta</p>
        </div>
      </div>
      <div className="responsive-pipeline" style={pv.board}>
        {PIPE_STAGES.map(stage => {
          const cards = byStage[stage.key] || [];
          return (
            <div
              key={stage.key}
              style={pv.col}
              className="pipe-col"
              onDragOver={e => { e.preventDefault(); e.currentTarget.classList.add('drag-over'); }}
              onDragLeave={e => e.currentTarget.classList.remove('drag-over')}
              onDrop={e => handleDrop(e, stage.key)}
            >
              <div style={pv.colHead}>
                <span style={{ ...pv.colDot, background: stage.color }}/>
                <span style={pv.colTitle}>{stage.label}</span>
                <span style={pv.colCnt}>{cards.length}</span>
              </div>
              <div style={pv.cards}>
                {cards.map(l => {
                  const globalIdx = leads.indexOf(l);
                  const val = l.estimated_value_tl || 0;
                  return (
                    <div
                      key={l.name}
                      style={pv.card}
                      className="pipe-card"
                      draggable
                      onDragStart={e => { dragRef.current = l.name; e.currentTarget.classList.add('dragging'); }}
                      onDragEnd={e => e.currentTarget.classList.remove('dragging')}
                      onClick={() => onSelect(globalIdx)}
                    >
                      <div style={pv.cardName}>{l.name}</div>
                      <div style={pv.cardActionLabel}>{getPrimaryActionMeta(l).label}</div>
                      <div style={pv.cardMeta}>
                        <span style={{ ...pv.cardScore, background: stage.color + '22', color: stage.color }}>{l.scoring.grade} {l.scoring.score}</span>
                        {val > 0 && <span style={pv.cardVal}>~{fmt(val)} ₺</span>}
                      </div>
                      <div style={pv.cardActions}>
                        <button
                          style={{ ...pv.cardBtn, ...(busyLead === l.name ? pv.cardBtnMuted : null) }}
                          onClick={e => runCardAction(l, e)}
                          disabled={busyLead === l.name}
                        >
                          {busyLead === l.name ? 'Kaydediliyor…' : getPrimaryActionMeta(l).label}
                        </button>
                        <button style={pv.cardBtnGhost} onClick={e => { e.stopPropagation(); triggerQuickLeadAction(l); }}>
                          Hızlı aç
                        </button>
                      </div>
                    </div>
                  );
                })}
                {cards.length === 0 && <div style={pv.empty}>Buraya sürükle</div>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

const pv = {
  header:      { padding: '26px 32px 20px', borderBottom: '1px solid var(--line)', background: 'var(--bg)' },
  pageEyebrow: { fontSize: 11, fontFamily: "'Space Grotesk'", textTransform: 'uppercase', letterSpacing: 1.2, color: 'var(--muted)', marginBottom: 8 },
  pageTitle:   { fontFamily: "'Space Grotesk'", fontSize: 34, fontWeight: 600, letterSpacing: -1.2, margin: 0, color: 'var(--tx)' },
  pageSub:     { fontSize: 13, color: 'var(--sub)', marginTop: 6, fontFamily: "'Space Grotesk'" },
  board:       { display: 'flex', gap: 14, padding: '24px 32px 40px', overflowX: 'auto', alignItems: 'flex-start', flex: 1 },
  col:         { minWidth: 220, flex: '0 0 220px', background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 'var(--rs)', padding: 14, display: 'flex', flexDirection: 'column', gap: 0 },
  colHead:     { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 },
  colDot:      { width: 8, height: 8, borderRadius: 99, flexShrink: 0 },
  colTitle:    { fontSize: 12.5, fontWeight: 600, flex: 1, color: 'var(--tx)' },
  colCnt:      { fontSize: 11, fontFamily: "'Space Grotesk'", background: 'var(--raised)', padding: '2px 7px', borderRadius: 99, color: 'var(--sub)' },
  cards:       { display: 'flex', flexDirection: 'column', gap: 10 },
  card:        { background: 'var(--raised)', border: '1px solid var(--line)', borderRadius: 14, padding: '14px', cursor: 'pointer' },
  cardName:    { fontSize: 13, fontWeight: 600, lineHeight: 1.3, marginBottom: 8, color: 'var(--tx)' },
  cardActionLabel:{ fontSize: 10.5, color: 'var(--muted)', fontFamily: "'Space Grotesk'", textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 8 },
  cardMeta:    { display: 'flex', gap: 6, flexWrap: 'wrap' },
  cardActions: { display: 'flex', gap: 6, marginTop: 10, flexWrap: 'wrap' },
  cardBtn:     { flex: 1, minHeight: 32, padding: '7px 10px', borderRadius: 8, border: 'none', background: 'var(--accent)', color: 'var(--accent-ink)', fontSize: 11.5, fontWeight: 600, cursor: 'pointer' },
  cardBtnMuted:{ opacity: 0.72, cursor: 'progress' },
  cardBtnGhost:{ minHeight: 32, padding: '7px 10px', borderRadius: 8, border: '1px solid var(--line)', background: 'var(--panel2)', color: 'var(--sub)', fontSize: 11.5, fontWeight: 500, cursor: 'pointer' },
  cardScore:   { fontSize: 11, fontFamily: "'Space Grotesk'", fontWeight: 700, padding: '2px 8px', borderRadius: 6 },
  cardVal:     { fontSize: 11, color: 'var(--accent)', fontFamily: "'Space Grotesk'" },
  empty:       { fontSize: 12, color: 'var(--muted)', textAlign: 'center', padding: '20px 0', border: '1.5px dashed var(--line2)', borderRadius: 10 },
};

// ── Hizmetler View ─────────────────────────────────────────────────────────

function HizmetlerView({ leads }) {
  const svcMap = {};
  leads.forEach(l => {
    (l.matched_services || []).forEach(svc => {
      if (!svcMap[svc.slug]) svcMap[svc.slug] = { svc, matches: [] };
      svcMap[svc.slug].matches.push({ lead: l, match: svc });
    });
  });

  const entries = services.map(svc => {
    const active = svcMap[svc.slug] || { matches: [] };
    const confirmed = active.matches.filter(item => item.match.match_type === 'confirmed_gap');
    const conditional = active.matches.filter(item => item.match.match_type === 'conditional_gap');
    const opportunities = active.matches.filter(item => item.match.match_type === 'qualified_opportunity');
    return { svc, matches: active.matches, confirmed, conditional, opportunities };
  }).sort((a, b) => b.matches.length - a.matches.length);

  const serviceTypeLabel = type => ({
    monthly: 'Aylık',
    project: 'Proje',
    project_or_monthly: 'Proje / Aylık',
  }[type] || 'Kapsamlanacak');

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, background: 'var(--bg)' }}>
      <div style={pv.header}>
        <div>
          <div style={pv.pageEyebrow}>HİZMETLER</div>
          <h1 style={pv.pageTitle}>Zeplin Media Hizmetleri</h1>
          <p style={pv.pageSub}>{entries.length} onaylı hizmet · {entries.reduce((a,e)=>a+e.matches.length,0)} ölçülebilir hizmet sinyali · Kesin açık ve görüşme fırsatı ayrı gösterilir</p>
        </div>
      </div>
      <div style={hv.grid}>
        {entries.map(({ svc, matches, confirmed, conditional, opportunities }) => (
          <div key={svc.slug} style={hv.card}>
            <div style={hv.cardTop}>
              <span style={{ ...hv.badge, background: svc.monthly ? 'rgba(124,197,255,0.14)' : 'rgba(197,242,74,0.12)', color: svc.monthly ? '#7cc5ff' : 'var(--accent)' }}>
                {serviceTypeLabel(svc.service_type)}
              </span>
              <span style={{ ...hv.badge, background: 'var(--raised)', color: 'var(--sub)' }}>{svc.category || 'Genel'}</span>
            </div>
            <div style={hv.cardName}>{svc.name}</div>
            {svc.desc && <div style={hv.cardDesc}>{svc.desc}</div>}
            {svc.detects && <div style={hv.detects}><strong style={{ color: 'var(--sub)' }}>Bot tespit eder:</strong> {svc.detects}</div>}
            <div style={hv.cardStats}>
              <div><div style={hv.statVal}>{matches.length}</div><div style={hv.statLbl}>Toplam Sinyal</div></div>
              <div><div style={{ ...hv.statVal, color: 'var(--accent)' }}>{confirmed.length}</div><div style={hv.statLbl}>Kesin Açık</div></div>
              <div><div style={{ ...hv.statVal, color: '#ffcf4a' }}>{conditional.length + opportunities.length}</div><div style={hv.statLbl}>Görüşmede Doğrula</div></div>
            </div>
            <div style={hv.price}>Fiyat ve kapsam görüşme sonrasında yönetim onayıyla belirlenir.</div>
          </div>
        ))}
      </div>
    </div>
  );
}

const hv = {
  grid:     { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 14, padding: '24px 32px 40px' },
  card:     { background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 'var(--rs)', padding: 20, display: 'flex', flexDirection: 'column', gap: 10 },
  cardTop:  { display: 'flex', gap: 6 },
  badge:    { fontSize: 10.5, fontFamily: "'Space Grotesk'", fontWeight: 600, padding: '3px 9px', borderRadius: 99 },
  cardName: { fontFamily: "'Space Grotesk'", fontSize: 17, fontWeight: 600, letterSpacing: -0.3, marginTop: 4, color: 'var(--tx)' },
  cardDesc: { fontSize: 12.5, color: 'var(--sub)', lineHeight: 1.45 },
  detects:  { fontSize: 12, color: 'var(--sub)', background: 'var(--panel2)', padding: '8px 12px', borderRadius: 8, lineHeight: 1.4 },
  cardStats:{ display: 'flex', gap: 24, paddingTop: 10, borderTop: '1px solid var(--line)', marginTop: 4 },
  statVal:  { fontFamily: "'Space Grotesk'", fontSize: 20, fontWeight: 700, letterSpacing: -0.5, color: 'var(--tx)' },
  statLbl:  { fontSize: 11, color: 'var(--muted)', fontFamily: "'Space Grotesk'", marginTop: 2 },
  price:    { fontFamily: "'Space Grotesk'", fontSize: 15, fontWeight: 600, color: 'var(--tx)', marginTop: 4 },
};

function AdminView({ user }) {
  const [query, setQuery] = React.useState('restoran');
  const [city, setCity] = React.useState('Istanbul Kadıköy');
  const [maxResults, setMaxResults] = React.useState(10);
  const [deepResearch, setDeepResearch] = React.useState(true);
  const [aiMode, setAiMode] = React.useState('smart');
  const [jobs, setJobs] = React.useState([]);
  const [tokens, setTokens] = React.useState(null);
  const [feedback, setFeedback] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const isAdmin = user?.role === 'admin';

  const [estimate, setEstimate] = React.useState(null);

  // The estimate comes from the API: the same figure the job will reserve.
  React.useEffect(() => {
    if (!isAdmin) return undefined;
    let cancelled = false;
    const params = new URLSearchParams({ estimate: '1', max_results: String(maxResults || 1), deep_research: deepResearch ? '1' : '0', ai_mode: aiMode });
    const timer = setTimeout(() => {
      fetchAdminJSON(`/api/admin_search?${params}`)
        .then(data => { if (!cancelled) setEstimate(data.estimate || null); })
        .catch(() => { if (!cancelled) setEstimate(null); });
    }, 250);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [isAdmin, maxResults, deepResearch, aiMode]);
  const usd = value => `$${Number(value || 0).toFixed(4)}`;

  function refreshAdmin() {
    return fetchAdminJSON('/api/admin_search')
      .then(data => {
        setJobs(data.jobs || []);
        setTokens(data.token_summary || null);
      })
      .catch(err => setFeedback(err.message));
  }

  React.useEffect(() => {
    if (isAdmin) refreshAdmin();
  }, [isAdmin]);

  function createJob(e) {
    e.preventDefault();
    setBusy(true);
    setFeedback('');
    fetchAdminJSON('/api/admin_search', {
      method: 'POST',
      body: JSON.stringify({
        query,
        city,
        max_results: Number(maxResults),
        deep_research: deepResearch,
        ai_mode: aiMode,
      }),
    })
      .then(data => {
        setFeedback(`Search job #${data.job.id} kuyruğa alındı. Tahmini ${data.estimate.estimated_tokens.toLocaleString('tr-TR')} token.`);
        return refreshAdmin();
      })
      .catch(err => setFeedback(err.message))
      .finally(() => setBusy(false));
  }

  if (!isAdmin) {
    return (
      <div style={av.root}>
        <div style={av.loginCard}>
          <div style={pv.pageEyebrow}>YETKİ</div>
          <h1 style={pv.pageTitle}>Admin alanı</h1>
          <p style={av.text}>Yeni search ve token bütçesi sadece patron hesaplarında açık.</p>
        </div>
      </div>
    );
  }

  return (
    <div style={av.root}>
      <div style={{ ...pv.header, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={pv.pageEyebrow}>ADMIN</div>
          <h1 style={pv.pageTitle}>Search operasyonu</h1>
          <p style={pv.pageSub}>Yeni lead taraması, DeepSeek bütçesi ve Supabase job kuyruğu.</p>
        </div>
        <div style={av.userChip}>{user?.name || user?.email}</div>
      </div>

      <div className="responsive-admin" style={av.grid}>
        <form style={av.panel} onSubmit={createJob}>
          <div style={ld.eyebrow}>YENİ SEARCH</div>
          <div style={ld.cardTitle}>Admin tarama başlat</div>
          <label style={av.label}>Arama tipi</label>
          <input value={query} onChange={e => setQuery(e.target.value)} style={av.input} placeholder="restoran, mağaza, kuaför" />
          <label style={av.label}>Bölge</label>
          <input value={city} onChange={e => setCity(e.target.value)} style={av.input} placeholder="Istanbul Kadıköy" />
          <div style={av.row}>
            <div style={{ flex: 1 }}>
              <label style={av.label}>Sonuç</label>
              <input type="number" min="1" max="30" value={maxResults} onChange={e => setMaxResults(e.target.value)} style={av.input} />
            </div>
            <div style={{ flex: 1 }}>
              <label style={av.label}>AI modu</label>
              <select value={aiMode} onChange={e => setAiMode(e.target.value)} style={av.input}>
                <option value="smart">Smart</option>
                <option value="flash">Flash</option>
                <option value="pro">Pro</option>
              </select>
            </div>
          </div>
          <label style={av.checkRow}>
            <input type="checkbox" checked={deepResearch} onChange={e => setDeepResearch(e.target.checked)} />
            <span>Deep research açık</span>
          </label>
          <div style={av.estimate}>
            <div><strong>{estimate ? Number(estimate.estimated_tokens).toLocaleString('tr-TR') : '—'}</strong><span> tahmini token</span></div>
            <div><strong>{estimate ? (estimate.priced ? usd(estimate.estimated_cost_usd) : 'Fiyat yok') : '—'}</strong><span> tahmini maliyet</span></div>
          </div>
          {feedback && <div style={av.feedback}>{feedback}</div>}
          <button style={av.primaryBtn} disabled={busy || !query.trim() || !city.trim()}>{busy ? 'Kuyruğa alınıyor…' : 'Search job oluştur'}</button>
        </form>

        <div style={av.sideStack}>
          <div style={av.panel}>
            <div style={ld.eyebrow}>TOKEN</div>
            <div style={ld.cardTitle}>AI kullanımı</div>
            <div style={av.metricRow}><span>Gerçek harcama (tüm zamanlar)</span><strong>{usd(tokens?.actual_cost_usd)}</strong></div>
            <div style={av.metricRow}><span>Bugün</span><strong>{usd(tokens?.today_cost_usd)}</strong></div>
            <div style={av.metricRow}><span>Gerçek token</span><strong>{Number(tokens?.actual_tokens || 0).toLocaleString('tr-TR')}</strong></div>
            <div style={av.metricRow}><span>Açık rezervasyon</span><strong>{usd(tokens?.active_reserved_usd)}</strong></div>
            <div style={av.metricRow}><span>Sağlayıcı çağrısı · önbellekten</span><strong>{Number(tokens?.provider_calls || 0)} · {Number(tokens?.cache_hits || 0)}</strong></div>
            {(Number(tokens?.failed_calls || 0) > 0 || Number(tokens?.unpriced_calls || 0) > 0) && (
              <div style={av.metricRow}><span>Başarısız · fiyatsız çağrı</span><strong>{Number(tokens?.failed_calls || 0)} · {Number(tokens?.unpriced_calls || 0)}</strong></div>
            )}
          </div>

          <div style={av.panel}>
            <div style={ld.eyebrow}>SON İŞLER</div>
            <div style={ld.cardTitle}>Search kuyruğu</div>
            <div style={av.jobs}>
              {jobs.length === 0 && <div style={av.muted}>Henüz job yok.</div>}
              {jobs.map(job => (
                <div key={job.id} style={av.jobRow}>
                  <div>
                    <div style={av.jobTitle}>#{job.id} {job.query} · {job.city}</div>
                    <div style={av.muted}>{job.max_results} lead · {job.ai_mode} · {Number(job.estimated_tokens || 0).toLocaleString('tr-TR')} token</div>
                  </div>
                  <span style={av.jobStatus}>{job.status}</span>
                </div>
              ))}
            </div>
            <button style={ld.btnGhost} onClick={refreshAdmin}>Yenile</button>
          </div>
        </div>
      </div>
    </div>
  );
}

const av = {
  root:      { flex: 1, minWidth: 0, background: 'var(--bg)', fontFamily: "'Instrument Sans', system-ui, sans-serif", color: 'var(--tx)' },
  empty:     { padding: 40, color: 'var(--sub)' },
  grid:      { display: 'grid', gridTemplateColumns: '1.1fr 0.9fr', gap: 18, padding: '24px 32px 40px' },
  sideStack: { display: 'flex', flexDirection: 'column', gap: 18 },
  panel:     { background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 'var(--rs)', padding: 22 },
  loginCard: { width: 420, margin: '80px auto', background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 'var(--rs)', padding: 24 },
  text:      { fontSize: 13, color: 'var(--sub)', lineHeight: 1.5, margin: '12px 0 18px' },
  label:     { display: 'block', fontSize: 11, color: 'var(--muted)', fontFamily: "'Space Grotesk'", textTransform: 'uppercase', letterSpacing: 1, margin: '16px 0 6px' },
  input:     { width: '100%', padding: '10px 12px', border: '1px solid var(--line)', borderRadius: 9, background: 'var(--panel2)', color: 'var(--tx)', outline: 'none', fontSize: 13 },
  row:       { display: 'flex', gap: 10 },
  checkRow:  { display: 'flex', alignItems: 'center', gap: 8, marginTop: 16, fontSize: 13, color: 'var(--sub)' },
  estimate:  { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginTop: 16 },
  feedback:  { marginTop: 14, padding: '10px 12px', borderRadius: 9, background: 'var(--raised)', color: 'var(--sub)', fontSize: 12.5 },
  primaryBtn:{ width: '100%', marginTop: 16, padding: '11px 14px', borderRadius: 9, border: 'none', background: 'var(--accent)', color: 'var(--accent-ink)', fontWeight: 600, cursor: 'pointer' },
  metricRow: { display: 'flex', justifyContent: 'space-between', padding: '12px 0', borderBottom: '1px solid var(--line)', fontSize: 13 },
  jobs:      { display: 'flex', flexDirection: 'column', gap: 8, margin: '14px 0' },
  jobRow:    { display: 'flex', justifyContent: 'space-between', gap: 12, padding: 12, border: '1px solid var(--line)', borderRadius: 10, background: 'var(--panel2)' },
  jobTitle:  { fontSize: 13, fontWeight: 600, color: 'var(--tx)' },
  jobStatus: { alignSelf: 'flex-start', padding: '4px 8px', borderRadius: 99, background: 'var(--accent)', color: 'var(--accent-ink)', fontSize: 10.5, fontFamily: "'Space Grotesk'" },
  muted:     { fontSize: 11.5, color: 'var(--muted)', marginTop: 4 },
  userChip:  { border: '1px solid var(--line)', background: 'var(--panel)', color: 'var(--sub)', borderRadius: 999, padding: '9px 14px', fontSize: 12.5, fontWeight: 600 },
};

// ── Analytics (Raporlar) View ──────────────────────────────────────────────

function bar(pct, color) { return { width: `${pct}%`, height: '100%', borderRadius: 99, background: color }; }

function AnalyticsView({ leads, statuses }) {
  const [periodDays, setPeriodDays] = React.useState('all');
  const cutoff = periodDays === 'all' ? null : Date.now() - periodDays * 86400000;
  const periodLeads = leads.filter(lead => {
    if (cutoff === null) return true;
    if (!lead.last_analyzed) return false;
    const stamp = new Date(lead.last_analyzed.replace(' ', 'T')).getTime();
    return !Number.isNaN(stamp) && stamp >= cutoff;
  });
  const actualTotal = periodLeads.length;
  const total = actualTotal || 1;

  const GRADE_COLORS = { A: '#b6f24a', B: '#ffcf4a', C: '#ff8f4a', D: '#7a7a78' };
  const gradeCounts = { A: 0, B: 0, C: 0, D: 0 };
  periodLeads.forEach(l => { const g = l.scoring?.grade; if (gradeCounts[g] !== undefined) gradeCounts[g] += 1; });
  const gradeMax = Math.max(...Object.values(gradeCounts), 1);
  const gradeBars = ['A','B','C','D'].map(g => ({ g, n: gradeCounts[g], c: GRADE_COLORS[g], pct: (gradeCounts[g]/gradeMax*100) }));

  const counts = computeTabCounts(periodLeads, statuses);
  const funnelSteps = [
    { label: 'Toplam', n: actualTotal, bg: 'var(--raised)', tx: 'var(--tx)' },
    { label: 'Yeni', n: counts.yeni, bg: 'var(--panel2)', tx: 'var(--tx)' },
    { label: 'Temasta', n: counts.contacted, bg: 'rgba(124,197,255,0.16)', tx: '#7cc5ff' },
    { label: 'Kazanıldı', n: counts.converted, bg: 'var(--accent)', tx: 'var(--accent-ink)' },
  ];

  const avgScore = Math.round(periodLeads.reduce((a, l) => a + (l.scoring?.score || 0), 0) / total);
  const gaugeCirc = 389.6;
  const gaugeOffset = gaugeCirc * (1 - Math.min(avgScore, 100) / 100);

  const now = new Date();
  const weekBuckets = new Array(8).fill(0);
  periodLeads.forEach(l => {
    if (!l.last_analyzed) return;
    const d = new Date(l.last_analyzed.replace(' ', 'T'));
    if (isNaN(d)) return;
    const diffDays = Math.floor((now - d) / 86400000);
    const weekIdx = Math.floor(diffDays / 7);
    if (weekIdx >= 0 && weekIdx < 8) weekBuckets[7 - weekIdx] += 1;
  });
  const weekMax = Math.max(...weekBuckets, 1);
  const weekly = weekBuckets.map((n, i) => ({ n, label: i === 7 ? 'Bu hafta' : `-${7-i}h`, pct: (n/weekMax*100) }));
  const weeklyTotal = weekBuckets.reduce((a, b) => a + b, 0);

  const sectorMap = {};
  periodLeads.forEach(l => {
    const s = canonicalSector(l);
    sectorMap[s] = (sectorMap[s] || 0) + 1;
  });
  const sectors = Object.entries(sectorMap).sort((a, b) => b[1] - a[1]).slice(0, 5)
    .map(([s, n], i) => ({ s, pct: Math.round(n/total*100), c: ['#b6f24a','#ffcf4a','#ff8f4a','#7cc5ff','#a78bfa'][i] || 'var(--sub)' }));

  const readiness = computeReadinessBuckets(periodLeads);

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, background: 'var(--bg)' }}>
      <div style={{ ...pv.header, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
        <div>
          <div style={pv.pageEyebrow}>{periodDays === 'all' ? 'PERFORMANS · TÜM ZAMANLAR' : `PERFORMANS · SON ${periodDays} GÜN`}</div>
          <h1 style={pv.pageTitle}>Raporlar</h1>
        </div>
        <div style={{ display: 'flex', gap: 4, background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 999, padding: 5 }}>
          {[7, 30, 90, 'all'].map(days => (
            <button key={days} onClick={() => setPeriodDays(days)} style={{ padding: '8px 16px', borderRadius: 999, border: 'none', cursor: 'pointer', background: periodDays === days ? 'var(--selected-bg)' : 'transparent', color: periodDays === days ? 'var(--selected-tx)' : 'var(--sub)', fontSize: 12.5, fontWeight: periodDays === days ? 600 : 500 }}>
              {days === 'all' ? 'Tümü' : days === 90 ? 'Çeyrek' : `${days}g`}
            </button>
          ))}
        </div>
      </div>

      <div className="responsive-report" style={rp.grid}>
        <div style={rp.card}>
          <div style={rp.cardTitle}>Not Dağılımı</div>
          <div style={rp.cardSub}>{actualTotal} lead sınıflandırıldı</div>
          <div style={rp.stack}>
            {gradeBars.map(g => (
              <div key={g.g}>
                <div style={rp.rowHead}><span style={{ fontWeight: 600, color: g.c }}>Sınıf {g.g}</span><span style={rp.num}>{g.n}</span></div>
                <div style={rp.barTrack}><div style={bar(g.pct, g.c)}/></div>
              </div>
            ))}
          </div>
        </div>

        <div style={rp.card}>
          <div style={rp.cardTitle}>Dönüşüm Hunisi</div>
          <div style={rp.cardSub}>Yeni → Müşteri · %{Math.round(counts.converted/total*100)}</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {funnelSteps.map(s => (
              <div key={s.label} style={{ width: `${40 + (s.n/total*60)}%`, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px', borderRadius: 12, background: s.bg }}>
                <span style={{ fontSize: 12.5, fontWeight: 600, color: s.tx }}>{s.label}</span>
                <span style={{ ...rp.num, fontSize: 14, fontWeight: 700, color: s.tx }}>{s.n}</span>
              </div>
            ))}
          </div>
        </div>

        <div style={{ ...rp.card, alignItems: 'center', justifyContent: 'center', display: 'flex', flexDirection: 'column' }}>
          <div style={{ ...rp.cardTitle, alignSelf: 'flex-start' }}>Ortalama Skor</div>
          <div style={{ ...rp.cardSub, alignSelf: 'flex-start' }}>tüm aktif leadler</div>
          <div style={{ position: 'relative', width: 150, height: 150, margin: '14px 0 6px' }}>
            <svg width="150" height="150" viewBox="0 0 150 150" style={{ transform: 'rotate(-90deg)' }}>
              <circle cx="75" cy="75" r="62" fill="none" stroke="var(--line2)" strokeWidth="11"/>
              <circle cx="75" cy="75" r="62" fill="none" stroke="var(--accent)" strokeWidth="11" strokeLinecap="round" strokeDasharray={gaugeCirc} strokeDashoffset={gaugeOffset} style={{ transition: 'stroke-dashoffset .9s cubic-bezier(.22,1,.36,1)' }}/>
            </svg>
            <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
              <span style={{ fontFamily: "'Space Grotesk'", fontSize: 44, fontWeight: 700, lineHeight: 1, color: 'var(--tx)' }}>{avgScore}</span>
              <span style={{ fontSize: 11, color: 'var(--muted)' }}>/ 100</span>
            </div>
          </div>
        </div>

        <div style={{ ...rp.card, gridColumn: 'span 2' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 18 }}>
            <div>
              <div style={rp.cardTitle}>Haftalık Yeni Lead</div>
              <div style={rp.cardSub}>tarama hacmi · 8 hafta</div>
            </div>
            <div style={{ fontFamily: "'Space Grotesk'", fontSize: 26, fontWeight: 700, color: 'var(--tx)' }}>{weeklyTotal}<span style={{ fontSize: 13, color: 'var(--muted)', fontWeight: 500 }}> toplam</span></div>
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 12, height: 150 }}>
            {weekly.map((w, i) => (
              <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, height: '100%', justifyContent: 'flex-end' }}>
                <span style={{ ...rp.num, fontSize: 11, color: 'var(--sub)' }}>{w.n}</span>
                <div style={{ width: '70%', minWidth: 14, height: `${Math.max(w.pct, 4)}%`, borderRadius: 6, background: 'linear-gradient(180deg, var(--accent), rgba(197,242,74,0.35))' }}/>
                <span style={{ fontSize: 10.5, color: 'var(--muted)' }}>{w.label}</span>
              </div>
            ))}
          </div>
        </div>

        <div style={rp.card}>
          <div style={rp.cardTitle}>Sektör Dağılımı</div>
          <div style={rp.cardSub}>seçili dönemdeki {actualTotal} lead · benzer kategoriler birleştirildi</div>
          <div style={rp.stack}>
            {sectors.map(s => (
              <div key={s.s}>
                <div style={rp.rowHead}><span>{s.s}</span><span style={rp.num}>{s.pct}%</span></div>
                <div style={{ ...rp.barTrack, height: 7 }}><div style={bar(s.pct, s.c)}/></div>
              </div>
            ))}
          </div>
        </div>

        <div style={{ ...rp.card, gridColumn: 'span 3', flexDirection: 'row', gap: 14, alignItems: 'stretch' }}>
          {[
            { label: 'Hazır arama', val: readiness.readyToCall, sub: 'telefon bilgisi tamam' },
            { label: 'Veri tamamlama', val: readiness.needsData, sub: 'telefon / adres eksik' },
            { label: 'Temasa hazır', val: readiness.proposalReady, sub: 'kanıt + hizmet + onaylı taslak' },
          ].map(r => (
            <div key={r.label} style={{ flex: 1, background: 'var(--raised)', borderRadius: 14, padding: '16px 18px' }}>
              <div style={{ fontFamily: "'Space Grotesk'", fontSize: 28, fontWeight: 700, color: 'var(--tx)' }}>{r.val}</div>
              <div style={{ fontSize: 12.5, fontWeight: 600, marginTop: 4, color: 'var(--tx)' }}>{r.label}</div>
              <div style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 2 }}>{r.sub}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

const rp = {
  grid:     { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14, padding: '24px 32px 40px' },
  card:     { background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 'var(--r)', padding: 22, display: 'flex', flexDirection: 'column' },
  cardTitle:{ fontSize: 13, fontWeight: 600, marginBottom: 4, color: 'var(--tx)' },
  cardSub:  { fontSize: 11.5, color: 'var(--muted)', marginBottom: 18 },
  stack:    { display: 'flex', flexDirection: 'column', gap: 14 },
  rowHead:  { display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 6 },
  num:      { fontFamily: "'Space Grotesk'", color: 'var(--sub)' },
  barTrack: { height: 9, background: 'var(--raised)', borderRadius: 99, overflow: 'hidden' },
};

// ── Profile View ──────────────────────────────────────────────────────────

function ProfileView({ user, users, summary, assignments, onLogout }) {
  const list = React.useMemo(() => {
    const byEmail = new Map();
    (users || []).forEach(item => {
      if (item?.email) byEmail.set(item.email, item);
    });
    if (user?.email && !byEmail.has(user.email)) byEmail.set(user.email, user);
    return [...byEmail.values()].sort((a, b) => {
      const ar = a.role === 'admin' ? 0 : 1;
      const br = b.role === 'admin' ? 0 : 1;
      if (ar !== br) return ar - br;
      return String(a.name || a.email).localeCompare(String(b.name || b.email), 'tr');
    });
  }, [users, user]);

  const assignmentCounts = React.useMemo(() => {
    const counts = {};
    (assignments || []).forEach(item => {
      if (item.status !== 'active') return;
      counts[item.user_email] = (counts[item.user_email] || 0) + 1;
    });
    return counts;
  }, [assignments]);

  const currentEmail = user?.email;
  const current = list.find(item => item.email === currentEmail) || user || {};
  const currentCount = user?.role === 'admin'
    ? (summary?.assigned_count ?? Object.values(assignmentCounts).reduce((a, b) => a + b, 0))
    : (summary?.assigned_count ?? assignmentCounts[currentEmail] ?? 0);
  const activeMembers = list.filter(item => item.active !== false).length;
  const bossCount = list.filter(item => item.role === 'admin').length;
  const salesCount = list.filter(item => item.role === 'sales').length;

  return (
    <div style={pf.root}>
      <div style={{ ...pv.header, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 18 }}>
        <div>
          <div style={pv.pageEyebrow}>PROFİL</div>
          <h1 style={pv.pageTitle}>Ekip ve hesap</h1>
          <p style={pv.pageSub}>Aktif oturum, ekip rolleri ve profil fotoğrafları.</p>
        </div>
        <button style={ld.btnGhost} onClick={onLogout}>Çıkış yap</button>
      </div>

      <div style={pf.hero}>
        <div style={pf.heroPhotoWrap}>
          {current.avatar_url ? <img src={current.avatar_url} alt={current.name || current.email || 'Profil'} style={pf.heroPhoto}/> : <div style={pf.heroInitial}>{initialsFor(current.name || current.email)}</div>}
        </div>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={pf.heroEyebrow}>Şu an bu hesaptasın</div>
          <div style={pf.heroName}>{current.name || current.email}</div>
          <div style={pf.heroMeta}>
            <span>{current.email}</span>
            <span>·</span>
            <span>{current.title || roleLabel(current.role)}</span>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 16 }}>
            <ProfilePill role={current.role}/>
            <span style={pf.softPill}>{current.active === false ? 'Pasif' : 'Aktif hesap'}</span>
            <span style={pf.softPill}>{currentCount} atanmış lead</span>
          </div>
        </div>
        <div style={pf.heroStats}>
          <div style={pf.statBox}><span>{list.length}</span><small>Toplam kişi</small></div>
          <div style={pf.statBox}><span>{activeMembers}</span><small>Aktif</small></div>
          <div style={pf.statBox}><span>{bossCount}</span><small>Patron</small></div>
          <div style={pf.statBox}><span>{salesCount}</span><small>Çalışan</small></div>
        </div>
      </div>

      <div style={pf.sectionHead}>
        <div>
          <div style={ld.eyebrow}>EKİP</div>
          <div style={pf.sectionTitle}>Zeplin kullanıcıları</div>
        </div>
        <div style={pf.sectionHint}>Fotoğraflar canlı profilden geliyor.</div>
      </div>

      <div style={pf.teamGrid}>
        {list.map(member => {
          const isMe = member.email === currentEmail;
          const count = assignmentCounts[member.email] || 0;
          return (
            <div key={member.email} style={{ ...pf.memberCard, ...(isMe ? pf.memberCardActive : null) }}>
              <div style={pf.memberPhotoWrap}>
                {member.avatar_url ? <img src={member.avatar_url} alt={member.name || member.email} style={pf.memberPhoto}/> : <div style={pf.memberInitial}>{initialsFor(member.name || member.email)}</div>}
                {isMe && <span style={pf.meBadge}>Bu hesap</span>}
              </div>
              <div style={pf.memberBody}>
                <div style={pf.memberName}>{member.name || member.email}</div>
                <div style={pf.memberEmail}>{member.email}</div>
                <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap', marginTop: 12 }}>
                  <ProfilePill role={member.role}/>
                  <span style={pf.softPill}>{member.title || roleLabel(member.role)}</span>
                  <span style={member.active === false ? pf.passivePill : pf.softPill}>{member.active === false ? 'Pasif' : 'Aktif'}</span>
                </div>
              </div>
              <div style={pf.memberFooter}>
                <span>Atanmış lead</span>
                <strong>{user?.role === 'admin' || isMe ? count : '—'}</strong>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ProfilePill({ role }) {
  const tone = roleTone(role);
  return <span style={{ ...pf.rolePill, background: tone.bg, color: tone.fg, borderColor: tone.bd }}>{roleLabel(role)}</span>;
}

const pf = {
  root:           { flex: 1, minWidth: 0, background: 'var(--bg)', color: 'var(--tx)' },
  hero:           { margin: '24px 32px 0', padding: 24, border: '1px solid var(--line)', borderRadius: 24, background: 'linear-gradient(135deg, var(--panel), var(--panel2))', display: 'flex', flexWrap: 'wrap', gap: 22, alignItems: 'center' },
  heroPhotoWrap:  { width: 136, height: 136, borderRadius: 24, overflow: 'hidden', border: '1px solid var(--line)', background: 'var(--raised)', boxShadow: '0 20px 44px rgba(0,0,0,0.12)' },
  heroPhoto:      { width: '100%', height: '100%', objectFit: 'cover', display: 'block' },
  heroInitial:    { width: '100%', height: '100%', display: 'grid', placeItems: 'center', fontFamily: "'Space Grotesk'", fontSize: 34, fontWeight: 700, color: 'var(--accent-ink)', background: 'var(--accent)' },
  heroEyebrow:    { fontFamily: "'Space Grotesk'", fontSize: 11, color: 'var(--muted)', letterSpacing: 1.4, textTransform: 'uppercase', marginBottom: 8 },
  heroName:       { fontFamily: "'Space Grotesk'", fontSize: 42, lineHeight: 1, fontWeight: 700, letterSpacing: '-0.04em', color: 'var(--tx)' },
  heroMeta:       { marginTop: 10, display: 'flex', gap: 8, flexWrap: 'wrap', color: 'var(--sub)', fontSize: 13.5 },
  heroStats:      { display: 'grid', gridTemplateColumns: 'repeat(2, minmax(110px, 1fr))', gap: 10, flex: '1 1 260px', maxWidth: 380 },
  statBox:        { background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 16, padding: 15, minHeight: 82, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' },
  sectionHead:    { margin: '28px 32px 12px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: 12, flexWrap: 'wrap' },
  sectionTitle:   { fontFamily: "'Space Grotesk'", fontSize: 24, fontWeight: 700, letterSpacing: '-0.03em' },
  sectionHint:    { fontSize: 12.5, color: 'var(--muted)' },
  teamGrid:       { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14, padding: '0 32px 40px' },
  memberCard:     { background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 22, overflow: 'hidden', display: 'flex', flexDirection: 'column', minWidth: 0 },
  memberCardActive:{ borderColor: 'rgba(197,242,74,0.65)', boxShadow: '0 16px 38px rgba(197,242,74,0.12)' },
  memberPhotoWrap:{ position: 'relative', aspectRatio: '1 / 1', background: 'var(--raised)', overflow: 'hidden' },
  memberPhoto:    { width: '100%', height: '100%', objectFit: 'cover', display: 'block' },
  memberInitial:  { width: '100%', height: '100%', display: 'grid', placeItems: 'center', fontFamily: "'Space Grotesk'", fontSize: 28, fontWeight: 700, color: 'var(--accent-ink)', background: 'var(--accent)' },
  meBadge:        { position: 'absolute', top: 12, left: 12, background: 'var(--accent)', color: 'var(--accent-ink)', borderRadius: 999, padding: '6px 10px', fontSize: 11, fontWeight: 700 },
  memberBody:     { padding: 16, minHeight: 126 },
  memberName:     { fontFamily: "'Space Grotesk'", fontSize: 18, fontWeight: 700, letterSpacing: '-0.02em', color: 'var(--tx)' },
  memberEmail:    { marginTop: 4, fontSize: 12.5, color: 'var(--muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' },
  memberFooter:   { marginTop: 'auto', padding: '12px 16px', borderTop: '1px solid var(--line)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'var(--sub)', fontSize: 12.5 },
  rolePill:       { border: '1px solid', borderRadius: 999, padding: '5px 9px', fontSize: 11.5, fontWeight: 700 },
  softPill:       { border: '1px solid var(--line)', background: 'var(--raised)', color: 'var(--sub)', borderRadius: 999, padding: '5px 9px', fontSize: 11.5, fontWeight: 600 },
  passivePill:    { border: '1px solid rgba(255,107,107,0.25)', background: 'rgba(255,107,107,0.1)', color: '#ff8f8f', borderRadius: 999, padding: '5px 9px', fontSize: 11.5, fontWeight: 600 },
};



export {
  AdminView,
  AnalyticsView,
  HizmetlerView,
  PipelineView,
  ProfileView,
};
