// Admin: start a lead search job, see AI spending and the job queue.
// The cost estimate comes from the API: the same figure the job will reserve.
import { useEffect, useState, type FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';

import type { User } from '../../data/types';
import { apiRequest } from '../../lib/api';
import { queryClient } from '../../lib/queryClient';
import { Button, ErrorState, Field, Input, Select } from '../../ui';
import { PageHeader } from '../shared/PageHeader';
import styles from './AdminView.module.css';

interface Estimate {
  estimated_tokens?: number;
  estimated_cost_usd?: number;
  priced?: boolean;
}

interface Job {
  id: number;
  query: string;
  city: string;
  max_results: number;
  ai_mode: string;
  estimated_tokens?: number;
  status: string;
  created_at?: string;
  heartbeat_at?: string;
  lease_until?: string;
  next_attempt_at?: string;
  attempt_count?: number;
  max_attempts?: number;
  progress_stage?: string;
  progress_done?: number;
  progress_total?: number;
  last_error?: { stage?: string; code?: string; message?: string };
  result?: { ai_usage?: { ledger_errors?: number } };
}

interface WorkerSummary {
  queued?: number;
  retry_wait?: number;
  stalled?: number;
  oldest_queue_seconds?: number;
  failed_generations?: number;
  provider_errors_24h?: number;
}

const statusLabels: Record<string, string> = {
  queued: 'Sırada', running: 'Çalışıyor', retry_wait: 'Tekrar denenecek',
  success: 'Tamamlandı', partial_success: 'Kısmen tamamlandı', failed: 'Başarısız', cancelled: 'İptal edildi',
};
const stageLabels: Record<string, string> = {
  queued: 'Başlamadı', starting: 'Hazırlanıyor', scraped: 'İşletmeler bulundu', listed: 'İşletme incelemesi',
  audit: 'İşletme incelemesi', audited: 'İnceleme kaydedildi', research: 'Araştırma', researched: 'Araştırma kaydedildi',
  brief: 'Araştırma özeti', report: 'AI raporu', email: 'İletişim taslağı', sync: 'Sonuçları kaydetme',
  synced: 'Sonuç kaydedildi', complete: 'Tüm aşamalar tamamlandı', scrape: 'İşletme arama',
};
const dateTime = (value?: string) => value ? new Date(value).toLocaleString('tr-TR', { timeZone: 'Europe/Istanbul', dateStyle: 'short', timeStyle: 'short' }) : '—';

interface TokenSummary {
  actual_cost_usd?: number;
  today_cost_usd?: number;
  actual_tokens?: number;
  active_reserved_usd?: number;
  provider_calls?: number;
  cache_hits?: number;
  failed_calls?: number;
  unpriced_calls?: number;
}

const usd = (value: unknown) => `$${Number(value || 0).toFixed(4)}`;
const count = (value: unknown) => Number(value || 0).toLocaleString('tr-TR');

/** Waits until `value` has stopped changing for `ms`. */
function useDebounced<T>(value: T, ms: number): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return settled;
}

export function AdminView({ user }: { user: User }) {
  const isAdmin = user.role === 'admin';
  const [query, setQuery] = useState('restoran');
  const [city, setCity] = useState('Istanbul Kadıköy');
  const [maxResults, setMaxResults] = useState('10');
  const [deepResearch, setDeepResearch] = useState(true);
  const [aiMode, setAiMode] = useState('smart');
  const [feedback, setFeedback] = useState('');
  const [busy, setBusy] = useState(false);
  const [busyJob, setBusyJob] = useState<number | null>(null);

  const overview = useQuery({
    queryKey: ['admin-search', user.email],
    enabled: isAdmin,
    queryFn: ({ signal }) => apiRequest<{ jobs?: Job[]; token_summary?: TokenSummary; worker_summary?: WorkerSummary }>('/api/admin_search', { signal }),
    refetchInterval: query => query.state.data?.jobs?.some(job => ['queued', 'running', 'retry_wait'].includes(job.status)) ? 15000 : false,
  });
  const params = useDebounced(
    new URLSearchParams({ estimate: '1', max_results: String(maxResults || 1), deep_research: deepResearch ? '1' : '0', ai_mode: aiMode }).toString(),
    250,
  );
  const estimate = useQuery({
    queryKey: ['admin-estimate', user.email, params],
    enabled: isAdmin,
    queryFn: ({ signal }) => apiRequest<{ estimate?: Estimate }>(`/api/admin_search?${params}`, { signal }).then(data => data.estimate || null),
  });

  if (!isAdmin) {
    return <ErrorState eyebrow="YETKİ" title="Admin alanı" message="Yeni search ve token bütçesi sadece patron hesaplarında açık." />;
  }

  const jobs = overview.data?.jobs || [];
  const tokens = overview.data?.token_summary || {};
  const cost = estimate.data;
  const worker = overview.data?.worker_summary;

  function createJob(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFeedback('');
    apiRequest<{ job: { id: number }; estimate: Estimate }>('/api/admin_search', {
      method: 'POST',
      body: { query, city, max_results: Number(maxResults), deep_research: deepResearch, ai_mode: aiMode },
    })
      .then(data => {
        setFeedback(`Search job #${data.job.id} kuyruğa alındı. Tahmini ${count(data.estimate.estimated_tokens)} token.`);
        return queryClient.invalidateQueries({ queryKey: ['admin-search'] });
      })
      .catch((err: Error) => setFeedback(err.message))
      .finally(() => setBusy(false));
  }

  async function controlJob(job: Job, action: 'cancel' | 'retry') {
    setBusyJob(job.id);
    setFeedback('');
    try {
      await apiRequest('/api/admin_search', { method: 'POST', body: { job_id: job.id, action } });
      setFeedback(`#${job.id} ${action === 'cancel' ? 'iptal edildi' : 'yeniden deneme kuyruğuna alındı'}.`);
      await overview.refetch();
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : 'İşlem kaydedilemedi.');
    } finally {
      setBusyJob(null);
    }
  }

  return (
    <div className={styles.root}>
      <PageHeader
        eyebrow="ADMIN"
        title="Search operasyonu"
        subtitle="Yeni lead taraması, DeepSeek bütçesi ve Supabase job kuyruğu."
        actions={<div className={styles.userChip}>{user.name || user.email}</div>}
      />

      <div className={styles.grid}>
        <form className={styles.panel} onSubmit={createJob} aria-labelledby="new-search-title">
          <div className={styles.eyebrow}>YENİ SEARCH</div>
          <h2 id="new-search-title" className={styles.title}>Admin tarama başlat</h2>
          <div className={styles.form}>
            <Field label="Arama tipi">
              {control => <Input {...control} value={query} onChange={event => setQuery(event.target.value)} placeholder="restoran, mağaza, kuaför" />}
            </Field>
            <Field label="Bölge">
              {control => <Input {...control} value={city} onChange={event => setCity(event.target.value)} placeholder="Istanbul Kadıköy" />}
            </Field>
            <div className={styles.row}>
              <Field label="Sonuç">
                {control => <Input {...control} type="number" min="1" max="30" value={maxResults} onChange={event => setMaxResults(event.target.value)} />}
              </Field>
              <Field label="AI modu">
                {control => (
                  <Select {...control} value={aiMode} onChange={event => setAiMode(event.target.value)}>
                    <option value="smart">Smart</option>
                    <option value="flash">Flash</option>
                    <option value="pro">Pro</option>
                  </Select>
                )}
              </Field>
            </div>
            <label className={styles.check}>
              <input type="checkbox" checked={deepResearch} onChange={event => setDeepResearch(event.target.checked)} />
              <span>Deep research açık</span>
            </label>
            <div className={styles.estimate} aria-live="polite">
              <div><strong>{cost ? count(cost.estimated_tokens) : '—'}</strong> tahmini token</div>
              <div><strong>{cost ? (cost.priced ? usd(cost.estimated_cost_usd) : 'Fiyat yok') : '—'}</strong> tahmini maliyet</div>
            </div>
            {feedback && <div className={styles.feedback} role="status">{feedback}</div>}
            <Button type="submit" variant="primary" size="lg" block busy={busy} busyLabel="Kuyruğa alınıyor…" disabled={!query.trim() || !city.trim()}>Search job oluştur</Button>
          </div>
        </form>

        <div className={styles.side}>
          <section className={styles.panel} aria-labelledby="tokens-title">
            <div className={styles.eyebrow}>TOKEN</div>
            <h2 id="tokens-title" className={styles.title}>AI kullanımı</h2>
            <dl className={styles.metrics}>
              <div className={styles.metric}><dt>Gerçek harcama (tüm zamanlar)</dt><dd>{usd(tokens.actual_cost_usd)}</dd></div>
              <div className={styles.metric}><dt>Bugün</dt><dd>{usd(tokens.today_cost_usd)}</dd></div>
              <div className={styles.metric}><dt>Gerçek token</dt><dd>{count(tokens.actual_tokens)}</dd></div>
              <div className={styles.metric}><dt>Açık rezervasyon</dt><dd>{usd(tokens.active_reserved_usd)}</dd></div>
              <div className={styles.metric}><dt>Sağlayıcı çağrısı · önbellekten</dt><dd>{Number(tokens.provider_calls || 0)} · {Number(tokens.cache_hits || 0)}</dd></div>
              {(Number(tokens.failed_calls || 0) > 0 || Number(tokens.unpriced_calls || 0) > 0) && (
                <div className={styles.metric}><dt>Başarısız · fiyatsız çağrı</dt><dd>{Number(tokens.failed_calls || 0)} · {Number(tokens.unpriced_calls || 0)}</dd></div>
              )}
            </dl>
          </section>

          <section className={styles.panel} aria-labelledby="jobs-title">
            <div className={styles.eyebrow}>SON İŞLER</div>
            <h2 id="jobs-title" className={styles.title}>Tarama kuyruğu</h2>
            <p className={styles.muted}>İşler yaklaşık 15 dakikada bir alınır. En fazla üç deneme yapılır; tamamlanan aşamalar korunur.</p>
            {worker && <p className={styles.muted}>
              Sırada {worker.queued ?? 0} · Tekrar denenecek {worker.retry_wait ?? 0} · Yanıt vermeyen {worker.stalled ?? 0}<br />
              En eski bekleme: {Math.floor((worker.oldest_queue_seconds ?? 0) / 60)} dk · Son 24 saat sağlayıcı hatası: {worker.provider_errors_24h ?? 0} · Başarısız AI üretimi: {worker.failed_generations ?? 0}
            </p>}
            {overview.isError && <div className={styles.feedback} role="alert">{overview.error.message}</div>}
            <ul className={styles.jobs}>
              {jobs.length === 0 && <li className={styles.muted}>{overview.isPending ? 'Yükleniyor…' : 'Henüz job yok.'}</li>}
              {jobs.map(job => (
                <li key={job.id} className={styles.job}>
                  <div>
                    <div className={styles.jobTitle}>#{job.id} {job.query} · {job.city}</div>
                    <div className={styles.muted}>{job.max_results} lead · {job.ai_mode} · {count(job.estimated_tokens)} token</div>
                    <div className={styles.muted}>
                      {stageLabels[job.progress_stage || 'queued'] || job.progress_stage} · {job.progress_done ?? 0}/{job.progress_total || job.max_results} işletme tamamlandı<br />
                      Deneme {job.attempt_count ?? 0}/{job.max_attempts ?? 3} · Oluşturulma: {dateTime(job.created_at)}
                    </div>
                    {job.status === 'running' && <p className={styles.muted}>
                      Son yaşam sinyali: {dateTime(job.heartbeat_at)}
                      {job.lease_until && Date.parse(job.lease_until) <= Date.now() && ' · İşçi yanıt vermiyor; sıradaki çalışmada kurtarılacak.'}
                    </p>}
                    {job.status === 'retry_wait' && <p className={styles.muted}>En erken yeniden deneme: {dateTime(job.next_attempt_at)}</p>}
                    {job.last_error && <p className={styles.jobError}>
                      {stageLabels[job.last_error.stage || ''] || 'Tarama'}: {job.last_error.code || 'Hata'}.
                      {['failed', 'partial_success'].includes(job.status) ? ' Deneme sınırı doldu. Kaydedilen sonuçları inceleyin.' : ' Tamamlanan aşamalar korunarak yeniden denenecek.'}
                    </p>}
                    {(job.result?.ai_usage?.ledger_errors ?? 0) > 0 && <p className={styles.jobError}>Bazı AI maliyet kayıtları yazılamadı. Tarama sonuçları korundu.</p>}
                    {['queued', 'running', 'retry_wait'].includes(job.status) && <Button size="sm" disabled={busyJob !== null} onClick={() => void controlJob(job, 'cancel')} aria-label={`Tarama #${job.id} iptal et`}>İptal et</Button>}
                    {['failed', 'partial_success'].includes(job.status) && (job.attempt_count ?? 0) < (job.max_attempts ?? 3) && <Button size="sm" disabled={busyJob !== null} onClick={() => void controlJob(job, 'retry')} aria-label={`Tarama #${job.id} yeniden dene`}>Yeniden dene</Button>}
                  </div>
                  <span className={styles.jobStatus} data-status={job.status}>{statusLabels[job.status] || job.status}</span>
                </li>
              ))}
            </ul>
            <Button busy={overview.isFetching} busyLabel="Yenileniyor…" onClick={() => void overview.refetch()}>Yenile</Button>
          </section>
        </div>
      </div>
    </div>
  );
}
