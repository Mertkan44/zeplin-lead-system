# Zeplin Lead System — Ayrıntılı Sistem İnceleme Raporu

**Tarih:** 29 Eylül 2026
**Depo:** [Mertkan44/zeplin-lead-system](https://github.com/Mertkan44/zeplin-lead-system) — inceleme sırasında özel depo
**İncelenen sürüm:** `main`, `5615946b9bc55711d19e6016d0e51de355b719f1`
**Canlı adres:** [zeplin-lead-system.vercel.app](https://zeplin-lead-system.vercel.app/)
**Amaç:** Hataları, eksikleri, operasyonel riskleri ve uygulanabilir iyileştirmeleri belirlemek.

## 1. Yönetici değerlendirmesi

Sistemin temel ürün akışı yerinde: işletme keşfi, dijital varlık analizi, kanıta dayalı hizmet eşleştirme, AI raporları, müşteri atama ve görüşme takibi aynı uygulamada birleştirilmiş. Kimlik doğrulama, sunucu tarafında rol denetimi, Supabase RLS, atomik kuyruk sahiplenme ve CI kontrolleri gibi önemli temeller mevcut.

Bununla birlikte **yetki iptali, müşteri kimliği, görüşme işlemlerinin tutarlılığı ve AI üretiminin Vercel üzerinde çalışması** alanlarında öncelikli düzeltmeler gerekiyor. Mevcut testlerin geçmesi bu sorunları dışlamıyor; testler çoğunlukla yardımcı fonksiyonlara odaklanıyor.

**22 bulgu belirledim: 8 P1 ve 14 P2.** Bunlardan yedisi dış servislere bağlanmayan yerel senaryolarda yeniden üretildi. P1 sınıfındaki SQL indeks bulgusu belirli bir migration yoluna bağlıdır; canlı veritabanındaki gerçekleşme durumu doğrulanmadı. Doğrulanmış, acil bir P0 olayı tespit edilmedi.

Önerim: yeni özelliklerden önce F01–F08'i ele almak; ardından ortak satış işlem modeli, tutarlı migration kurulumu ve gerçek API/veritabanı entegrasyon testlerini tamamlamak.

### Öncelik ve kanıt tanımları

- **P1 — Yüksek:** Yetkisiz erişim, kayıt bozulması veya temel işlevin çalışmaması riski; ilk düzeltme grubuna alınmalı.
- **P2 — Orta:** İş akışı, veri doğruluğu, ölçeklenebilirlik, bakım veya güvenlik dayanıklılığı sorunu.
- **Yerel yeniden üretim:** Gerçek uygulama fonksiyonları, sahte kullanıcı/veri ve mock dış servislerle çalıştırıldı. Canlı istismar anlamına gelmez.
- **Kodla doğrulandı:** Kontrol akışı veya şema doğrudan incelendi; üretimdeki sıklığı ölçülmedi.
- **Koşullu:** Etki belirli şema, veri hacmi veya çalışma koşuluna bağlı.

## 2. Kapsam, yöntem ve sınırlar

Depo boş çalışma klasörüne klonlandı. `api/`, `src/`, SQL şemaları/migration'ları, dashboard şablonu, işçi süreci, GitHub Actions ve Vercel yapılandırması incelendi. Birim testleri, veri doğrulaması, güvenlik taraması, Python derleme kontrolü, bağımlılık taraması ve dashboard üretim tutarlılığı çalıştırıldı.

Canlı ortamda yalnızca okuma kontrolleri yapıldı. Giriş ekranı tarayıcıda görsel olarak incelendi; oturumsuz API yanıtları ve seçili kaynak dosyalarının web erişimi kontrol edildi. Gerçek kullanıcı hesabıyla giriş, müşteri kaydı değiştirme, ücretli AI/Places çağrısı, deployment veya SQL değişikliği yapılmadı.

**Doğrulama sınırları:**

- Vercel bağlayıcısında takım listesi boş döndü; proje sorgusu aracın `projectId`/`idOrName` parametre uyumsuzluğuyla başarısız oldu. Bu nedenle ortam değişkenleri, çalışma süresi limitleri, runtime logları ve hesap ayarları incelenemedi.
- GitHub commit durumundan Vercel yayınının başarılı olduğu doğrulandı. Bu, canlı deployment'ın tüm ayarlarının veya veritabanı şemasının doğrulandığı anlamına gelmez.
- Supabase'e doğrudan bağlanılmadı; canlı veri sayısı, migration durumu, yedekleme ve gerçek SQL yetkileri görülmedi.
- Giriş sonrası ekranlar kaynak kod üzerinden incelendi. Gerçek admin/satış kullanıcısıyla uçtan uca kullanım ve mobil cihaz testi yapılmadı.
- Yerel Python sürümü **3.14.4**; CI yapılandırması **3.11**. CI geçmişi ayrıca kontrol edildi.
- İnceleme güvenlik sertifikasyonu veya kapsamlı penetrasyon testi değildir; rapor erişilen kanıtların sınırları içindedir.

## 3. Doğrulama sonuçları

| Kontrol | Sonuç | Yorum |
|---|---|---|
| `python -m unittest discover -s tests -v` | **50/50 geçti** | API ve SQL entegrasyon kapsamı sınırlı. |
| `scripts/validate_data.py` | **Geçti; 49 kayıt** | Depodaki `leads_final.json`; canlı Supabase toplamı değildir. |
| `scripts/security_check.py` | **Geçti** | Çalışma ağacındaki bilinen anahtar desenlerini tarar; geçmiş/anahtar rotasyonu garantisi değildir. |
| `compileall` | **Geçti** | Python sözdizimi/derleme kontrolü. |
| `pip-audit -r requirements.txt` | **35 paket, bilinen açık bulunmadı** | 29 Eylül 2026 taramasının sonucu; mantık hatalarını kapsamaz. |
| Dashboard'u geçici konuma yeniden üretme | **Üretilen HTML mevcut `public/index.html` ile aynı** | İncelenen sürümde şablon/çıktı tutarlı. |
| Canlı ana sayfa | **HTTP 200** | Giriş ekranı görüntülendi. |
| `GET /api/auth` | **HTTP 200** | `configured=true`, `authenticated=false`. |
| Workspace, leads, users, assignments, outreach, admin_search GET | **HTTP 401** | Oturumsuz erişim engelleniyor. |
| Places cron GET, gizli anahtar olmadan | **HTTP 401** | Cron koruması çalışıyor. |
| `/leads_final.json`, `/outreach_log.json`, `/src/auth.py`, `/README.md` | **HTTP 404** | Seçili dosyalar canlı web kökünden sunulmuyor. |
| Canlı güvenlik başlıkları | **Mevcut** | HSTS, nosniff, DENY, CSP, Referrer-Policy ve Permissions-Policy görüldü. CSP istisnaları F20'de. |
| Tarayıcı konsolu | **Gözlenen hata yok; Babel uyarısı var** | Yalnızca giriş ekranı yükleme gözlemi. |
| Son CI çalışması | **Başarılı** | 1 Ağustos 2026, aşağıdaki bağlantı. |
| Son 6 arama işçisi çalışması | **Başarılı** | En son logda `queued job yok`; gerçek aramanın başarılı olduğuna kanıt değildir. |

Kaynaklar: [Son CI](https://github.com/Mertkan44/zeplin-lead-system/actions/runs/30705726362), [son incelenen işçi çalışması](https://github.com/Mertkan44/zeplin-lead-system/actions/runs/36533579617), [GitHub'da bildirilen Vercel yayını](https://vercel.com/mertkans-projects-b444ee44/zeplin-lead-system/AdEsDw3hewntzJk4qJjvJftZ7Bmf).

### Yerel yeniden üretim özeti

| Senaryo | Gözlenen davranış |
|---|---|
| Satış kullanıcısının yalnızca arşivlenmiş ataması var | Workspace **200** ile müşteri kaydını döndürdü. |
| Satış kullanıcısı kendi arşivlenmiş atamasını etkinleştiriyor | Handler **200** döndürdü ve `status=active` güncellemesini çağırdı. |
| AI önbelleğinin yerel yazımı salt okunur dosya sistemi hatası veriyor | `OSError` dışarı çıktı; Supabase önbellek yazımı **hiç çağrılmadı**. |
| Genel URL özel IP'ye yönlendiriyor | Mock HTTP taşıyıcısı özel IP isteğini **güvenlik kontrolünden önce** gördü. Gerçek özel ağa istek gönderilmedi. |
| Eski görüşme isteği yeni kazanım kaydından sonra tekrar gönderiliyor | İki tekil olay olmasına rağmen son durum `converted` yerine **`follow_up`** oldu. |
| Aynı isimli işletme tamamen farklı şehirde | Yanlış şehirdeki aday **80 güven puanıyla kabul edildi**. |
| İstanbul'da gece yarısı sonrası günlük ekip metriği | Önceki yerel güne ait bir arama **bugünün araması** sayıldı. |

## 4. Mimari değerlendirme

```text
Tarayıcı / React dashboard
        |
        v
Vercel Python API ── HMAC oturum + uygulama rol kontrolleri
        |
        +── Supabase: müşteriler, atamalar, görüşmeler, kullanıcılar,
        |             iş kuyruğu, AI önbelleği ve token kayıtları
        +── DeepSeek / isteğe bağlı Groq
        +── Google Places

GitHub Actions işçisi
        └── arama kuyruğu → Playwright keşfi → website analizi
                             → hizmet eşleştirme → AI → Supabase
```

**Güçlü yanlar:** Statik HTML'e CRM kayıtları gömülmüyor. Service-role anahtarı sunucu tarafında kullanılıyor. Parolalar salt'lı PBKDF2 ile tutuluyor; çerezler HttpOnly ve SameSite içeriyor. Kullanıcı aktifliği ve rolü isteklerde yeniden okunuyor. Ana website analizindeki yönlendirmeler tek tek kontrol ediliyor ve içerik boyutu sınırlanıyor. İş kuyruğunda `SKIP LOCKED`, atama için RPC ve audit kayıtları düşünülmüş. Hizmet kataloğu ve kanıt/bilinmeyen ayrımı, satış önerilerinin kontrolsüz üretilmesini azaltıyor.

**Temel tasarım sorunu:** Aynı iş kavramları farklı yerlerde farklı kurallarla ele alınıyor. Yetkiler endpoint'e, satış durumu işlemin başlatıldığı ekrana, veri modeli ise `raw` JSON / ilişkisel kolon / JSON biçimli not arasında değişiyor. İyileştirmenin odağı bu kuralları ortak bir işlem katmanında toplamak olmalı.

## 5. Öncelikli bulgular

### F01 — P1: Arşivlenmiş atama müşteriyi okumaya devam ediyor

**Kanıt:** [api/workspace.py:149–164](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/api/workspace.py#L149); karşılaştırma için [api/leads.py:34–40](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/api/leads.py#L34) ve [src/auth.py:196–206](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/src/auth.py#L196). **Yerel olarak yeniden üretildi.**

Workspace satış kullanıcısının atamalarını durum filtresi olmadan getiriyor ve bu atamaların tamamından müşteri erişim listesi oluşturuyor. Diğer ilgili endpoint'ler ise aktif atama arıyor. Müşteri A çalışanından B çalışanına devredildiğinde A'nın arşivlenmiş ataması, müşterinin güncel bilgilerini ve görüşmelerini okumaya devam etmesine neden oluyor.

**Düzeltme:** Okuma ve yazma yetkisini tek fonksiyonda tanımlayın. Aktif sahiplik ile geçmiş faaliyet görüntüleme hakkını ayırın. Geçmiş erişimi ürün gereği isteniyorsa yalnızca izin verilen tarihsel alanları döndürün.

**Kabul testi:** A → B devir işleminden sonra A, workspace ve tekil müşteri API'lerinde müşterinin yeni verisini görememeli; B erişebilmeli.

### F02 — P1: Çalışan kendi iptal edilmiş atamasını yeniden etkinleştirebiliyor

**Kanıt:** [api/assignments.py:94–128](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/api/assignments.py#L94); [src/storage/supabase.py:477–501](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/src/storage/supabase.py#L477). **Handler düzeyinde yerel yeniden üretim.**

PATCH yalnızca atama satırındaki e-postanın kullanıcıyla eşleşmesini kontrol ediyor. Mevcut durumun `archived` veya `done` olması, çalışanın `active` göndermesine engel değil. Başka aktif sahip bulunmayan bir müşteride çalışan admin'in kapattığı erişimi geri kazanabilir. Başka aktif sahip varsa migration 006'nın tek aktif sahip indeksi işlemi engelleyebilir; bu, eksik API yetki kuralını gidermez.

**Düzeltme:** Rol ve mevcut duruma göre açık geçiş matrisi uygulayın. Arşivden dönüş ve sahipliğin yeniden açılması admin işlemi olsun. Yetkiyi ve geçişi mümkünse aynı SQL işleminde doğrulayın.

**Kabul testi:** Satış kullanıcısı `archived → active` için 403 almalı; admin geçişi kayıt altına alınmalı.

### F03 — P1: AI üretimi Vercel'in salt okunur dosya sistemiyle uyumsuz

**Kanıt:** [src/ai/cache.py:11,32–34,65–97](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/src/ai/cache.py#L11); [src/ai/generator.py:238–258](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/src/ai/generator.py#L238); [api/lead_ai.py:67–76](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/api/lead_ai.py#L67). **Dosya sistemi hatası yerel olarak simüle edildi.**

Yeni üretimden sonra önce proje kökündeki `.cache/ai_generations.json` yazılıyor. Bu işlem, Supabase'e yazım için kullanılan `try` bloğunun dışında. Yazma başarısızsa üretilmiş yanıt kaydedilmeden fonksiyondan hata çıkıyor. Uzak önbellekte zaten bulunan yanıtlar sorunu gizleyebilir; yeni raporlar etkilenir.

Vercel Functions dosya sistemi salt okunurdur; geçici yazım için `/tmp` sunulur. Bu platform koşulu ve yerel kontrol akışı birlikte değerlendirildiğinde sorun yüksek önceliklidir. Üretimde ücretli AI çağrısı yapılarak doğrulanmadı. [Vercel runtime belgeleri](https://vercel.com/docs/functions/runtimes).

**Düzeltme:** Supabase'i kalıcı önbellek yapın. Yerel önbelleği isteğe bağlı ve hata toleranslı kullanın; gerekiyorsa `/tmp` seçin. Önbellek arızası başarılı AI yanıtını kaybettirmemeli.

**Kabul testi:** Yerel dosya yazımı yasakken yeni rapor üretilebilmeli, uzak kayıt yapılmalı ve endpoint başarılı dönmeli.

### F04 — P1: Bazı araştırma yolları özel ağ URL'lerine erişimi engellemiyor

**Kanıt:** [src/research.py:38–47](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/src/research.py#L38); [src/audit/finder.py:447–476](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/src/audit/finder.py#L447); güvenli örnek `src/audit/website.py` içindeki `_fetch_public`. **HTTP yönlendirme sırası mock taşıyıcıyla yeniden üretildi.**

`research_website`, `follow_redirects=True` ile hedefe gittikten sonra son URL'yi kontrol ediyor. Genel bir site özel IP'ye yönlendirirse erişim zaten gerçekleşmiş oluyor. Ayrıca `find_instagram`, işletmenin website URL'sini doğrudan Playwright ile açıyor; bu yolda eşdeğer URL ve alt kaynak denetimi görünmüyor.

**Etki:** Araştırma işçisinin ulaşabildiği yerel/özel ağ kaynaklarına istek gönderme riski. Erişilebilir gerçek kaynaklar çalıştırma ortamına bağlıdır. Yerel kontrolde hiçbir gerçek özel ağ isteği yapılmadı.

**Düzeltme:** Ortak güvenli HTTP istemcisi kullanın; her yönlendirmeyi istekten önce doğrulayın. Browser tabanlı araştırmada navigasyon ve alt kaynaklar için ağ kısıtları koyun. DNS kontrolü ile bağlantı arasındaki adres değişimi riskini de değerlendirin. `research_website` için indirme boyutu sınırı ekleyin.

**Kabul testi:** Genel URL → özel IP yönlendirmesinde taşıyıcıya ikinci istek ulaşmamalı.

### F05 — P1: İşletme adı müşteri kimliği olarak kullanılıyor

**Kanıt:** [supabase/schema.sql:4–8,147–157](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/supabase/schema.sql#L4); [src/storage/supabase.py:53–110](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/src/storage/supabase.py#L53); `besiktas.py:189–203`. **Kod ve şema ile doğrulandı.**

`external_id` üretilmesine rağmen Supabase upsert hâlâ `on_conflict=name` kullanıyor; ad kolonu tekil ve atamalar da ada bağlı. Yerel birleştirme de işletme adı üzerinden yapılıyor. Farklı şehirlerdeki aynı adlı iki işletme ayrı müşteri olarak saklanamaz; sonraki tarama öncekinin adresini, analizini ve iletişim bilgisini değiştirebilir.

Ayrıca migration 006 mevcut kayıtlara `maps:` / `name:` önekli kimlik yazarken Python `name-city:` üretiyor. Kimlik stratejisi tutarlı değil. Ad+şehir de aynı şehirdeki şubeleri tek başına ayıramaz.

**Düzeltme:** Değişmez `lead_id` üzerinden ilişkileri kurun. Kaynak kimliği olarak güvenilir Places ID gibi bir alanı ayrı unique tutun; yoksa şube ayrımını içeren kontrollü eşleştirme kullanın. Ad, güncellenebilir görüntüleme alanı olsun.

**Kabul testi:** Aynı adlı farklı şehir/şube kayıtları ayrı kalmalı; isim değişikliği görüşmeleri ve atamaları koparmamalı.

### F06 — P1: Görüşme kaydı atomik değil; tekrar gönderim satış durumunu geriye çevirebiliyor

**Kanıt:** [api/outreach.py:99–132](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/api/outreach.py#L99); [src/storage/supabase.py:181–194](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/src/storage/supabase.py#L181); [src/dashboard/template.html:237,246–253](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/src/dashboard/template.html#L237). **Tekrar gönderim etkisi yerel olarak yeniden üretildi.**

Önce görüşme ekleniyor, sonra müşteri durumu, sonra atama güncelleniyor. Bunlar ayrı HTTP/veritabanı işlemleri. Ortadaki hata kısmen kaydedilmiş bir işlem bırakıyor. `idempotency_key` tekrar eden olay satırını engellese de sonraki durum güncellemelerini engellemiyor.

Örnek: A isteği `no_answer`, B isteği `won`, ardından aynı anahtarla A tekrarı. Yeni olay eklenmese bile durum tekrar `follow_up` olabiliyor. Tarayıcının `Date.now()` tabanlı genel anahtarı da farklı kullanıcıların aynı milisaniyedeki işlemlerinde çakışabilir.

**Düzeltme:** Olay, müşteri durumu ve atamayı tek transaction/RPC içinde işleyin. Tekrar gelen anahtar önceki işlem sonucunu dönsün ve yeni yan etki üretmesin. İstemci UUID kullansın; anahtar aktör/işlem kapsamıyla bağlansın. Yeni olaydan eski bir olayın durumu geri almaması için sürüm veya sıra denetimi ekleyin.

**Kabul testi:** Her adımda hata enjeksiyonu tam rollback sağlamalı; eski isteğin tekrarı kazanılmış satışı yeniden açmamalı.

### F07 — P1, koşullu: Eski kurulumdaki idempotency indeksi upsert ile uyumsuz

**Kanıt:** [supabase/migrations/006_security_crm_hardening.sql:22–29](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/supabase/migrations/006_security_crm_hardening.sql#L22); [src/storage/supabase.py:181–193](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/src/storage/supabase.py#L181); karşılaştırma [supabase/schema.sql:50](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/supabase/schema.sql#L50). **SQL/kod uyumsuzluğu; canlı şemada doğrulanmadı.**

Migration 006, `idempotency_key IS NOT NULL` koşullu unique indeks oluşturuyor. API ise PostgREST'e yalnızca `on_conflict=idempotency_key` gönderiyor. Aynı kolon üzerinde koşulsuz unique indeks/constraint bulunmayan eski kurulumda PostgreSQL'in conflict target eşleştirmesi başarısız olabilir. Yeni `schema.sql` içindeki koşulsuz unique tanımı bu nedenle farklı davranır.

**Düzeltme:** Migration ve yeni kurulum şemasını aynı koşulsuz unique tanıma getirin veya koşullu conflict hedefini açık yazan RPC kullanın. Mevcut tekrarları önce tespit edin. [PostgreSQL ON CONFLICT / indeks eşleştirme belgeleri](https://www.postgresql.org/docs/current/sql-insert.html#SQL-ON-CONFLICT).

**Kabul testi:** Hem eski şemadan migration hem sıfırdan kurulum üzerinde anahtarlı ilk kayıt ve tekrar kayıt entegrasyon testi geçmeli.

### F08 — P1: Places eşleştirmesi farklı şehirdeki aynı adlı işletmeyi kabul ediyor

**Kanıt:** [src/integrations/google_places.py:49–78,139–155](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/src/integrations/google_places.py#L49). **Yerel olarak yeniden üretildi.**

İsim benzerliği %80, konum benzerliği %20 ağırlıklı; kabul eşiği 72. İsim tam eşleştiğinde konum skoru sıfır olsa bile toplam 80 oluyor. Sentetik Ankara müşterisi için İzmir adayı kabul edildi. Sonraki birleştirme adresi, Maps URL'sini, puanı ve yorum sayısını değiştirebiliyor; workflow bunu doğrulanmış Places verisi sayıyor.

**Düzeltme:** Güçlü konum uyuşmazlığını puandan bağımsız ret nedeni yapın. Önceden doğrulanmış Place ID varsa onu kullanın. Koordinat/ilçe/adres ve adaylar arasındaki skor farkıyla eşleştirme yapın; belirsiz durumda kullanıcı doğrulaması isteyin.

**Kabul testi:** İsim tam aynı olsa da farklı şehir adayı otomatik kabul edilmemeli; aynı markanın şubeleri ayrı test edilmeli.

## 6. Diğer hatalar ve eksikler

### F09 — P2: Sıfırdan kurulum tarifi gereken RPC'leri oluşturmuyor

**Kanıt:** `README.md:20–24`; `supabase/schema.sql`; [supabase/migrations/006_security_crm_hardening.sql:128–305](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/supabase/migrations/006_security_crm_hardening.sql#L128); [src/storage/supabase.py:466–474](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/src/storage/supabase.py#L466).

README yeni projeye yalnızca `schema.sql` uygulanmasını söylüyor. Bu dosyada tablolar var, fakat `assign_lead_owner`, kuyruk sahiplenme ve login rate-limit RPC'leri yok. Bazı çağrıların geriye uyumluluk yolu var; atama RPC'sinin yok. Tek aktif sahip indeksi ve güncelleme trigger'ları da migration 006'da.

**Öneri:** Tek bir kurulum/migration komutu ve şema sürüm tablosu oluşturun. Temiz veritabanı kurulumunu CI'da çalıştırın. Migration 007'nin isteğe bağlı olduğunu ve yapılandırılmış alanların uygulamada henüz kullanılmadığını belgeleyin.

**Kabul:** README adımlarıyla kurulan boş veritabanında kullanıcı/atama/görüşme/kuyruk/rate-limit işlemleri çalışmalı.

### F10 — P2: Önce limit, sonra yetki filtresi uygulanıyor; veriler sessizce eksiliyor

**Kanıt:** [src/storage/supabase.py:213–247](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/src/storage/supabase.py#L213); [api/leads.py:31–42](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/api/leads.py#L31); [api/outreach.py:52–61](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/api/outreach.py#L52); [api/workspace.py:149–164](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/api/workspace.py#L149); [api/lead_ai.py:51](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/api/lead_ai.py#L51); `api/place_refresh.py`.

Müşteriler ve görüşmeler önce tüm sistemden 500/1000 adet çekiliyor, sonra kullanıcıya veya müşteriye göre filtreleniyor. Çalışanın müşterisi bu pencerenin dışında kaldığında görünmüyor. Eski manuel doğrulama olayı son 1000 görüşme arasında değilse müşteri tekrar eksik doğrulanmış görünebilir. Tekil AI/Places işlemleri de tüm müşteri listesini aradığı için mevcut kayıt için 404 dönebilir.

**Öneri:** Yetki ve müşteri filtresini sorguya taşıyın; cursor pagination ekleyin. Sayaçları SQL aggregate, son doğrulamayı tekil sorgu/özet tablo üzerinden üretin.

**Kabul:** 1500 müşteri ve 3000 olayla atanmış müşteriler, doğru toplamlar ve son doğrulama durumu eksiksiz görünmeli.

### F11 — P2: Tam kayıt upsert'i eşzamanlı zenginleştirmeleri ezebilir

**Kanıt:** [api/lead_ai.py:51–76](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/api/lead_ai.py#L51); `api/place_refresh.py` içindeki `_refresh_one`; [src/storage/supabase.py:53–110](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/src/storage/supabase.py#L53).

AI ve Places kayıtları okuyup zenginleştiriyor, sonra `raw` dahil geniş bir kayıt kümesini yeniden yazıyor. İki işlem aynı başlangıç kopyasını okursa son yazan diğerinin eklediği alanları silebilir. Tarama da mevcut uzak araştırma/AI bilgilerini koruyan alan bazlı bir birleştirme yapmıyor.

**Öneri:** İşlem bazlı alan güncellemeleri ve optimistic concurrency kullanın; örneğin `version` veya `updated_at` önkoşulu. `raw` ile kolonların hangi alan için kaynak olduğu açık olsun.

**Kabul:** Eşzamanlı AI ve Places güncellemesi sonunda iki işlemin verisi de korunmalı; eski sürümle yazma sessizce kabul edilmemeli.

### F12 — P2: AI raporunun güncelliği veri değişiminden bağımsız kontrol ediliyor

**Kanıt:** [api/lead_ai.py:62–69](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/api/lead_ai.py#L62); [src/ai/generator.py:201–237,326–341](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/src/ai/generator.py#L201).

Endpoint mevcut raporun prompt sürümü aynıysa ve gerekli metinler varsa doğrudan eski raporu dönüyor. Lead verisi değişse bile alttaki içerik parmak izi hesabına ulaşılmayabiliyor. API tarafından üretilen rapor ayrıca `last_analyzed` zamanını güncellemiyor. Üretim yolunda negatif e-posta sonucu için açık bir tamamlanma durumu yok; bilinçli olarak taslak üretilmemesi sürekli yeniden işleme koşuluna dönüşebilir.

**Öneri:** `input_fingerprint`, `generated_at`, `generation_status`, `prompt_version` saklayın. Endpoint parmak izini karşılaştırsın; `insufficient_evidence` gibi geçerli sonuçları da önbelleğe alın. Prompta konan tüm değişkenler önbellek kimliğine dahil olsun.

**Kabul:** Aynı veri cache hit, değişmiş kanıt yeni üretim, yetersiz kanıt ise tekrar ücretli çağrı gerektirmeyen açık sonuç vermeli.

### F13 — P2: AI maliyet kaydı eksik ve yapılandırma adları tutarsız

**Kanıt:** [scripts/process_search_jobs.py:16–38](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/scripts/process_search_jobs.py#L16); [src/ai/cache.py:100–114](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/src/ai/cache.py#L100); [src/storage/supabase.py:763–806,857–872](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/src/storage/supabase.py#L763); `.env.example:12–13`; `api/lead_ai.py`.

İşçi maliyeti yerel önbelleğin önce/sonra token toplamından çıkarıyor. Başarısız işte tüketilen tokenlar kayıt aşamasına ulaşmayabilir; dashboard AI üretimi ledger'a yazılmıyor. `usage_totals()` alanı `cached_tokens` üretirken `record_token_usage()` başka alan adlarını okuyor; cache indirimli tokenlar yanlış ücretlenebilir. Örnek env dosyasındaki `DEEPSEEK_INPUT_PRICE_PER_MILLION` / `OUTPUT_PRICE_PER_MILLION`, kodun okuduğu `*_USD_PER_M_TOKENS` adlarıyla eşleşmiyor. `smart` gibi modlar gerçek model yerine kaydedilebiliyor.

Rezervasyon kaydı ayrıca bütçe sınırı uygulamıyor; yalnızca tahmini tutarı kaydediyor. Manuel AI/Places işlemlerinde de uygulama düzeyinde tüketim kotası görünmüyor.

**Öneri:** Her sağlayıcı çağrısını ayrı üretim kimliğiyle kaydedin; gerçek model, input/output/cache tokenları ve sonuç durumu tutulsun. Günlük/proje bütçesi kontrolü ve eşzamanlı üretim kilidi ekleyin. Tarife/env adlarını tekleştirin; tahmin ile fiili tüketimi ayrı gösterin.

**Kabul:** Başarılı, başarısız, fallback ve dashboard üretimleri ledger ile uzlaşmalı; env fiyat değişikliği hesaplamaya yansımalı.

### F14 — P2: Günlük raporlarda İstanbul ve UTC gün sınırı farklı

**Kanıt:** [src/workflow.py:155–186](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/src/workflow.py#L155); [api/workspace.py:38–50](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/api/workspace.py#L38). **Yerel olarak yeniden üretildi.**

Workspace günlük özeti İstanbul tarihini kullanırken ekip performansı UTC tarihini kullanıyor. İstanbul'da 00:00–02:59 arasında iki bölüm farklı günün faaliyetlerini sayabiliyor. Sentetik gece yarısı senaryosunda önceki yerel güne ait arama bugüne yazıldı.

**Öneri:** Depolama UTC, iş günü hesabı ortak `Europe/Istanbul` yardımcı fonksiyonu olsun. Zaman dilimi içermeyen tarihleri açık kuralla kabul edin veya reddedin.

**Kabul:** İstanbul 23:59/00:00 ve UTC gün geçişi sınır testleri tüm özetlerde aynı sonucu vermeli.

### F15 — P2: Pipeline ve görüşme merkezi aynı satış sonucunu farklı işliyor

**Kanıt:** [src/dashboard/template.html:246–253,2824–2847](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/src/dashboard/template.html#L246); [api/outreach.py:87–132](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/api/outreach.py#L87); [src/workflow.py:192–216](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/src/workflow.py#L192); `api/status.py`.

Pipeline sürükle-bırak `deal_won`/`deal_lost` gibi genel olaylar ekliyor ve ayrı istekle durumu değiştiriyor. Görüşme merkezi ise `contact_result_recorded` üzerinden müşteri durumunu ve atamayı birlikte yönetiyor. Ekip `won_total` hesabı yalnızca ikinci biçimi sayıyor. Böylece pipeline'dan kazanılan müşteri ekip performansına yansımayabilir; ataması aktif kalabilir. Eski takip olayı da sonlandırılmadığı için takip sayaçlarıyla çelişebilir.

Zorunlu kaynak kontrolleri sunucuda görüşme kaydının önkoşulu olarak uygulanmıyor; arayüzdeki hazır olma kuralı API üzerinden aşılabiliyor.

**Öneri:** `record_contact`, `close_deal`, `reopen_lead` gibi ortak sunucu işlemleri tanımlayın. Bütün ekranlar aynı işlemleri çağırsın. Doğrulama önkoşulunu ve admin istisnasını sunucuda tanımlayın.

**Kabul:** Bir fırsat hangi ekrandan kazanılırsa kazanılsın durum, atama, takip ve ekip istatistiği aynı olmalı.

### F16 — P2: Çıkışta CRM verileri tarayıcı belleğinde ve localStorage'da kalıyor

**Kanıt:** [src/dashboard/template.html:153–211,336–345,3983–3991](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/src/dashboard/template.html#L153).

Görüşme notları ve durumlar kullanıcıya özel olmayan localStorage anahtarlarına yazılıyor. Çıkış sadece oturumu/React auth durumunu değiştiriyor; global `leads`, `outreachEvents`, `remoteStatuses`, `apiReady` ve yerel kayıtlar temizlenmiyor. Yeni girişte başarılı workspace yüklemesi verileri yeniliyor; fakat ortak bilgisayarda veri kalıntısı devam ediyor. Bu bulgu, başarılı giriş sonrası başka kullanıcının verilerinin mutlaka ekranda gösterildiği iddiası değildir.

**Öneri:** CRM verilerini kalıcı tarayıcı depolamasında tutmayın veya gerekçeli, kullanıcı kapsamlı ve süreli tutun. Çıkışta, 401'de ve kullanıcı değişiminde tüm CRM durumunu temizleyin. Tema tercihini ayrı bırakın.

**Kabul:** Admin çıkışından sonra yeni kullanıcı/yenileme/ağ hatası senaryolarında önceki görüşme içeriği uygulama önbelleğinde bulunmamalı.

### F17 — P2: API alan tipleri ve hata sınıfları tutarlı doğrulanmıyor

**Kanıt:** [src/http_api.py:33–43](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/src/http_api.py#L33); [api/auth.py:60–78](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/api/auth.py#L60); [api/users.py:71–85,126–143](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/api/users.py#L71); [api/status.py:47–51](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/api/status.py#L47).

JSON nesnesi kontrol ediliyor fakat alan bazlı şema yok. Örneğin e-posta için liste verilmesi `.strip()` çağrısını bozabilir; bazı yerlerde bu genel hata yakalamanın dışında. `bool("false")` gerçek boolean `false` gibi davranmaz. `read_json` uygulama seviyesinde gövde limiti uygulamıyor. Geçersiz durum kimi endpoint'lerde istemci hatası yerine 502 oluyor. Kullanıcı PATCH işleminde aktiflik, diğer alanlar doğrulanmadan değiştirilebiliyor.

**Öneri:** İstek şemaları, string uzunlukları, gerçek boolean tipleri, tarih ve enum doğrulaması kullanın. Tüm doğrulama yazımdan önce tamamlansın. 400/401/403/404/409/429/5xx ayrımı standartlaşsın.

**Kabul:** Yanlış tipler ve geçersiz enumlar kontrollü 400/422 vermeli; hatalı çok alanlı istek hiçbir alanı değiştirmemeli.

### F18 — P2: Hesap yaşam döngüsü ve giriş sınırlaması güçlendirilmeli

**Kanıt:** [src/auth.py:42–48,209–240](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/src/auth.py#L42); [api/auth.py:66–70](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/api/auth.py#L66); [api/users.py:65–96,126–152](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/api/users.py#L65); [src/storage/supabase.py:557–605](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/src/storage/supabase.py#L557).

Parola oluşturma yalnızca boş olmamayı kontrol ediyor. Son aktif admin'i devre dışı bırakma veya rolünü düşürme engeli yok. Rate-limit anahtarı IP+e-posta bileşimi; tek başına hesap ve toplam IP sınırı uygulanmıyor. Kalıcı limiter erişilemezse süreç içi sayaçlara düşülüyor; serverless örnekleri bu sayacı paylaşmıyor. Kontrol ve giriş denemesini kaydetme de ayrı adımlar.

**Öneri:** Parola politikası, son admin koruması, kontrollü parola sıfırlama ve admin için ek doğrulama tasarlayın. Hesap/IP/genel hız limitlerini birlikte uygulayın; kalıcı limit servisinin arızasında sessiz zayıflama yerine ölçülebilir korumalı davranış belirleyin. Çıkışta sunucu tarafında oturum iptal gereksinimini de netleştirin.

**Kabul:** Tek karakterli parola reddedilmeli; son admin kapatılamamalı; limiter kesintisi ve eşzamanlı denemeler test edilmeli.

### F19 — P2: İşçi başarı durumu gerçek iş sonucunu tam yansıtmıyor

**Kanıt:** [scripts/process_search_jobs.py:15–39](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/scripts/process_search_jobs.py#L15); `besiktas.py:163–183,232–244`; `.github/workflows/process-search-jobs.yml`.

Tarama bazı AI hatalarını `failures` listesine koyup normal dönebiliyor. İşçi bu sonuç için yine `success` yazıyor. Token kaydı veya son durum güncellemesi hata verirse tarama tamamlanmış olsa da iş `running` kalabilir. İşler topluca sahiplenilip sırayla yürütülüyor; kesilen süreçte henüz başlamamış işler de bekler. Migration 006 bir saat sonra kurtarma sağlıyor, ancak heartbeat/deneme sınırı ve ayrı hata kuyruğu yok.

Son altı zamanlayıcı çalışması arasındaki gözlenen aralıklar yaklaşık **4–8 saat**; yapılandırma `*/15` olsa da gerçek zamanlar 15 dakika düzeninde değil. Neden bu incelemeyle belirlenemedi. Son başarılı run yalnızca kuyruğun boş olduğunu gösteriyor.

**Öneri:** `partial_success`, aşama, ilerleme, heartbeat, deneme sayısı ve hata sınıfını tutun. Başarı ölçütünü bulunan/analiz edilen/AI üretilen/senkronize edilen sayılarla belirleyin. Kuyruk yaşına alarm ve güvenilir tetikleme mekanizması ekleyin.

**Kabul:** Tüm AI çağrıları hata verdiğinde tam başarı görünmemeli; işçi kesilip tekrar başladığında tamamlanmış yan etkiler tekrarlanmamalı.

### F20 — P2: Frontend üretim derlemesi ve güvenlik politikası zayıf

**Kanıt:** [src/dashboard/template.html:104–106,129](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/src/dashboard/template.html#L104); `vercel.json`; canlı tarayıcı konsolu.

Yaklaşık 4021 satırlık tek HTML içinde React/JSX, stil ve iş kuralları bulunuyor. React ve Babel CDN'den alınıyor; JSX tarayıcıda derleniyor. Konsolda bunun üretim için uygun olmadığı uyarısı görüldü. CSP `unsafe-inline` ve `unsafe-eval` içeriyor; script etiketlerinde SRI yok. Bu, tek başına doğrulanmış bir XSS açığı değil; saldırı etkisini azaltan korumaların zayıf olmasıdır.

**Öneri:** React/JSX'i build aşamasında derleyin; bağımlılıkları sabitleyip kendi asset'lerinizle sunun. Bileşen/API/state katmanlarını ayırın. Ardından eval gereksinimini kaldırıp CSP'yi sıkılaştırın. Şablon üretimini CI ile deployment arasında zorunlu ve otomatik hale getirin.

**Kabul:** Babel runtime uyarısı olmamalı, `unsafe-eval` gerekmemeli; CDN kesintisi uygulama JS'ini engellememeli.

### F21 — P2: Testler kritik entegrasyon sınırlarını korumuyor

**Kanıt:** `tests/test_hardening.py`; `.github/workflows/ci.yml`; bu rapordaki yedi yeniden üretim.

50 test değerli iş kuralı kontrolleri içeriyor fakat API handler yetkileri, gerçek SQL migration yolları, transaction/tekrar gönderim, serverless dosya sistemi ve browser iş akışları kapsanmıyor. CI'daki tek işletme adıyla statik veri sızıntısı araması da genel bir sızıntı kontrolü değil. Python bağımlılıklarının doğrudan sürümleri sabit; transitif paketler için tam kilit dosyası yok.

**Öneri:** Önce F01–F08 için regresyon testleri; sonra geçici PostgreSQL üzerinde iki kurulum yolu ve rol matrisi; en son admin atama → satış doğrulama → görüşme → takip → kazanım uçtan uca testi ekleyin. Temsili anonim fixture kullanın. Python ve frontend bağımlılıklarını tekrarlanabilir kurun.

**Kabul:** Bu incelemede üretilen hatalı davranışlar CI'da başarısız test olarak yakalanmalı; düzeltmeler sonrası geçmeli.

### F22 — P2: Veri güncelliği, kaynak önceliği ve doğrulama süreleri net değil

**Kanıt:** [src/integrations/google_places.py:139–155](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/src/integrations/google_places.py#L139); [api/place_refresh.py:99–113](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/api/place_refresh.py#L99); [src/workflow.py:81–104](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/src/workflow.py#L81); `supabase/migrations/007_sales_workspace.sql`; [src/storage/supabase.py:177–179,234–240](https://github.com/Mertkan44/zeplin-lead-system/blob/5615946b9bc55711d19e6016d0e51de355b719f1/src/storage/supabase.py#L177).

Places yeni telefon ve website bulsa bile dolu eski değerler korunuyor. Bu koruma manuel düzeltmeyi saklamak için anlamlı olabilir; ancak kaynağı ayırmadığı için yanlış/eski iletişim bilgisi de kalıyor. Günlük varsayılan 5 kayıt, 30 günde en fazla 150 yenileme sağlar; daha büyük veri setinde 30 günlük tazelik hedefi karşılanamaz. Manuel doğrulamalar için Places'teki gibi süre aşımı görünmüyor.

Migration 007 yapılandırılmış görüşme kolonları ve takip indeksleri ekliyor; mevcut yazma/okuma kodu bunları kullanmak yerine `note` içindeki önekli JSON'u işliyor. Böylece veritabanında takip sorguları ve raporlama güçleşiyor.

**Öneri:** Alan bazında kaynak, son kontrol zamanı ve manuel override saklayın. Çelişen telefon/website için inceleme görevi açın. Tazelik hedefini kayıt hacmine göre planlayın. Yapılandırılmış görüşme alanlarına kontrollü geçiş ve geçmiş kayıt backfill'i yapın.

**Kabul:** Yanlış numara, değişen website, süresi geçmiş manuel doğrulama ve 150'den büyük kayıt kümesi için açık ve test edilmiş davranış olmalı.

## 7. Ürün ve kullanım deneyimi önerileri

Bunlar doğrulanmış güvenlik açıklarından ayrı geliştirme önerileridir.

1. **Girişte gerçek veri izlenimi veren sıfır sayaçlarını kaldırın.** Oturum öncesi boş bootstrap nedeniyle “0 aktif lead / 0 kazanıldı / ~0 ₺” gösteriliyor; bu canlı veri yokmuş izlenimi veriyor. Giriş ekranında kısa ürün açıklaması yeterli.
2. **Rol seçimini sadeleştirin.** Yetki veritabanındaki rolden geliyor; kullanıcıdan yönetici/çalışan seçmesi istenmesi gereksiz beklenti yaratıyor. Tek giriş sonrası role göre yönlendirme daha anlaşılır.
3. **Takip görevine durum ve sorumlu ekleyin.** Yalnızca tarih hesaplamak yerine açık/tamamlandı/ertelendi ve tamamlanma nedeni tutun. Geciken takiplerin yöneticide görünmesi ve gerekiyorsa bildirim üretilmesi ayrı bir özellik olsun.
4. **Kayıt hatalarını görünür yapın.** Pipeline güncelleme hatası yalnızca konsola yazılıyor; bazı aksiyonlarda `.catch(() => {})` var. Kullanıcı “kaydedildi / kaydedilemedi / yeniden dene” durumunu görmeli.
5. **Sayfa açıkken verinin eskimesini ele alın.** Dashboard ilk açılış ve kendi işlemleri sonrasında yenileniyor. Sekmeye dönüşte kontrollü yenileme veya uygun polling ve “son güncelleme” zamanı eklenebilir.
6. **Fırsat değeri ile gerçek satış gelirini ayırın.** Katalogdan hesaplanan potansiyel değer; teklif, kabul edilen tutar ve tahsilatla aynı metrik olmamalı. Gerçek satış raporu için fırsat/teklif tutarı alanları gerekir.
7. **İletişim tercihleri ve tekrar temas kontrolü ekleyin.** Aranmak istemeyen müşteri, yanlış kanal ve tekrar temas kuralları tek merkezde tutulsun. “İlgilenmedi” kaydı sonraki yeniden atama/tarama ile etkisizleşmemeli.
8. **Erişilebilirlik testi planlayın.** Giriş sonrası modal odak yönetimi, klavyeyle pipeline alternatifi, form hata bağlantıları ve mobil düzen gerçek kullanıcı akışıyla test edilmeli. Bu rapor bunların tamamının başarısız olduğunu iddia etmiyor.
9. **Eski çalıştırma yollarını netleştirin.** `src/dashboard/app.py` sınırlı Flask API'si içeriyor; ana paneldeki auth/workspace uçlarını sağlamıyor. Desteklenen yerel çalışma komutu tek olsun; eski yol kaldırılmalı veya açıkça geliştirme aracı olarak işaretlenmeli.

## 8. Veri ve operasyon önerileri

### Depodaki veri ile canlı veriyi ayırın

Depoda `leads_final.json` yaklaşık **2,48 MB / 49 kayıt**; ayrıca `leads_raw.json` ve `leads_audited.json` da Git tarafından izleniyor. `.gitignore` içinde bu desenlerin bulunması, önceden izlenen dosyaları takipten çıkarmaz. 49 kaydın 46'sında telefon var. Yerel snapshot'ta dolu `ai_report` ve `ai_email` sayısı sıfır; bunun canlı Supabase'de de böyle olduğu söylenemez. `last_analyzed` değerleri Mayıs–Temmuz 2026 aralığında.

Üretim verisini uygulama deposundan ayırın; test için anonim fixture kullanın. GitHub deposu inceleme sırasında özel ve seçili veri yolları canlı sitede 404 olduğundan burada doğrulanmış kamusal veri sızıntısı iddiası yoktur.

### Secret geçmişi ve rotasyon

`SECURITY.md` geçmişte bir Groq anahtarının commit edildiğini söylüyor. Mevcut çalışma ağacı taraması temiz çıktı; `.env` yoluna ait geçmiş sorgusunda kayıt görülmedi. Bu iki kontrol, eski anahtarın iptal edildiğini veya başka yollarda hiç sır bulunmadığını kanıtlamaz. Rotasyon durumunu sağlayıcı tarafında doğrulayın; gerekiyorsa geçmiş taramasını ayrı bakım işi olarak yapın. Rapora hiçbir secret değeri alınmadı.

### İzleme ve kurtarma

- API latency/error oranı, AI hata oranı, maliyet, kuyruk yaşı ve takip gecikmesi için ölçümler belirleyin.
- Audit yazımı hata verdiğinde uygulama işlemini bozmaması olumlu; ancak hatanın sessizce kaybolması yerine ayrı sayaç/log üretin.
- Yedek/PITR, geri yükleme tatbikatı ve migration rollback planını doğrulayın. Kod deposu veritabanı yedeği yerine geçmez.
- Preview ile production Supabase/AI ortamlarının ayrıldığını kontrol edin; bu incelemede ortam değerlerine erişilmedi.
- Ham sağlayıcı hatalarının loglarda müşteri metni veya URL bilgisi taşımasını sınırlayın; correlation ID ile izleme kullanın.

## 9. Önerilen uygulama sırası

| Aşama | Kapsam | Tamamlanma ölçütü |
|---|---|---|
| **1 — Erişim ve çalışma engelleri** | F01, F02, F03, F04; F07'nin canlı şemada kontrolü | Eski sahip erişemiyor; çalışan erişimini geri açamıyor; yeni AI raporu salt okunur ortamda üretiliyor; yönlendirme koruması çalışıyor. |
| **2 — Veri bütünlüğü** | F05, F06, F08, F09, F11 | Değişmez müşteri kimliği, tek atomik satış işlemi, güvenilir Places eşleştirmesi, tekrarlanabilir kurulum. |
| **3 — İş akışı doğruluğu** | F10, F12–F19, F22 | Doğru sayaçlar, eksiksiz sayfalama, güncel raporlar, tutarlı takip, görünür işçi hataları ve maliyet kaydı. |
| **4 — Bakım ve deneyim** | F20, F21 ve ürün önerileri | Derlenen frontend, sıkılaştırılmış CSP, entegrasyon/E2E testleri, ölçülebilir performans ve kurtarma planı. |

Süre tahmini; canlı şema, veri miktarı ve beklenen iş kuralları görüldükten sonra verilmelidir. Özellikle müşteri kimliği geçişi, mevcut atama ve görüşmeleri koruyan veri migration'ı gerektirir.

## 10. Canlı ortamda tamamlanması gereken kontroller

- [ ] Vercel proje erişimi düzeltilerek deployment SHA, function süreleri/bölgesi ve ortam değişkeni **adları** doğrulanmalı.
- [ ] Supabase'de migration 006 RPC'leri, trigger'ları, tek aktif sahip ve idempotency indeksleri incelenmeli.
- [ ] Admin ve iki satış hesabıyla müşteri devri/erişim iptali senaryosu test ortamında doğrulanmalı.
- [ ] AI cache miss akışı test ortamında gerçek sağlayıcıyla; süre, kalıcılık ve maliyet açısından sınanmalı.
- [ ] Eski şemadan yükseltme ve temiz kurulum aynı davranışı vermeli.
- [ ] İşçi tetikleme aralıklarının neden yapılandırmadan farklı olduğu incelenmeli.
- [ ] Yedek geri yükleme ve secret rotasyonu durumu kanıtlanmalı.
- [ ] Giriş sonrası mobil/klavye kullanımı ve tam satış akışı uçtan uca test edilmeli.

Bu rapor kapsamında uygulama kodu, canlı veriler ve deployment değiştirilmedi. Yerel inceleme ortamı kuruldu ve bu Markdown raporu oluşturuldu.
