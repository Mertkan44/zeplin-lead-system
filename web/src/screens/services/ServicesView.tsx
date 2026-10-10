import type { Lead, ServiceMatch } from "../../data/types";
import { SERVICES } from "../../domain/catalog";
import { PageHeader } from "../shared/PageHeader";
import styles from "./ServicesView.module.css";

const TYPES: Record<string, string> = {
  monthly: "Aylık",
  project: "Proje",
  project_or_monthly: "Proje / Aylık",
};
const SIGNALS: Record<string, string> = {
  no_website: "Website bulunamaması",
  no_ssl: "Güvenli bağlantı sorunu",
  not_mobile: "Mobil uyum sorunu",
  slow_site: "Yavaş sayfa yüklenmesi",
  no_schema: "Yapılandırılmış veri eksikliği",
  no_og: "Paylaşım önizlemesi eksikliği",
  no_instagram: "Instagram hesabının bulunamaması",
  low_engagement: "Düşük etkileşim",
  low_followers: "Düşük takipçi sayısı",
};

export function ServicesView({
  leads,
  signalsAvailable = true,
}: {
  leads: Lead[];
  signalsAvailable?: boolean;
}) {
  const matchesBySlug = new Map<string, ServiceMatch[]>();
  leads.forEach((lead) =>
    (lead.matched_services || []).forEach((match) =>
      matchesBySlug.set(match.slug, [
        ...(matchesBySlug.get(match.slug) || []),
        match,
      ]),
    ),
  );
  return (
    <div className={styles.root}>
      <PageHeader
        eyebrow="HİZMETLER"
        title="Zeplin Media Hizmetleri"
        subtitle={`${SERVICES.length} hizmet · Kapsam, öneri dayanakları ve keşif soruları`}
      />
      <p className={styles.scope}>
        {signalsAvailable
          ? "Sayılar yalnız erişebildiğin işletmelerdeki hizmet eşleşmelerini gösterir; satış fırsatı veya gelir değildir."
          : "İşletme verileri henüz alınamadı; hizmet kataloğu gösteriliyor, eşleşme sayıları bilinmiyor."}
      </p>
      <ul className={styles.grid}>
        {SERVICES.map((service) => {
          const matches = matchesBySlug.get(service.slug) || [];
          return (
            <li
              key={service.slug}
              id={`hizmet-${service.slug}`}
              className={styles.card}
            >
              <div className={styles.tags}>
                <span className={styles.tag}>
                  {TYPES[service.service_type] || "Kapsamlanacak"}
                </span>
                <span className={styles.tag}>{service.category}</span>
                <span className={styles.tag}>
                  Sorumlu: {service.owner === "Sales" ? "Satış" : service.owner}
                </span>
              </div>
              <h2 className={styles.name}>{service.name}</h2>
              <p className={styles.desc}>{service.desc}</p>
              <div className={styles.detects}>
                <strong>
                  {service.recommendation_mode === "discovery_only"
                    ? "Görüşmede ihtiyaç doğrulanmalı"
                    : "Önerinin dayanağı"}
                </strong>
                <p>
                  {service.recommendation_mode === "discovery_only"
                    ? "Yalnız araştırma skoru bu hizmeti önermek için yeterli değildir."
                    : (service.triggers as string[])
                        .map(
                          (key) =>
                            SIGNALS[key] || "Görüşmede doğrulanacak bulgu",
                        )
                        .join(" · ")}
                </p>
                {service.recommendation_mode === "conditional" && (
                  <p>
                    Bulgular ihtimali gösterir; ihtiyaç ve kapsam görüşmede
                    teyit edilir.
                  </p>
                )}
              </div>
              <dl className={styles.stats}>
                <div>
                  <dt className={styles.statLabel}>Eşleşme</dt>
                  <dd className={styles.statValue}>
                    {signalsAvailable ? matches.length : "—"}
                  </dd>
                </div>
                <div>
                  <dt className={styles.statLabel}>Kanıtlı açık</dt>
                  <dd className={styles.statValue}>
                    {signalsAvailable
                      ? matches.filter(
                          (item) => item.match_type === "confirmed_gap",
                        ).length
                      : "—"}
                  </dd>
                </div>
                <div>
                  <dt className={styles.statLabel}>Görüşmede doğrula</dt>
                  <dd className={styles.statValue}>
                    {signalsAvailable
                      ? matches.filter(
                          (item) => item.match_type !== "confirmed_gap",
                        ).length
                      : "—"}
                  </dd>
                </div>
              </dl>
              <p className={styles.price}>
                {service.pricing_status === "approved"
                  ? "Fiyat onaylı; teklif kapsamına göre doğrulanır."
                  : "Fiyat ve kapsam yönetim onayı bekliyor."}
              </p>
              <details className={styles.details}>
                <summary>Kapsam ve keşif soruları</summary>
                <h3>Teslimat</h3>
                <ul>
                  {(service.deliverables as string[]).map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
                <h3>Kapsam dışında</h3>
                {service.exclusions.length ? (
                  <ul>
                    {(service.exclusions as string[]).map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <p>Görüşmede ayrıca netleştirilir.</p>
                )}
                <h3>Keşifte sor</h3>
                <ul>
                  {(service.discovery_questions as string[]).map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </details>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
