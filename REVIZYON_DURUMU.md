# Sistem incelemesi sonrası revizyon durumu

Tarih: 29 Eylül 2026. Dayanak: [SISTEM_INCELEME_RAPORU.md](SISTEM_INCELEME_RAPORU.md). Bu dosya, kodda yapılan değişiklikleri ve henüz karşılanmayan kabul ölçütlerini ayırır. **Bu dal canlı Vercel/Supabase ortamına uygulanmadı.**

| Bulgu | Durum | Yapılan iş / kalan kabul ölçütü |
| --- | --- | --- |
| F01 | Kod düzeltildi | Satış rolü yalnızca aktif atamaları, lead'leri ve olayları okuyabiliyor. Arşivlenmiş atama GET yanıtından da çıkarıldı. Canlı rol matrisi testi gerekli. |
| F02 | Kod düzeltildi | Satış rolü aktif olmayan atamayı yeniden açamıyor; admin yetkisi gerekiyor. |
| F03 | Kod düzeltildi | AI önbelleği önce Supabase'e yazıyor, yerel yazma salt okunur ortamda en iyi çaba olarak kalıyor. |
| F04 | Kısmi | Araştırma URL'leri ve her yönlendirme doğrulanıyor; istekler proxy ortam değişkenlerini kullanmıyor ve yanıt boyutu sınırlı. DNS kontrolü ile bağlantı arasındaki yeniden çözümleme yarışını ortadan kaldıran IP sabitlemesi hâlâ gerekli. |
| F05 | Açık, P1 | Yeni tarama aynı adlı farklı şehir/şube kaydını mevcut kaydın üzerine yazmak yerine hata veriyor. Ancak `leads.name` ve ilişkiler hâlâ ada bağlı; aynı adlı iki lead saklanamıyor ve ad değiştirme ilişkileri koparabilir. `lead_id` temelli kapsamlı şema/API/arayüz geçişi gerekli. |
| F06 | Kod düzeltildi, DB testi gerekli | `record_outreach_action` RPC olay, lead ve atamayı tek transaction içinde yazıyor; UUID anahtarı tekrarları yan etkisiz kılıyor. Eski tarihli ve kapalı lead'i geri açan olaylar engelleniyor. Gerçek PostgreSQL hata enjeksiyonu testi gerekli. |
| F07 | Migration hazır, DB testi gerekli | 008 koşulsuz unique idempotency indeksi kuruyor. Eski ve temiz şemada gerçek `ON CONFLICT` testi gerekli. |
| F08 | Kısmi | Farklı şehirdeki aynı adlı Places adayı reddediliyor. Yakın şubelerin Place ID/koordinat ayrımı ve belirsiz eşleşmeler için kullanıcı onayı gerekli. |
| F09 | Kısmi | README, temiz kurulumda şema + 006–012 geçiş sırasını açıklıyor. Migration sürüm tablosu ve temiz PostgreSQL CI kurulumu yok. |
| F10 | Doğruluk düzeltildi, performans açık | Tüm sayfalar çekilip rol filtresi uygulanıyor; API'lerde offset var ve tekil AI/Places ada göre okunuyor. Büyük veri kümesinde filtre/aggregate SQL'e taşınmalı. |
| F11 | Kısmi | AI ve Places alan bazlı optimistic update kullanıyor. Tarama upsert'i hâlâ geniş kayıt yazıyor; tarama ile eşzamanlı güncelleme kabul testi gerekli. |
| F12 | Kod düzeltildi | AI giriş parmak izi, prompt sürümü, üretim zamanı ve tamamlanma durumu saklanıyor; `last_analyzed` yenileniyor. |
| F13 | Kısmi | Gerçek sağlayıcı/model/token çağrı bazında kaydediliyor; fiyat adları uyumlandı; başka sağlayıcıya yanlış DeepSeek fiyatı uygulanmıyor. Başarısız/fallback çağrısı ledger uzlaşması ve atomik bütçe limiti açık. |
| F14 | Kod düzeltildi | Günlük ekip hesapları İstanbul gün sınırını kullanıyor. |
| F15 | Kısmi | Pipeline ve durum seçimi kazanım/kayıp için ortak outreach RPC'sini kullanıyor; sunucu satış rolünde hazır olma kontrolü yapıyor. Tüm ara geçişlerin tek iş akışı modeli ve E2E testi gerekli. |
| F16 | Kod düzeltildi | CRM localStorage yazıları kaldırıldı; çıkış, 401 ve yeni girişte bellek temizleniyor. Tarayıcı oturum geçişi E2E testi gerekli. |
| F17 | Kısmi | JSON boyut sınırı, önemli API alanlarında tip/enum kontrolleri ve istemci hataları eklendi. Tüm alanlar için tek şema katmanı henüz yok. |
| F18 | Kısmi | 12 karakter parola, son admin için veritabanı trigger'ı, hesap/IP/birleşik giriş limitleri ve kalıcı limiter arızasında kapalı davranış var. Eşzamanlı giriş denemesi atomik rezervasyon ve ek admin doğrulaması açık. |
| F19 | Kısmi | AI başarısızlıkları `partial_success` olarak yazılıyor. Heartbeat, deneme sınırı, kuyruk yaşı alarmı ve aşama ilerlemesi yok. |
| F20 | Büyük ölçüde düzeltildi | React/JSX esbuild ile derleniyor; React/Babel CDN kaldırıldı; script CSP yalnızca `self`. Bileşenlere ayırma ve satır içi stil CSP'sini kaldırma açık. |
| F21 | Kısmi | Regresyon testleri, frontend build ve CI çıktı kontrolü eklendi. Gerçek PostgreSQL migration/transaction ve kimlikli tarayıcı E2E testleri yok. |
| F22 | Kısmi | Yapılandırılmış outreach alanlarına yeni kayıt yazılıyor ve 011 eski kayıtları taşıyor; manuel doğrulama 30 gün sonra eskiyor. Alan bazlı kaynak/override, çelişki kuyruğu ve veri hacmine göre tazelik kapasitesi açık. |

## Yerel doğrulama

- 62 Python testi geçti; `compileall`, veri doğrulama, güvenlik taraması ve `git diff --check` geçti.
- Frontend üretim derlemesi üretildi; giriş ekranı yerel tarayıcıda yüklendi.
- 13 SQL dosyası `pglast` ile sözdizimi açısından ayrıştırıldı. Bu, PostgreSQL/Supabase üzerinde çalıştırma yerine geçmez.

## Yayına alma sırası

1. Veritabanı yedeği ve önizleme ortamı oluşturup 006–012 geçişlerini sırayla çalıştırın; özellikle 008 RPC imzası, 011 geçmiş kayıt taşıması ve 012 admin trigger'ını gerçek verilerle doğrulayın.
2. Önizleme ortamında admin atama → satış doğrulama → görüşme → takip → kazanım akışını ve eski isteğin tekrarını deneyin.
3. F05 için ayrı, kimlik temelli veri geçişini ve F04 DNS bağlantı sabitlemesini tamamlayın; sonrasında yayın öncesi kabul testlerini tekrarlayın.
