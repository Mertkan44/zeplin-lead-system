// The team's own check of the sources (Google Maps, Instagram, menu, website)
// and the Google Places refresh with its "which business is it?" choice.
import { useEffect, useState, type FormEvent } from 'react';

import { refreshWorkspace, saveManualVerification } from '../../data/mutations';
import type { Lead } from '../../data/types';
import { FACT_LABELS, FACT_SOURCES, PLACE_REASONS } from '../../domain/catalog';
import { fmtDate } from '../../domain/format';
import { manualVerificationDefaults } from '../../domain/lead';
import { apiRequest, ApiError } from '../../lib/api';
import { openExternal } from '../../lib/browser';
import styles from './LeadDetail.module.css';

type Values = ReturnType<typeof manualVerificationDefaults>;
type Group = 'google' | 'instagram' | 'menu' | 'website';

interface PlaceCandidate {
  place_id: string;
  display_name?: string;
  formatted_address?: string;
  phone?: string;
  maps_url?: string;
}

interface PlaceResult {
  status?: string;
  reason?: string;
  match_method?: string;
  match_confidence?: number;
  candidates?: PlaceCandidate[];
}

interface Fact {
  value?: unknown;
  status?: string;
  source?: string;
  observed_at?: string;
  stale?: boolean;
  conflicts?: Fact[];
}

const factValue = (fact: Fact) => (fact.status === 'absent' ? 'yok' : String(fact.value ?? '—'));

function SourceLink({ url, label }: { url?: string; label: string }) {
  if (!url) return null;
  return <button type="button" className={styles.link} onClick={() => openExternal(url)}>{label} ↗</button>;
}

export interface ManualVerificationCardProps {
  lead: Lead;
  placesEnabled: boolean;
  onFeedback: (message: string) => void;
}

export function ManualVerificationCard({ lead, placesEnabled, onFeedback }: ManualVerificationCardProps) {
  const [values, setValues] = useState<Values>(() => manualVerificationDefaults(lead));
  const [busy, setBusy] = useState(false);
  const [placesBusy, setPlacesBusy] = useState(false);
  const [placeChoice, setPlaceChoice] = useState<PlaceResult | null>(null);
  const current = lead.manual_verification || null;
  const storedAttempt: PlaceResult | undefined = lead.research?.google_places?.last_attempt;
  const choice = placeChoice || (storedAttempt?.status === 'ambiguous' ? storedAttempt : null);
  const candidates = placesEnabled ? choice?.candidates || [] : [];
  // Conflicts between sources, and team/Places data past its re-check date.
  const factIssues = (Object.entries(lead.facts || {}) as Array<[string, Fact]>)
    .filter(([, fact]) => (fact.conflicts || []).length || (fact.stale && fact.source !== 'scrape'));

  // A new team check arrived from the server: show it.
  useEffect(() => setValues(manualVerificationDefaults(lead)), [current?.checked_at]);

  function update<G extends Group>(group: G, field: keyof Values[G], value: unknown) {
    setValues(previous => ({ ...previous, [group]: { ...previous[group], [field]: value } }));
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!(['google', 'instagram', 'menu', 'website'] as Group[]).some(group => values[group].checked)) {
      onFeedback('Kaydetmek için en az bir alanı kontrol edildi olarak işaretle.');
      return;
    }
    setBusy(true);
    saveManualVerification(lead, values)
      .then(() => {
        onFeedback('Manuel kontrol kaydedildi; öneriler güncellendi.');
        return refreshWorkspace();
      })
      .catch(() => onFeedback('Manuel kontrol kaydedilemedi.'))
      .finally(() => setBusy(false));
  }

  /** Without a place id the server finds the business; with one, the user picked it. */
  function refreshGooglePlace(placeId?: string) {
    setPlacesBusy(true);
    apiRequest<{ place?: PlaceResult }>('/api/place_refresh', {
      method: 'POST',
      body: placeId ? { lead_name: lead.name, place_id: placeId } : { lead_name: lead.name },
    })
      .catch((err: unknown) => {
        throw new Error((err instanceof ApiError && typeof err.data.error === 'string' && err.data.error) || 'Google verisi yenilenemedi.');
      })
      .then(data => {
        const place = data.place || {};
        if (place.status === 'verified') {
          setPlaceChoice(null);
          onFeedback(place.match_method === 'text_search'
            ? `Google verisi yenilendi · %${place.match_confidence || 0} eşleşme güveni.`
            : 'Google verisi kayıtlı işletme üzerinden yenilendi.');
        } else if (place.status === 'ambiguous') {
          setPlaceChoice(place);
          onFeedback((place.reason && PLACE_REASONS[place.reason]) || 'Google sonucu belirsiz; doğru işletmeyi seç.');
        } else {
          setPlaceChoice(null);
          throw new Error((place.reason && PLACE_REASONS[place.reason]) || 'Google’da güvenilir işletme eşleşmesi bulunamadı; manuel kontrol et.');
        }
        return refreshWorkspace();
      })
      .catch((error: Error) => onFeedback(error.message || 'Google verisi yenilenemedi.'))
      .finally(() => setPlacesBusy(false));
  }

  const sectionClass = (checked: boolean) => (checked ? styles.manualSection : `${styles.manualSection} ${styles.manualSectionOff}`);

  return (
    <form className={styles.card} onSubmit={submit} aria-labelledby="manual-check-title">
      <div className={`${styles.cardHeader} ${styles.cardHeaderRow}`}>
        <div>
          <div className={styles.eyebrow}>EKİP DOĞRULAMASI</div>
          <h2 id="manual-check-title" className={styles.cardTitle}>Kaynakları aç, gördüğünü kaydet</h2>
        </div>
        <div className={styles.placeActions}>
          {placesEnabled && (
            <button type="button" className={styles.button} disabled={placesBusy} onClick={() => refreshGooglePlace()}>
              {placesBusy ? 'Google yenileniyor…' : 'Google verisini yenile'}
            </button>
          )}
          {current?.checked_at
            ? <span className={styles.badgeVerified}>{fmtDate(current.checked_at)} · {current.checked_by || 'Ekip'}</span>
            : <span className={styles.badgeCount}>Henüz yapılmadı</span>}
        </div>
      </div>

      {candidates.length > 0 && (
        <div className={styles.placeChoices}>
          <div className={styles.placeHint}>{(choice?.reason && PLACE_REASONS[choice.reason]) || 'Google sonucu belirsiz; doğru işletmeyi seç.'}</div>
          {candidates.map(candidate => (
            <div key={candidate.place_id} className={styles.placeChoice}>
              <div>
                <strong>{candidate.display_name || 'İsimsiz kayıt'}</strong>
                <div className={styles.placeMeta}>{[candidate.formatted_address, candidate.phone].filter(Boolean).join(' · ')}</div>
              </div>
              <div className={styles.placeActions}>
                <SourceLink url={candidate.maps_url} label="Maps" />
                <button type="button" className={styles.button} disabled={placesBusy} onClick={() => refreshGooglePlace(candidate.place_id)}>Bu işletme</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {factIssues.length > 0 && (
        <ul className={styles.factIssues}>
          {factIssues.map(([key, fact]) => (
            <li key={key}>
              <strong>{FACT_LABELS[key] || key}:</strong> {factValue(fact)}{' '}
              <span className={styles.factSource}>
                ({(fact.source && FACT_SOURCES[fact.source]) || fact.source}{fact.observed_at ? `, ${fmtDate(fact.observed_at)}` : ''}{fact.stale ? ', yeniden kontrol et' : ''})
              </span>
              {(fact.conflicts || []).map((other, index) => (
                <span key={index}> · {(other.source && FACT_SOURCES[other.source]) || other.source} farklı diyor: {factValue(other)}</span>
              ))}
            </li>
          ))}
        </ul>
      )}

      <div className={styles.manualGrid}>
        <fieldset className={sectionClass(values.google.checked)}>
          <div className={styles.manualHead}>
            <label className={styles.manualCheck}><input type="checkbox" checked={values.google.checked} onChange={event => update('google', 'checked', event.target.checked)} /><strong>Google Maps</strong></label>
            <SourceLink url={lead.maps_url} label="Maps aç" />
          </div>
          <select aria-label="Google profil durumu" className={styles.manualInput} disabled={!values.google.checked} value={values.google.status} onChange={event => update('google', 'status', event.target.value)}>
            <option value="found">Profil bulundu</option><option value="not_found">Profil bulunamadı</option><option value="unknown">Sonuç belirsiz</option>
          </select>
          <div className={styles.manualFields}>
            <input aria-label="Google puanı" className={styles.manualInput} disabled={!values.google.checked} type="number" min="0" max="5" step="0.1" placeholder="Puan (4.3)" value={values.google.rating} onChange={event => update('google', 'rating', event.target.value)} />
            <input aria-label="Google yorum sayısı" className={styles.manualInput} disabled={!values.google.checked} type="number" min="0" placeholder="Yorum sayısı" value={values.google.review_count} onChange={event => update('google', 'review_count', event.target.value)} />
          </div>
        </fieldset>

        <fieldset className={sectionClass(values.instagram.checked)}>
          <div className={styles.manualHead}>
            <label className={styles.manualCheck}><input type="checkbox" checked={values.instagram.checked} onChange={event => update('instagram', 'checked', event.target.checked)} /><strong>Instagram</strong></label>
            <SourceLink url={values.instagram.url || lead.social?.instagram_url} label="Instagram aç" />
          </div>
          <select aria-label="Instagram durumu" className={styles.manualInput} disabled={!values.instagram.checked} value={values.instagram.status} onChange={event => update('instagram', 'status', event.target.value)}>
            <option value="active">Aktif kullanılıyor</option><option value="inactive">Uzun süredir pasif</option><option value="not_found">Hesap bulunamadı</option><option value="unknown">Sonuç belirsiz</option>
          </select>
          <div className={styles.manualFields}>
            <input aria-label="Instagram takipçi sayısı" className={styles.manualInput} disabled={!values.instagram.checked} type="number" min="0" placeholder="Takipçi" value={values.instagram.followers} onChange={event => update('instagram', 'followers', event.target.value)} />
            <input aria-label="Instagram gönderi sayısı" className={styles.manualInput} disabled={!values.instagram.checked} type="number" min="0" placeholder="Gönderi" value={values.instagram.post_count} onChange={event => update('instagram', 'post_count', event.target.value)} />
          </div>
          <input aria-label="Instagram URL" className={styles.manualInput} disabled={!values.instagram.checked} placeholder="Instagram profil URL" value={values.instagram.url} onChange={event => update('instagram', 'url', event.target.value)} />
        </fieldset>

        <fieldset className={sectionClass(values.menu.checked)}>
          <div className={styles.manualHead}>
            <label className={styles.manualCheck}><input type="checkbox" checked={values.menu.checked} onChange={event => update('menu', 'checked', event.target.checked)} /><strong>Menü</strong></label>
            <SourceLink url={values.menu.url} label="Menüyü aç" />
          </div>
          <select aria-label="Menü durumu" className={styles.manualInput} disabled={!values.menu.checked} value={values.menu.status} onChange={event => update('menu', 'status', event.target.value)}>
            <option value="current">Güncel ve yeterli</option><option value="outdated">Eski / görseller yetersiz</option><option value="not_found">Dijital menü yok</option><option value="unknown">Sonuç belirsiz</option>
          </select>
          <input aria-label="Menü URL" className={styles.manualInput} disabled={!values.menu.checked} placeholder="Menü URL (varsa)" value={values.menu.url} onChange={event => update('menu', 'url', event.target.value)} />
        </fieldset>

        <fieldset className={sectionClass(values.website.checked)}>
          <div className={styles.manualHead}>
            <label className={styles.manualCheck}><input type="checkbox" checked={values.website.checked} onChange={event => update('website', 'checked', event.target.checked)} /><strong>Website</strong></label>
            <SourceLink url={values.website.url || lead.website?.website_url} label="Siteyi aç" />
          </div>
          <select aria-label="Website durumu" className={styles.manualInput} disabled={!values.website.checked} value={values.website.status} onChange={event => update('website', 'status', event.target.value)}>
            <option value="working">Çalışıyor ve güncel</option><option value="outdated">Eski / yetersiz</option><option value="not_found">Website yok</option><option value="unknown">Sonuç belirsiz</option>
          </select>
          <input aria-label="Website URL" className={styles.manualInput} disabled={!values.website.checked} placeholder="Website URL (varsa)" value={values.website.url} onChange={event => update('website', 'url', event.target.value)} />
        </fieldset>
      </div>

      <div className={styles.manualFooter}>
        <textarea aria-label="Manuel kontrol notu" className={styles.manualNote} placeholder="Kısa ekip notu (isteğe bağlı)" value={values.notes} onChange={event => setValues(previous => ({ ...previous, notes: event.target.value }))} />
        <button type="submit" className={styles.saveButton} disabled={busy}>{busy ? 'Kaydediliyor…' : 'Doğrulamayı kaydet'}</button>
      </div>
    </form>
  );
}
