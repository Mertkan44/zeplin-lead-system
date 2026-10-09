// What the research established, and what still has to be asked or checked.
import { openExternal } from '../../lib/browser';
import styles from './LeadDetail.module.css';

interface BriefItem {
  code?: string;
  title: string;
  evidence?: string;
  confidence?: number;
  source_label?: string;
  source_url?: string;
  next_step?: string;
  note?: string;
}

export interface ResearchBrief {
  status?: string;
  status_label?: string;
  counts?: { confirmed?: number; opportunities?: number };
  coverage?: number;
  source_count?: number;
  stale?: boolean;
  confirmed_gaps?: BriefItem[];
  likely_gaps?: BriefItem[];
  manual_facts?: BriefItem[];
  manual_checks?: BriefItem[];
  unknowns?: BriefItem[];
  guardrail?: string;
}

export function ResearchBriefCard({ brief }: { brief: ResearchBrief | null }) {
  if (!brief) return null;
  const gaps = [...(brief.confirmed_gaps || []), ...(brief.likely_gaps || [])];
  const manualFacts = brief.manual_facts || [];
  const unknowns = brief.manual_checks || brief.unknowns || [];
  const tone = brief.status === 'ready' ? styles.badgeVerified : brief.status === 'partial' ? styles.badgeDiscovery : styles.badgeCount;
  return (
    <section className={styles.card} aria-labelledby="research-title">
      <div className={`${styles.cardHeader} ${styles.cardHeaderRow}`}>
        <div>
          <div className={styles.eyebrow}>ARAŞTIRMA DOSYASI</div>
          <h2 id="research-title" className={styles.cardTitle}>Ne biliyoruz, neyi hâlâ sormalıyız?</h2>
        </div>
        <span className={tone}>{brief.status_label}</span>
      </div>
      <div className={styles.researchStats}>
        <div className={styles.researchStat}><strong>{brief.counts?.confirmed || 0}</strong><span>Doğrulanmış açık</span></div>
        <div className={styles.researchStat}><strong>{brief.counts?.opportunities || 0}</strong><span>Fırsat sinyali</span></div>
        <div className={styles.researchStat}><strong>%{brief.coverage || 0}</strong><span>Tarama kapsamı</span></div>
        <div className={styles.researchStat}><strong>{brief.source_count || 0}</strong><span>Kaynak</span></div>
      </div>
      {brief.stale && <div className={styles.warning}>Araştırma 30 günden eski veya tarihsiz. Temastan önce kaynakları yeniden kontrol et.</div>}
      {manualFacts.length > 0 && (
        <div className={styles.manualFacts}>
          {manualFacts.map(item => <span key={item.code || item.title}><strong>{item.title}:</strong> {item.evidence}</span>)}
        </div>
      )}
      <div className={styles.researchColumns}>
        <div>
          <div className={styles.miniLabel}>MÜŞTERİYE SÖYLENEBİLİR</div>
          {gaps.length ? gaps.slice(0, 4).map((item, index) => (
            <div key={`${item.code}-${index}`} className={styles.researchRow}>
              <div className={styles.researchRowHead}><strong>{item.title}</strong><span>%{item.confidence}</span></div>
              <p className={styles.researchEvidence}>{item.evidence}</p>
              <div className={styles.researchSource}>
                <span>{item.source_label}</span>
                {item.source_url && <button type="button" className={styles.link} onClick={() => openExternal(item.source_url)}>Kaynağı aç</button>}
              </div>
            </div>
          )) : <div className={styles.emptyResearch}>Kesin açık bulunmadı. Satış iddiası yerine keşif sorularını kullan.</div>}
        </div>
        <div>
          <div className={styles.miniLabel}>GÖRÜŞMEDE DOĞRULA</div>
          {unknowns.length ? unknowns.slice(0, 5).map((item, index) => (
            <div key={`${item.code || item.title}-${index}`} className={styles.manualRow}>
              <strong>{item.title}</strong>
              <span>{item.next_step || item.note}</span>
              {item.source_url && <button type="button" className={styles.link} onClick={() => openExternal(item.source_url)}>Kontrol et</button>}
            </div>
          )) : <div className={styles.emptyResearch}>Bekleyen manuel kontrol yok.</div>}
        </div>
      </div>
      {brief.guardrail && <div className={styles.guardrail}>{brief.guardrail}</div>}
    </section>
  );
}
