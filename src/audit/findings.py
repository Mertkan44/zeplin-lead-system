from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any


AUDIT_MODEL_VERSION = 3


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _tokens(value: str | None) -> set[str]:
    normalized = unicodedata.normalize("NFKD", value or "")
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = normalized.casefold().replace("ı", "i")
    ignored = {
        "ve",
        "the",
        "at",
        "istanbul",
        "restaurant",
        "restoran",
        "cafe",
        "kafe",
        "magaza",
        "klinik",
        "clinic",
    }
    return {
        token
        for token in re.findall(r"[a-z0-9]+", normalized)
        if len(token) > 1 and token not in ignored
    }


def _phone(value: str | None) -> str | None:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("90") and len(digits) >= 12:
        digits = digits[-10:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    return digits if len(digits) == 10 else None


def _finding(
    *,
    code: str,
    title: str,
    category: str,
    severity: str,
    confidence: int,
    evidence: str,
    impact: str,
    source_url: str | None,
    checked_at: str | None,
    observed: str | int | float | None = None,
    expected: str | None = None,
    service_slugs: list[str] | None = None,
    recommendation_strength: str = "conditional",
    talking_point: str | None = None,
    verification: str | None = None,
) -> dict[str, Any]:
    confidence = max(0, min(int(confidence), 100))
    return {
        "code": code,
        "title": title,
        "category": category,
        "status": "confirmed" if confidence >= 80 else "likely",
        "severity": severity,
        "confidence": confidence,
        "evidence": evidence,
        "impact": impact,
        "source_url": source_url,
        "checked_at": checked_at,
        "observed": observed,
        "expected": expected,
        "service_slugs": service_slugs or [],
        "recommendation_strength": recommendation_strength,
        "talking_point": talking_point or impact,
        "verification": verification,
    }


def _check(
    *,
    code: str,
    label: str,
    category: str,
    weight: int,
    status: str,
    confidence: int,
    note: str,
    source_url: str | None = None,
    checked_at: str | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "label": label,
        "category": category,
        "weight": weight,
        "status": status,
        "confidence": max(0, min(int(confidence), 100)),
        "note": note,
        "source_url": source_url,
        "checked_at": checked_at,
    }


def _grade(score: int) -> str:
    if score >= 80:
        return "A"
    if score >= 60:
        return "B"
    if score >= 40:
        return "C"
    return "D"


def _website_profile(lead: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    website = lead.get("website") or {}
    findings: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    source_url = website.get("final_url") or website.get("website_url") or lead.get("maps_url")
    checked_at = website.get("checked_at") or lead.get("last_analyzed")
    is_v3 = int(website.get("audit_version") or 0) >= 3
    audit_status = website.get("audit_status")
    lookup_status = website.get("lookup_status")

    if is_v3 and audit_status == "missing":
        if lookup_status == "not_found":
            confidence = 94
            checks.append(
                _check(
                    code="website.presence",
                    label="Website varlığı",
                    category="website",
                    weight=18,
                    status="fail",
                    confidence=confidence,
                    note="Google Maps işletme panelinde website bağlantısı bulunamadı.",
                    source_url=lead.get("maps_url"),
                    checked_at=checked_at,
                )
            )
            findings.append(
                _finding(
                    code="website.absent",
                    title="İşletme panelinde website bağlantısı yok",
                    category="website",
                    severity="high",
                    confidence=confidence,
                    evidence="Google Maps işletme panelindeki website alanı tarandı ve bağlantı bulunamadı.",
                    impact="Müşteri; hizmet, güven ve iletişim bilgisini işletmenin kontrol ettiği tek bir sayfada göremeyebilir.",
                    source_url=lead.get("maps_url"),
                    checked_at=checked_at,
                    observed="Website bağlantısı yok",
                    expected="İşletmeye ait çalışan bir website",
                    service_slugs=["website_creation"],
                    recommendation_strength="direct",
                    talking_point="Maps panelinizde müşteriyi yönlendiren bir website görünmüyor; hizmetleri ve iletişim aksiyonlarını tek yerde toplayabiliriz.",
                    verification="İşletmenin farklı bir alan adı kullanıp kullanmadığını görüşmede teyit et.",
                )
            )
        else:
            checks.append(
                _check(
                    code="website.presence",
                    label="Website varlığı",
                    category="website",
                    weight=18,
                    status="unknown",
                    confidence=0,
                    note="Website alanı güvenilir biçimde kontrol edilemedi.",
                    source_url=lead.get("maps_url"),
                    checked_at=checked_at,
                )
            )
        return findings, checks

    if is_v3 and audit_status == "invalid_candidate":
        checks.append(
            _check(
                code="website.presence",
                label="Website varlığı",
                category="website",
                weight=18,
                status="fail",
                confidence=96,
                note="Website alanı bağımsız bir site yerine sosyal/mesajlaşma bağlantısına gidiyor.",
                source_url=source_url,
                checked_at=checked_at,
            )
        )
        findings.append(
            _finding(
                code="website.invalid_candidate",
                title="Website alanı bağımsız bir siteye gitmiyor",
                category="website",
                severity="high",
                confidence=96,
                evidence=f"Maps website alanındaki bağlantı türü: {website.get('candidate_kind') or 'website dışı bağlantı'}.",
                impact="Müşteri detaylı hizmet, güven ve iletişim bilgisini işletmenin kontrol ettiği bir website üzerinde inceleyemiyor.",
                source_url=source_url,
                checked_at=checked_at,
                observed=website.get("website_url"),
                expected="İşletmeye ait website alan adı",
                service_slugs=["website_creation"],
                recommendation_strength="direct",
                verification="İşletmenin ayrıca kullandığı bir website olup olmadığını teyit et.",
            )
        )
        return findings, checks

    if is_v3 and audit_status in {"blocked", "unreachable", "server_error", "http_error", "non_html"}:
        checks.append(
            _check(
                code="website.presence",
                label="Website erişimi",
                category="website",
                weight=18,
                status="unknown",
                confidence=0,
                note=f"Kontrol durumu: {audit_status}. Yok veya bozuk olduğu sonucuna varılamaz.",
                source_url=source_url,
                checked_at=checked_at,
            )
        )
        if audit_status == "unreachable":
            resolution_error = "resolved" in str(website.get("error") or "")
            confidence = 84 if resolution_error else 66
            findings.append(
                _finding(
                    code="website.unreachable",
                    title="Website adresine bu kontrolde ulaşılamadı",
                    category="website",
                    severity="high",
                    confidence=confidence,
                    evidence=f"Bağlantı hatası: {website.get('error') or 'site yanıt vermedi'}.",
                    impact="Aynı durum müşterilerde de oluşuyorsa website üzerinden bilgi alma ve iletişim akışı kesiliyor olabilir.",
                    source_url=source_url,
                    checked_at=checked_at,
                    observed=website.get("error"),
                    expected="Alan adının çözülmesi ve başarılı HTML yanıtı",
                    service_slugs=["website_creation"],
                    recommendation_strength="conditional",
                    verification="Farklı ağdan ve DNS üzerinden tekrar dene; alan adının süresini ve hosting durumunu işletmeyle teyit et.",
                )
            )
        elif audit_status in {"server_error", "http_error"}:
            status_code = website.get("http_status")
            findings.append(
                _finding(
                    code="website.http_error",
                    title="Website bu kontrolde hata yanıtı verdi",
                    category="website",
                    severity="high",
                    confidence=75,
                    evidence=f"Website isteği HTTP {status_code or 'hata'} yanıtı verdi.",
                    impact="Aynı hata müşterilerde de oluşuyorsa website üzerinden bilgi alma ve iletişime geçme akışı kesilebilir.",
                    source_url=source_url,
                    checked_at=checked_at,
                    observed=status_code,
                    expected="Başarılı HTML yanıtı",
                    service_slugs=["website_creation"],
                    recommendation_strength="conditional",
                    verification="Farklı ağ ve cihazdan tekrar aç; geçici hata olmadığını doğrula.",
                )
            )
        return findings, checks

    if not is_v3:
        if website.get("has_website") is True:
            checks.append(
                _check(
                    code="website.presence",
                    label="Website varlığı",
                    category="website",
                    weight=18,
                    status="pass",
                    confidence=55,
                    note="Eski tarama websitesinin açıldığını kaydetmiş; yeniden denetlenmeli.",
                    source_url=source_url,
                    checked_at=checked_at,
                )
            )
        else:
            checks.append(
                _check(
                    code="website.presence",
                    label="Website varlığı",
                    category="website",
                    weight=18,
                    status="unknown",
                    confidence=0,
                    note="Eski kayıtta website bulunamamış; bu yokluk kanıtı değildir.",
                    source_url=lead.get("maps_url"),
                    checked_at=checked_at,
                )
            )
        return findings, checks

    checks.append(
        _check(
            code="website.presence",
            label="Website erişimi",
            category="website",
            weight=18,
            status="pass",
            confidence=98,
            note=f"HTML sayfası HTTP {website.get('http_status')} ile açıldı.",
            source_url=source_url,
            checked_at=checked_at,
        )
    )

    placeholder = website.get("placeholder_detected")
    checks.append(
        _check(
            code="website.placeholder",
            label="Kurumsal içerik",
            category="website",
            weight=14,
            status="fail" if placeholder is True else "pass" if placeholder is False else "unknown",
            confidence=98 if placeholder is not None else 0,
            note=(
                f"Varsayılan/park sayfası sinyali: {website.get('placeholder_reason')}."
                if placeholder
                else "Varsayılan hosting veya park sayfası sinyali bulunmadı."
                if placeholder is False
                else "Kontrol tamamlanamadı."
            ),
            source_url=source_url,
            checked_at=checked_at,
        )
    )
    if placeholder:
        findings.append(
            _finding(
                code="website.placeholder",
                title="Website adresi kurumsal içerik yerine varsayılan sayfa gösteriyor",
                category="website",
                severity="critical",
                confidence=98,
                evidence=(
                    f"Sayfa başlığı `{website.get('title') or 'yok'}`; "
                    f"tespit: {website.get('placeholder_reason') or 'varsayılan hosting sayfası'}."
                ),
                impact="Müşteri işletmenin hizmet, güven ve iletişim bilgisine ulaşamıyor; alan adı teknik olarak açık olsa da website işlevini görmüyor.",
                source_url=source_url,
                checked_at=checked_at,
                observed=website.get("title"),
                expected="İşletmeye ait güncel kurumsal içerik",
                service_slugs=["website_creation"],
                recommendation_strength="direct",
                talking_point="Kayıtlı alan adınız şu anda işletme içeriği yerine sunucunun varsayılan sayfasını gösteriyor; bunu çalışan, mobil uyumlu kurumsal siteye çevirebiliriz.",
                verification="Alan adının geçici bakımda veya farklı bir adrese taşınmış olup olmadığını teyit et.",
            )
        )
        # A parked/default page cannot provide meaningful evidence for the site's
        # SEO, conversion or accessibility implementation. Keep the root cause
        # instead of multiplying it into dependent findings.
        return findings, checks

    def add_binary(
        *,
        code: str,
        label: str,
        field: str,
        weight: int,
        title: str,
        severity: str,
        evidence: str,
        impact: str,
        expected: str,
        service_slugs: list[str],
        confidence: int = 94,
        strength: str = "conditional",
        verification: str | None = None,
    ) -> None:
        value = website.get(field)
        if value is None:
            checks.append(
                _check(
                    code=code,
                    label=label,
                    category="website",
                    weight=weight,
                    status="unknown",
                    confidence=0,
                    note="Kontrol tamamlanamadı.",
                    source_url=source_url,
                    checked_at=checked_at,
                )
            )
            return
        checks.append(
            _check(
                code=code,
                label=label,
                category="website",
                weight=weight,
                status="pass" if value else "fail",
                confidence=confidence,
                note="Kontrol geçti." if value else evidence,
                source_url=source_url,
                checked_at=checked_at,
            )
        )
        if value:
            return
        findings.append(
            _finding(
                code=code,
                title=title,
                category="website",
                severity=severity,
                confidence=confidence,
                evidence=evidence,
                impact=impact,
                source_url=source_url,
                checked_at=checked_at,
                observed="Bulunamadı",
                expected=expected,
                service_slugs=service_slugs,
                recommendation_strength=strength,
                verification=verification,
            )
        )

    add_binary(
        code="website.https",
        label="HTTPS",
        field="has_ssl",
        weight=8,
        title="Website güvenli HTTPS bağlantısı kullanmıyor",
        severity="high",
        evidence=f"Son açılan adres `{website.get('final_url') or website.get('website_url')}` HTTP protokolünde kaldı.",
        impact="Tarayıcı güven uyarıları ve veri güvenliği kaygısı iletişim veya form dönüşümünü olumsuz etkileyebilir.",
        expected="HTTPS ile açılan ve geçerli sertifikası bulunan adres",
        service_slugs=["seo_organic"],
    )
    add_binary(
        code="website.viewport",
        label="Mobil görünüm etiketi",
        field="is_mobile_friendly",
        weight=6,
        title="Mobil görünüm yapılandırması bulunamadı",
        severity="high",
        evidence="Ana sayfa HTML'inde viewport meta etiketi bulunamadı.",
        impact="Sayfa mobil cihazlarda yanlış ölçeklenebilir; bu kontrol tek başına tam mobil uyumluluk testi değildir.",
        expected="Geçerli viewport meta etiketi",
        service_slugs=["website_creation", "seo_organic"],
        verification="Gerçek mobil cihaz veya ekran görüntüsüyle yerleşimi ayrıca kontrol et.",
    )
    add_binary(
        code="seo.indexable",
        label="Google indekslenebilirliği",
        field="is_indexable",
        weight=12,
        title="Ana sayfa arama motorlarına kapalı",
        severity="critical",
        evidence=f"Sayfada `{website.get('noindex_reason') or 'noindex'}` sinyali bulundu.",
        impact="Arama motoru bu talimata uyarsa ana sayfa organik arama sonuçlarında gösterilmeyebilir.",
        expected="Ana sayfanın index yönergesine açık olması",
        service_slugs=["seo_organic"],
        confidence=98,
    )

    title_length = website.get("title_length")
    title_ok = isinstance(title_length, int) and 15 <= title_length <= 65
    checks.append(
        _check(
            code="seo.title",
            label="Sayfa başlığı",
            category="seo",
            weight=5,
            status="pass" if title_ok else "fail",
            confidence=96,
            note=f"Başlık uzunluğu: {title_length or 0} karakter.",
            source_url=source_url,
            checked_at=checked_at,
        )
    )
    if not title_ok:
        findings.append(
            _finding(
                code="seo.title",
                title="Ana sayfa başlığı eksik veya zayıf yapılandırılmış",
                category="seo",
                severity="medium",
                confidence=96,
                evidence=f"HTML title uzunluğu {title_length or 0} karakter; içerik: {website.get('title') or 'yok'}.",
                impact="Arama sonucundaki başlık işletmeyi ve sunduğu hizmeti yeterince açıklamayabilir.",
                source_url=source_url,
                checked_at=checked_at,
                observed=website.get("title"),
                expected="İşletme ve ana hizmeti açıklayan yaklaşık 15-65 karakterlik benzersiz başlık",
                service_slugs=["seo_organic"],
            )
        )

    business_tokens = _tokens(lead.get("name"))
    identity_text = " ".join(
        [
            str(website.get("title") or ""),
            " ".join(website.get("h1_texts") or []),
            " ".join(website.get("schema_names") or []),
        ]
    )
    identity_tokens = _tokens(identity_text)
    identity_overlap = business_tokens & identity_tokens
    identity_compact = re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", identity_text).casefold())
    embedded_brand_match = any(
        len(token) >= 4 and token in identity_compact
        for token in business_tokens
    )
    identity_checked = bool(business_tokens and identity_tokens)
    identity_ok = bool(identity_overlap or embedded_brand_match)
    checks.append(
        _check(
            code="identity.website_name",
            label="Website işletme kimliği",
            category="identity",
            weight=7,
            status="pass" if identity_ok else "fail" if identity_checked else "unknown",
            confidence=82 if identity_checked else 0,
            note=(
                f"İşletme adıyla ortak marka ifadesi bulundu: {', '.join(sorted(identity_overlap)) or 'birleşik marka yazımı'}."
                if identity_ok
                else "Başlık, H1 ve Schema adında işletme adıyla ortak belirgin ifade bulunamadı."
                if identity_checked
                else "Kimlik karşılaştırması için yeterli başlık verisi yok."
            ),
            source_url=source_url,
            checked_at=checked_at,
        )
    )
    if identity_checked and not identity_ok and not website.get("placeholder_detected"):
        findings.append(
            _finding(
                code="identity.website_name",
                title="Website başlığı işletme kimliğiyle örtüşmüyor",
                category="identity",
                severity="high",
                confidence=82,
                evidence=(
                    f"Maps adı `{lead.get('name')}`; website başlığı "
                    f"`{website.get('title') or 'yok'}` ve H1 değerleri "
                    f"`{', '.join(website.get('h1_texts') or []) or 'yok'}`."
                ),
                impact="Yanlış veya genel bir sayfa eşleşmiş olabilir; bu site üzerinden yapılacak tüm satış tespitleri önce kimlik doğrulaması gerektirir.",
                source_url=source_url,
                checked_at=checked_at,
                observed=website.get("title"),
                expected=f"{lead.get('name')} ile açık marka ilişkisi",
                service_slugs=[],
                recommendation_strength="none",
                verification="Alan adının bu şubeye/markaya ait olduğunu Maps, website footer ve işletme yetkilisiyle doğrula.",
            )
        )

    description_length = website.get("meta_description_length")
    description_ok = isinstance(description_length, int) and 70 <= description_length <= 180
    checks.append(
        _check(
            code="seo.meta_description",
            label="Meta açıklama",
            category="seo",
            weight=5,
            status="pass" if description_ok else "fail",
            confidence=96,
            note=f"Meta açıklama uzunluğu: {description_length or 0} karakter.",
            source_url=source_url,
            checked_at=checked_at,
        )
    )
    if not description_ok:
        findings.append(
            _finding(
                code="seo.meta_description",
                title="Ana sayfa meta açıklaması eksik veya zayıf",
                category="seo",
                severity="medium",
                confidence=96,
                evidence=f"Meta açıklama uzunluğu {description_length or 0} karakter.",
                impact="Arama sonucundaki açıklama işletmenin değerini ve tıklama nedenini net anlatmayabilir.",
                source_url=source_url,
                checked_at=checked_at,
                observed=website.get("meta_description"),
                expected="Ana hizmeti ve lokasyonu doğal biçimde anlatan özgün meta açıklama",
                service_slugs=["seo_organic"],
            )
        )

    h1_count = website.get("h1_count")
    h1_ok = h1_count == 1
    checks.append(
        _check(
            code="seo.h1",
            label="Ana başlık yapısı",
            category="seo",
            weight=4,
            status="pass" if h1_ok else "fail",
            confidence=95,
            note=f"H1 sayısı: {h1_count if h1_count is not None else 'ölçülemedi'}.",
            source_url=source_url,
            checked_at=checked_at,
        )
    )
    if not h1_ok:
        findings.append(
            _finding(
                code="seo.h1",
                title="Ana sayfanın H1 başlık yapısı net değil",
                category="seo",
                severity="medium",
                confidence=95,
                evidence=f"HTML içinde {h1_count or 0} adet H1 bulundu.",
                impact="Sayfanın ana konusu kullanıcı ve arama motoru için daha belirsiz kalabilir.",
                source_url=source_url,
                checked_at=checked_at,
                observed=h1_count,
                expected="Sayfanın ana konusunu anlatan tek bir H1",
                service_slugs=["seo_organic"],
            )
        )

    add_binary(
        code="seo.canonical",
        label="Canonical adres",
        field="has_canonical",
        weight=3,
        title="Canonical sayfa adresi belirtilmemiş",
        severity="low",
        evidence="Ana sayfa HTML'inde canonical link etiketi bulunamadı.",
        impact="Aynı içeriğin farklı adresleri varsa arama motorunun ana sürümü seçmesi zorlaşabilir.",
        expected="Doğru ana sayfa adresini gösteren canonical etiketi",
        service_slugs=["seo_organic"],
    )
    add_binary(
        code="seo.schema",
        label="Yapılandırılmış veri",
        field="has_schema",
        weight=8,
        title="Geçerli yapılandırılmış veri bulunamadı",
        severity="medium",
        evidence=(
            f"JSON-LD blok sayısı {website.get('schema_block_count') or 0}; "
            f"geçersiz blok sayısı {website.get('schema_invalid_count') or 0}."
        ),
        impact="Arama motorunun işletme türü, iletişim ve yerel işletme bilgisini doğrudan anlaması zorlaşabilir.",
        expected="İşletme türüne uygun geçerli JSON-LD yapılandırılmış veri",
        service_slugs=["seo_organic"],
    )
    if website.get("has_schema") is True and website.get("has_local_business_schema") is False:
        checks.append(
            _check(
                code="seo.local_schema",
                label="Yerel işletme şeması",
                category="seo",
                weight=4,
                status="fail",
                confidence=92,
                note=f"Bulunan türler: {', '.join(website.get('schema_types') or []) or 'tür yok'}.",
                source_url=source_url,
                checked_at=checked_at,
            )
        )
        findings.append(
            _finding(
                code="seo.local_schema",
                title="Schema var ancak işletme türünü açıklamıyor",
                category="seo",
                severity="medium",
                confidence=92,
                evidence=f"Bulunan Schema türleri: {', '.join(website.get('schema_types') or []) or 'tanımsız'}.",
                impact="Yerel işletmeye ait kategori, adres ve iletişim bilgisinin arama motoruna aktarımı sınırlı kalabilir.",
                source_url=source_url,
                checked_at=checked_at,
                observed=", ".join(website.get("schema_types") or []),
                expected="LocalBusiness veya sektöre uygun alt tür",
                service_slugs=["seo_organic"],
            )
        )
    elif website.get("has_local_business_schema") is True:
        schema_fields = set(website.get("schema_fields") or [])
        expected_fields = {"address", "telephone", "url"}
        missing_fields = sorted(expected_fields - schema_fields)
        checks.append(
            _check(
                code="seo.local_schema_completeness",
                label="Yerel Schema alanları",
                category="seo",
                weight=4,
                status="fail" if missing_fields else "pass",
                confidence=92,
                note=(
                    f"Eksik temel alanlar: {', '.join(missing_fields)}."
                    if missing_fields
                    else "Adres, telefon ve URL alanları mevcut."
                ),
                source_url=source_url,
                checked_at=checked_at,
            )
        )
        if missing_fields:
            findings.append(
                _finding(
                    code="seo.local_schema_completeness",
                    title="Yerel işletme Schema bilgileri eksik",
                    category="seo",
                    severity="medium",
                    confidence=92,
                    evidence=f"LocalBusiness türü var; eksik temel alanlar: {', '.join(missing_fields)}.",
                    impact="Arama motoruna aktarılan adres, telefon veya resmi URL bilgisi eksik kalıyor.",
                    source_url=source_url,
                    checked_at=checked_at,
                    observed=", ".join(sorted(schema_fields)),
                    expected="address, telephone ve url alanları",
                    service_slugs=["seo_organic"],
                )
            )

    add_binary(
        code="social.open_graph",
        label="Sosyal paylaşım önizlemesi",
        field="has_og",
        weight=3,
        title="Sosyal paylaşım önizleme alanları eksik",
        severity="low",
        evidence=f"Eksik Open Graph alanları: {', '.join(website.get('og_missing_fields') or []) or 'temel alanlar'}.",
        impact="Website linki sosyal medya veya mesajlaşmada paylaşıldığında başlık, açıklama veya görsel eksik görünebilir.",
        expected="og:title, og:description, og:image ve og:url",
        service_slugs=["seo_organic"],
    )
    add_binary(
        code="seo.sitemap",
        label="XML sitemap",
        field="has_sitemap",
        weight=4,
        title="XML sitemap bulunamadı",
        severity="medium",
        evidence="robots.txt içindeki sitemap adresleri ve /sitemap.xml kontrolünde geçerli sitemap bulunamadı.",
        impact="Arama motorlarının önemli sayfaları düzenli keşfetmesi ve güncellemeleri izlemesi zorlaşabilir.",
        expected="Erişilebilir XML sitemap",
        service_slugs=["seo_organic"],
        confidence=90,
    )
    robots_blocked = website.get("robots_blocks_site")
    checks.append(
        _check(
            code="seo.robots_block",
            label="Robots erişimi",
            category="seo",
            weight=10,
            status="fail" if robots_blocked is True else "pass" if robots_blocked is False else "unknown",
            confidence=98 if robots_blocked is not None else 0,
            note="robots.txt tüm siteyi engelliyor." if robots_blocked else "Tüm siteyi engelleyen robots kuralı bulunmadı." if robots_blocked is False else "robots.txt güvenilir biçimde okunamadı.",
            source_url=source_url,
            checked_at=checked_at,
        )
    )
    if robots_blocked:
        findings.append(
            _finding(
                code="seo.robots_block",
                title="robots.txt arama motorlarına tüm siteyi kapatıyor",
                category="seo",
                severity="critical",
                confidence=98,
                evidence="User-agent: * altında kök dizini engelleyen `Disallow: /` kuralı bulundu.",
                impact="Arama motorları site sayfalarını tarayamaz ve organik görünürlük ciddi biçimde sınırlanabilir.",
                source_url=source_url,
                checked_at=checked_at,
                observed="Disallow: /",
                expected="Canlı sitede yalnızca gerekli özel yolların engellenmesi",
                service_slugs=["seo_organic"],
                recommendation_strength="conditional",
                verification="Kuralın staging/bakım amacıyla geçici olmadığını yayın sorumlusuyla doğrula.",
            )
        )

    contact_values = [
        website.get("has_phone_link"),
        website.get("has_whatsapp"),
        website.get("has_contact_form"),
    ]
    contact_ok = any(value is True for value in contact_values)
    checks.append(
        _check(
            code="conversion.contact_path",
            label="Görünür iletişim aksiyonu",
            category="conversion",
            weight=6,
            status="pass" if contact_ok else "fail",
            confidence=90,
            note="Telefon, WhatsApp veya iletişim formu bulundu." if contact_ok else "Telefon, WhatsApp veya iletişim formu sinyali bulunamadı.",
            source_url=source_url,
            checked_at=checked_at,
        )
    )
    if not contact_ok:
        findings.append(
            _finding(
                code="conversion.contact_path",
                title="Ana sayfada net iletişim aksiyonu bulunamadı",
                category="conversion",
                severity="high",
                confidence=90,
                evidence="HTML içinde tel bağlantısı, WhatsApp bağlantısı veya iletişim formu sinyali bulunamadı.",
                impact="İlgilenen ziyaretçi arama, mesaj veya form adımına hızlı geçemeyebilir.",
                source_url=source_url,
                checked_at=checked_at,
                observed="Belirgin iletişim aksiyonu bulunamadı",
                expected="Telefon, WhatsApp veya iletişim formundan en az biri",
                service_slugs=["website_creation"],
                verification="Sayfanın JavaScript ile sonradan yüklenen veya sadece iç sayfada bulunan iletişim alanını görsel olarak kontrol et.",
            )
        )

    maps_phone = _phone(lead.get("phone"))
    website_phones = {
        phone
        for value in (website.get("phone_numbers") or [])
        for phone in [_phone(str(value))]
        if phone
    }
    phone_identity_checked = bool(maps_phone and website_phones)
    phone_identity_ok = bool(maps_phone and maps_phone in website_phones)
    checks.append(
        _check(
            code="identity.phone_consistency",
            label="Telefon tutarlılığı",
            category="identity",
            weight=7,
            status="pass" if phone_identity_ok else "fail" if phone_identity_checked else "unknown",
            confidence=94 if phone_identity_checked else 0,
            note=(
                "Maps ve website telefonu eşleşiyor."
                if phone_identity_ok
                else "Maps telefonu website üzerinde bulunan telefonlarla eşleşmiyor."
                if phone_identity_checked
                else "İki kaynakta karşılaştırılabilir telefon bulunamadı."
            ),
            source_url=source_url,
            checked_at=checked_at,
        )
    )
    if phone_identity_checked and not phone_identity_ok:
        findings.append(
            _finding(
                code="identity.phone_consistency",
                title="Maps telefonu ana sayfadaki arama bağlantılarında görünmüyor",
                category="identity",
                severity="medium",
                confidence=84,
                evidence=(
                    f"Maps telefonu `{lead.get('phone')}`; ana sayfadaki tel bağlantıları "
                    f"`{', '.join(sorted(website_phones))}` numaralarına gidiyor."
                ),
                impact="Şube ve merkez numaraları bilinçli olarak farklı olabilir; yine de müşteri Maps ile website arasında farklı arama noktaları görüyor.",
                source_url=source_url,
                checked_at=checked_at,
                observed=f"Maps: {lead.get('phone')} / Site: {', '.join(sorted(website_phones))}",
                expected="Şube ve merkez numaralarının kullanıcıya açık biçimde ayrıştırılması",
                service_slugs=[],
                recommendation_strength="none",
                verification="Şube ve merkez numarası ayrımı olup olmadığını işletmeyle kontrol et; ardından Maps veya website bilgisini güncelle.",
            )
        )

    samples = website.get("response_time_samples_ms") or []
    performance_checked = len(samples) >= 2
    slow_origin = performance_checked and int(website.get("load_time_ms") or 0) >= 2500
    checks.append(
        _check(
            code="performance.origin_response",
            label="Sunucu yanıt örneği",
            category="performance",
            weight=6,
            status="fail" if slow_origin else "pass" if performance_checked else "unknown",
            confidence=68 if performance_checked else 0,
            note=(
                f"{len(samples)} ölçüm medyanı {website.get('load_time_ms')} ms."
                if performance_checked
                else "İki ölçüm alınamadığı için hız yorumu yapılmadı."
            ),
            source_url=source_url,
            checked_at=checked_at,
        )
    )
    if slow_origin:
        findings.append(
            _finding(
                code="performance.origin_response",
                title="İlk HTML yanıtı iki ölçümde de yavaş kaldı",
                category="performance",
                severity="medium",
                confidence=68,
                evidence=f"Ölçümler {samples}; medyan {website.get('load_time_ms')} ms.",
                impact="Sunucu yanıtındaki gecikme sayfanın kullanıcıya görünme süresini uzatabilir; bu ölçüm Core Web Vitals değildir.",
                source_url=source_url,
                checked_at=checked_at,
                observed=f"{website.get('load_time_ms')} ms medyan",
                expected="Bu örneklemde 2500 ms altında ilk HTML yanıtı",
                service_slugs=["seo_organic"],
                verification="PageSpeed Insights veya gerçek kullanıcı verisiyle LCP/INP/CLS değerlerini ayrıca ölç.",
            )
        )

    links_checked = int(website.get("internal_links_checked") or 0)
    broken_links = website.get("broken_internal_links") or []
    checks.append(
        _check(
            code="website.internal_links",
            label="İç bağlantı örneği",
            category="website",
            weight=4,
            status="fail" if broken_links else "pass" if links_checked else "unknown",
            confidence=90 if links_checked else 0,
            note=f"{links_checked} bağlantı kontrol edildi; {len(broken_links)} sorun bulundu.",
            source_url=source_url,
            checked_at=checked_at,
        )
    )
    if broken_links:
        findings.append(
            _finding(
                code="website.internal_links",
                title="Örneklenen iç bağlantılarda hata bulundu",
                category="website",
                severity="high",
                confidence=90,
                evidence="; ".join(
                    f"{item.get('url')} → {item.get('status') or item.get('error')}"
                    for item in broken_links[:3]
                ),
                impact="Ziyaretçi hizmet veya iletişim sayfasına geçerken hata ile karşılaşabilir.",
                source_url=source_url,
                checked_at=checked_at,
                observed=len(broken_links),
                expected="Örneklenen iç bağlantıların başarılı açılması",
                service_slugs=["website_creation", "seo_organic"],
            )
        )

    image_count = int(website.get("image_count") or 0)
    alt_coverage = website.get("image_alt_coverage")
    accessibility_checked = image_count >= 4 and alt_coverage is not None
    low_alt = accessibility_checked and float(alt_coverage) < 60
    checks.append(
        _check(
            code="accessibility.image_alt",
            label="Görsel açıklamaları",
            category="accessibility",
            weight=3,
            status="fail" if low_alt else "pass" if accessibility_checked else "unknown",
            confidence=92 if accessibility_checked else 0,
            note=f"{image_count} görselde alt metin kapsamı %{alt_coverage}." if accessibility_checked else "Yeterli görsel örneği yok.",
            source_url=source_url,
            checked_at=checked_at,
        )
    )
    if low_alt:
        findings.append(
            _finding(
                code="accessibility.image_alt",
                title="Görsellerin çoğunda açıklayıcı alt metin yok",
                category="accessibility",
                severity="medium",
                confidence=92,
                evidence=f"{image_count} görselin %{alt_coverage} kadarı alt metin içeriyor.",
                impact="Ekran okuyucu kullanan ziyaretçiler içeriği anlamakta zorlanabilir; görsel arama bağlamı da sınırlı kalabilir.",
                source_url=source_url,
                checked_at=checked_at,
                observed=f"%{alt_coverage}",
                expected="İçerik taşıyan görsellerde anlamlı alt metin",
                service_slugs=["seo_organic"],
            )
        )

    form_controls = int(website.get("form_control_count") or 0)
    form_coverage = website.get("form_label_coverage")
    form_checked = form_controls >= 2 and form_coverage is not None
    low_form_labels = form_checked and float(form_coverage) < 75
    checks.append(
        _check(
            code="accessibility.form_labels",
            label="Form alanı etiketleri",
            category="accessibility",
            weight=3,
            status="fail" if low_form_labels else "pass" if form_checked else "unknown",
            confidence=90 if form_checked else 0,
            note=f"{form_controls} alanda erişilebilir etiket kapsamı %{form_coverage}." if form_checked else "Değerlendirilecek form örneği yok.",
            source_url=source_url,
            checked_at=checked_at,
        )
    )
    if low_form_labels:
        findings.append(
            _finding(
                code="accessibility.form_labels",
                title="Form alanlarının erişilebilir etiketleri eksik",
                category="accessibility",
                severity="medium",
                confidence=90,
                evidence=f"{form_controls} form alanında etiket kapsamı %{form_coverage}.",
                impact="Klavye veya ekran okuyucu kullanan ziyaretçiler formu tamamlamakta zorlanabilir.",
                source_url=source_url,
                checked_at=checked_at,
                observed=f"%{form_coverage}",
                expected="Her form alanının görünür veya erişilebilir adı olması",
                service_slugs=[],
                recommendation_strength="none",
            )
        )

    word_count = website.get("word_count")
    thin_content = (
        isinstance(word_count, int)
        and word_count < 80
        and not website.get("placeholder_detected")
    )
    checks.append(
        _check(
            code="content.homepage_depth",
            label="Ana sayfa metin kapsamı",
            category="content",
            weight=4,
            status="fail" if thin_content else "pass" if isinstance(word_count, int) else "unknown",
            confidence=64 if isinstance(word_count, int) else 0,
            note=f"Ana HTML içinde yaklaşık {word_count} kelime bulundu." if isinstance(word_count, int) else "Metin kapsamı ölçülemedi.",
            source_url=source_url,
            checked_at=checked_at,
        )
    )
    if thin_content:
        findings.append(
            _finding(
                code="content.homepage_depth",
                title="Ana HTML içeriği işletmeyi açıklamak için çok sınırlı",
                category="content",
                severity="medium",
                confidence=64,
                evidence=f"Script ve stil blokları çıkarıldıktan sonra ana HTML içinde yaklaşık {word_count} kelime bulundu.",
                impact="Hizmet, lokasyon ve güven unsurları yeterince açıklanmıyorsa hem ziyaretçi hem arama motoru sayfanın değerini anlamakta zorlanabilir.",
                source_url=source_url,
                checked_at=checked_at,
                observed=f"{word_count} kelime",
                expected="İşletmenin ana hizmetlerini, lokasyonunu ve iletişim yolunu açıklayan özgün içerik",
                service_slugs=["seo_organic"],
                recommendation_strength="conditional",
                verification="Site JavaScript ile içerik yüklüyorsa tarayıcıda render edilmiş metni ayrıca kontrol et.",
            )
        )

    return findings, checks


def _social_profile(lead: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    social = lead.get("social") or {}
    stats = social.get("stats") or {}
    findings: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    source_url = social.get("instagram_url")
    checked_at = social.get("checked_at") or stats.get("checked_at") or lead.get("last_analyzed")
    lookup_status = social.get("lookup_status")
    identity_confidence = int(social.get("identity_confidence") or 0)

    if social.get("has_instagram") is True and identity_confidence >= 70:
        checks.append(
            _check(
                code="social.instagram_presence",
                label="Instagram kimliği",
                category="social",
                weight=10,
                status="pass",
                confidence=identity_confidence,
                note=social.get("identity_evidence") or "Instagram profili işletmeyle eşleştirildi.",
                source_url=source_url,
                checked_at=checked_at,
            )
        )
    elif social.get("has_instagram") is False and lookup_status == "not_found":
        checks.append(
            _check(
                code="social.instagram_presence",
                label="Instagram kimliği",
                category="social",
                weight=10,
                status="fail",
                confidence=72,
                note="Website ve arama sonuçlarında işletmeyle eşleşen profil bulunamadı.",
                source_url=lead.get("maps_url"),
                checked_at=checked_at,
            )
        )
        findings.append(
            _finding(
                code="social.instagram_absent",
                title="İşletmeyle doğrulanabilen Instagram profili bulunamadı",
                category="social",
                severity="medium",
                confidence=72,
                evidence="Website bağlantıları ve sınırlı profil aramasında işletme adıyla yeterli kimlik eşleşmesi bulunamadı.",
                impact="İşletmenin sosyal kanaldaki güncel içerik ve mesajlaşma noktası müşteriler tarafından kolay bulunamayabilir.",
                source_url=lead.get("maps_url"),
                checked_at=checked_at,
                observed="Eşleşen profil bulunamadı",
                expected="İşletmeyle açıkça eşleşen resmi profil",
                service_slugs=["social_media"],
                recommendation_strength="conditional",
                verification="Farklı kullanıcı adı veya gizli/yenilenmiş hesap olup olmadığını işletmeye sor.",
            )
        )
    else:
        note = (
            f"Profil var ancak kimlik güveni %{identity_confidence}; performans verisi satış kanıtı olarak kullanılmadı."
            if social.get("has_instagram") is True
            else f"Instagram kontrol durumu: {lookup_status or 'bilinmiyor'}."
        )
        checks.append(
            _check(
                code="social.instagram_presence",
                label="Instagram kimliği",
                category="social",
                weight=10,
                status="unknown",
                confidence=0,
                note=note,
                source_url=source_url or lead.get("maps_url"),
                checked_at=checked_at,
            )
        )

    sample_size = int(stats.get("engagement_sample_size") or 0)
    engagement = stats.get("engagement_rate")
    stats_verified = (
        social.get("has_instagram") is True
        and identity_confidence >= 70
        and stats.get("lookup_status") == "found"
        and sample_size >= 6
        and engagement is not None
    )
    low_engagement = stats_verified and float(engagement) < 1.0
    checks.append(
        _check(
            code="social.instagram_engagement",
            label="Instagram etkileşim örneği",
            category="social",
            weight=8,
            status="fail" if low_engagement else "pass" if stats_verified else "unknown",
            confidence=82 if stats_verified else 0,
            note=(
                f"{sample_size} gönderi örneğinde etkileşim %{engagement}."
                if stats_verified
                else "Doğru profil ve en az 6 gönderi verisi birlikte doğrulanamadı."
            ),
            source_url=source_url,
            checked_at=checked_at,
        )
    )
    if low_engagement:
        findings.append(
            _finding(
                code="social.low_engagement",
                title="Doğrulanan Instagram gönderi etkileşimi düşük",
                category="social",
                severity="medium",
                confidence=82,
                evidence=f"{sample_size} gönderi örneğinde takipçiye göre etkileşim %{engagement}.",
                impact="Mevcut kitle içerikle sınırlı etkileşim kuruyor olabilir; içerik formatı ve yayın planı incelenmeli.",
                source_url=source_url,
                checked_at=checked_at,
                observed=f"%{engagement}",
                expected="Sektör, takipçi ölçeği ve içerik tipine göre karşılaştırılacak sağlıklı etkileşim",
                service_slugs=["social_media", "reels_production"],
                recommendation_strength="conditional",
                verification="Gönderi türlerini, organik/reklam dağılımını ve son 90 günlük Instagram Insights verisini görüşmede incele.",
            )
        )
    return findings, checks


def _maps_profile(lead: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    maps = lead.get("maps") or {}
    findings: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    checked_at = maps.get("checked_at") or lead.get("last_analyzed")
    source_url = lead.get("maps_url")
    rating = lead.get("rating")
    review_count = lead.get("review_count")
    rating_status = maps.get("rating_lookup_status")
    review_status = maps.get("review_count_lookup_status")

    rating_verified = rating is not None and rating_status == "found"
    reviews_verified = review_count is not None and review_status == "found"
    reputation_checked = rating_verified and reviews_verified
    reputation_problem = (
        reputation_checked
        and int(review_count) >= 10
        and float(rating) < 3.7
    )
    checks.append(
        _check(
            code="maps.reputation",
            label="Google puan ve yorum",
            category="maps",
            weight=8,
            status="fail" if reputation_problem else "pass" if reputation_checked else "unknown",
            confidence=94 if reputation_checked else 0,
            note=(
                f"{rating}/5 puan, {review_count} yorum."
                if reputation_checked
                else "Puan ve yorum sayısı aynı işletme panelinden birlikte doğrulanamadı."
            ),
            source_url=source_url,
            checked_at=checked_at,
        )
    )
    if reputation_problem:
        findings.append(
            _finding(
                code="maps.low_rating",
                title="Google puanı anlamlı yorum örneğinde düşük",
                category="reputation",
                severity="high",
                confidence=94,
                evidence=f"Google Maps panelinde {review_count} yorum üzerinden {rating}/5 puan görünüyor.",
                impact="Yeni müşteriler işletmeyi karşılaştırırken düşük puanı güven sinyali olarak değerlendirebilir.",
                source_url=source_url,
                checked_at=checked_at,
                observed=f"{rating}/5 ({review_count} yorum)",
                expected="İşletmenin gerçek müşteri deneyimini sürdürülebilir biçimde iyileştirmesi",
                service_slugs=[],
                recommendation_strength="none",
                verification="Son yorumların ana şikayet başlıklarını ve işletme yanıtlarını manuel incele.",
            )
        )

    phone_status = maps.get("phone_lookup_status")
    if phone_status in {"found", "not_found"}:
        phone_missing = phone_status == "not_found"
        checks.append(
            _check(
                code="maps.phone",
                label="Maps telefon bilgisi",
                category="maps",
                weight=5,
                status="fail" if phone_missing else "pass",
                confidence=94,
                note="Telefon bulundu." if not phone_missing else "İşletme panelinde telefon bulunamadı.",
                source_url=source_url,
                checked_at=checked_at,
            )
        )
        if phone_missing:
            findings.append(
                _finding(
                    code="maps.phone_missing",
                    title="Google Maps panelinde telefon görünmüyor",
                    category="conversion",
                    severity="high",
                    confidence=94,
                    evidence="Seçili işletme panelinde telefon aksiyonu bulunamadı.",
                    impact="Arama sonucundan doğrudan aramak isteyen müşteri ek adım atmak zorunda kalabilir.",
                    source_url=source_url,
                    checked_at=checked_at,
                    observed="Telefon alanı yok",
                    expected="Güncel işletme telefonu",
                    service_slugs=[],
                    recommendation_strength="none",
                    verification="Google Business Profile erişimi ve telefon bilgisinin yayın durumunu işletmeyle kontrol et.",
                )
            )
    else:
        checks.append(
            _check(
                code="maps.phone",
                label="Maps telefon bilgisi",
                category="maps",
                weight=5,
                status="unknown",
                confidence=0,
                note="Telefon alanı güvenilir biçimde kontrol edilemedi.",
                source_url=source_url,
                checked_at=checked_at,
            )
        )
    return findings, checks


def analyze_lead(lead: dict[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    for builder in (_website_profile, _social_profile, _maps_profile):
        new_findings, new_checks = builder(lead)
        findings.extend(new_findings)
        checks.extend(new_checks)

    total_weight = sum(int(item["weight"]) for item in checks)
    assessed = [item for item in checks if item["status"] in {"pass", "fail"}]
    assessed_weight = sum(int(item["weight"]) for item in assessed)
    passed_weight = sum(int(item["weight"]) for item in assessed if item["status"] == "pass")
    score = round(passed_weight / assessed_weight * 100) if assessed_weight else 0
    coverage = round(assessed_weight / total_weight * 100) if total_weight else 0
    confidence = (
        round(
            sum(int(item["confidence"]) * int(item["weight"]) for item in assessed)
            / assessed_weight
        )
        if assessed_weight
        else 0
    )
    score_status = (
        "reliable"
        if coverage >= 70 and confidence >= 80
        else "partial"
        if coverage >= 35
        else "insufficient"
    )
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    findings.sort(
        key=lambda item: (
            severity_order.get(item["severity"], 9),
            -int(item["confidence"]),
            item["title"],
        )
    )
    checked_values = [item.get("checked_at") for item in checks if item.get("checked_at")]
    checked_at = max(checked_values) if checked_values else _now()
    opportunities = list(
        dict.fromkeys(
            slug
            for finding in findings
            for slug in finding.get("service_slugs", [])
        )
    )
    return {
        "version": AUDIT_MODEL_VERSION,
        "checked_at": checked_at,
        "findings": findings,
        "checks": checks,
        "summary": {
            "score": score,
            "grade": _grade(score),
            "score_status": score_status,
            "coverage": coverage,
            "confidence": confidence,
            "assessed_checks": len(assessed),
            "passed_checks": sum(1 for item in assessed if item["status"] == "pass"),
            "failed_checks": sum(1 for item in assessed if item["status"] == "fail"),
            "unknown_checks": sum(1 for item in checks if item["status"] == "unknown"),
            "total_checks": len(checks),
            "confirmed_findings": sum(1 for item in findings if item["status"] == "confirmed"),
            "likely_findings": sum(1 for item in findings if item["status"] == "likely"),
        },
        "scoring": {
            "score": score,
            "max_score": 100,
            "grade": _grade(score),
            "score_status": score_status,
            "coverage": coverage,
            "confidence": confidence,
            "issues": [item["title"] for item in findings],
            "opportunities": opportunities,
        },
    }
