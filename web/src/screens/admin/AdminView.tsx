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
}

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

  const overview = useQuery({
    queryKey: ['admin-search', user.email],
    enabled: isAdmin,
    queryFn: ({ signal }) => apiRequest<{ jobs?: Job[]; token_summary?: TokenSummary }>('/api/admin_search', { signal }),
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
    return <ErrorState eyebrow="YETKİ" title="Tarama merkezi" message="Tarama ve analiz bütçesi yalnız yöneticilere açık." />;
  }

  const jobs = overview.data?.jobs || [];
  const tokens = overview.data?.token_summary || {};
  const cost = estimate.data;

  function createJob(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFeedback('');
    apiRequest<{ job: { id: number }; estimate: Estimate }>('/api/admin_search', {
      method: 'POST',
      body: { query, city, max_results: Number(maxResults), deep_research: deepResearch, ai_mode: aiMode },
    })
      .then(data => {
        setFeedback(`Tarama #${data.job.id} kuyruğa alındı. Tahmini ${count(data.estimate.estimated_tokens)} token.`);
        return queryClient.invalidateQueries({ queryKey: ['admin-search'] });
      })
      .catch((err: Error) => setFeedback(err.message))
      .finally(() => setBusy(false));
  }

  return (
    <div className={styles.root}>
      <PageHeader
        eyebrow="TARAMA"
        title="Tarama merkezi"
        subtitle="Yeni işletme taraması, analiz bütçesi ve iş kuyruğu."
        actions={<div className={styles.userChip}>{user.name || user.email}</div>}
      />

      <div className={styles.grid}>
        <form className={styles.panel} onSubmit={createJob} aria-labelledby="new-search-title">
          <div className={styles.eyebrow}>YENİ TARAMA</div>
          <h2 id="new-search-title" className={styles.title}>Yeni tarama başlat</h2>
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
                    <option value="smart">Otomatik seçim</option>
                    <option value="flash">Ekonomik analiz</option>
                    <option value="pro">Derin analiz</option>
                  </Select>
                )}
              </Field>
            </div>
            <label className={styles.check}>
              <input type="checkbox" checked={deepResearch} onChange={event => setDeepResearch(event.target.checked)} />
              <span>Website ve sosyal hesapları da araştır</span>
            </label>
            <div className={styles.estimate} aria-live="polite">
              <div><strong>{cost ? count(cost.estimated_tokens) : '—'}</strong> tahmini token</div>
              <div><strong>{cost ? (cost.priced ? usd(cost.estimated_cost_usd) : 'Fiyat yok') : '—'}</strong> tahmini maliyet</div>
            </div>
            {feedback && <div className={styles.feedback} role="status">{feedback}</div>}
            <Button type="submit" variant="primary" size="lg" block busy={busy} busyLabel="Kuyruğa alınıyor…" disabled={!query.trim() || !city.trim()}>Taramayı kuyruğa al</Button>
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
            {overview.isError && <div className={styles.feedback} role="alert">{overview.error.message}</div>}
            <ul className={styles.jobs}>
              {jobs.length === 0 && <li className={styles.muted}>{overview.isPending ? 'Yükleniyor…' : 'Henüz tarama yok.'}</li>}
              {jobs.map(job => (
                <li key={job.id} className={styles.job}>
                  <div>
                    <div className={styles.jobTitle}>#{job.id} {job.query} · {job.city}</div>
                    <div className={styles.muted}>{job.max_results} lead · {job.ai_mode} · {count(job.estimated_tokens)} token</div>
                  </div>
                  <span className={styles.jobStatus}>{job.status}</span>
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
