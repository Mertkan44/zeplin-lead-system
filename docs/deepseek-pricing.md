# DeepSeek maliyet hesabı — 13 Ekim 2026

[Resmî tarife](https://api-docs.deepseek.com/quick_start/pricing/) bu tarihte
doğrulandı. Aşağıdaki USD tutarları bir milyon token içindir:

| Model | Yoğun giriş | Yoğun cache hit | Yoğun çıktı | Yoğun olmayan katsayı |
|---|---:|---:|---:|---:|
| deepseek-flash | 0.30 | 0.006 | 1.20 | 0.5 |
| deepseek-v4-pro | 1.32 | 0.044 | 3.96 | 0.5 |

Legacy `deepseek-v4-flash` ve `deepseek-v4-flash-vision-exp`, sağlayıcı tarafından
V4.1 Flash'a yönlendirilir; migration 016 bu takma adları da aynı tarifeyle ekler.
Model adları ve generation cache anahtarları bu güncellemede değiştirilmez.

Yoğun saatler hafta içi 01:00–04:00 ve 06:00–10:00 UTC'dir; bitiş saati hariç.
Hafta sonu ve Çin resmî tatilleri yoğun olmayan tarifeyi kullanır. 2026 takvimi
[Çin Devlet Konseyi duyurusunun resmî belediye yayını](https://www.beijing.gov.cn/cs/gncs/zcwj/202603/t20260327_4568275.html)
ile doğrulandı. Tatil yılları billing_calendar.py içinde sürümlenir.

Kuyruğun hangi saatte başlayacağı belli olmadığı için tarama ön tahmini **yoğun
tarife üzerinden rezerv** ayırır. Gerçek çağrı hesabı istemcinin çağrıya başladığı
UTC zamanı ve sağlayıcının döndürdüğü cache hit/miss/çıktı tokenlarıyla yapılır;
aynı tarihte İstanbul saati iş bütçesi için kullanılmaya devam eder. Rate snapshotı
dönemi ve çağrı zamanını ledger'da taşır. Sağlayıcının faturasıyla mutabakat ayrıca
gerekir; istemci zamanı sağlayıcı billing timestamp'inin garantisi değildir.

2027 ve sonrası için takvim doğrulanmadan yoğun pencereye denk gelen çağrının
gerçek maliyeti `unpriced` kalır. Hafta sonu/pencere dışı fiyatı ve üst sınır
rezervi hesaplanabilir. Sonraki yıl takvimi ve tarife değişiklikleri ayrıca
güncellenmelidir. Bilinmeyen modele genel `.env` fiyatı uygulanmaz.

Yeni tarife 2026-10-13'ten başlar. Eski usage kayıtları ve uygulanan rate
snapshotları değiştirilmez; geçmişteki hatalı genel fiyatlar bugünkü tarife
ile sessizce yeniden hesaplanmaz. Migration tekrarında mevcut fiyat satırı
üzerine yazılmaz. Panel/API/worker bu kod için migration 016 readiness ister.
