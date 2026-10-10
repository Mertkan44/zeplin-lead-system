# İşletim ve yayın (WP15)

## Günlük kontrol

`Operations checks` GitHub Actions işi her saat ve main CI başarılı olduğunda çalışır.
Üretim adresi `PRODUCTION_URL` repository variable'ında tutulur. Servis anahtarı
mevcut Actions secrets'ından gelir; PR koduna bu anahtar verilmez.

Kontrol yalnızca okur: `/api/health` veritabanının beklenen şemaya hazır olduğunu
ve `VERCEL_GIT_COMMIT_SHA` ile doğru sürümün çalıştığını doğrular. Panel, JS/CSS,
CSP, anonim oturum ve müşteri verisi veren uç noktaların 401 yanıtı kontrol edilir.
AI üretmez, tarama başlatmaz, satış kaydı değiştirmez.

Saatlik kontroller: kuyruktaki en eski iş 60 dakikayı aşarsa, işin lease'i/kalp
atışı durursa, son saatte başarısız/kısmen tamamlanan iş veya başarısız generation
varsa, ya da sağlayıcıdan en az 5 hata gelirse iş kırmızı olur. Eşikler CLI
parametreleriyle değiştirilebilir. 011 şeması için eski worker'a uygun kontrol,
012 sonrası için gerçek lease özeti kullanılır. Actions hata bildirimleri hesabın
GitHub notification ayarlarına bağlıdır; ayrı e-posta/Slack entegrasyonu kurulmadı.

Audit yazma hatası satış işleminin başarılı yanıtını değiştirmez. Vercel loglarında
`zeplin.operations` / `audit_persistence_failed` aranır. Yalnızca işlem kategorisi
ve hata sınıfı yazılır; müşteri adı, e-posta, prompt ve bağlantı bilgisi yazılmaz.
Eksik audit otomatik olarak tekrar CRM işlemi uygulayarak düzeltilmez. Transaction
içindeki audit hatası ise transaction'ı geri alır; bu ayrı davranıştır.

## Yayın sırası

1. Paket branch'i main'den açılır; unit, schema parity/SQL davranışı, frontend build
   ve E2E kontrolleri PR'da yeşil olmalıdır. UI değişince public/ aynı PR'a girer.
2. Preview/staging gerçek üretim DB'sine bağlanıyorsa orada yazmalı test çalıştırma.
   Ayrı staging projesinde sentetik fixture ile login → liste → temas sonucu →
   takip → logout akışını dene. Yerel Playwright sentetik fixture testleri CI'da
   çalışır; bunlar canlı staging kanıtı yerine geçmez.
3. Şema değişiyorsa aşağıdaki yedeği al, geri yükleme provasını doğrula, migration'ı
   aynı PostgreSQL ana sürümünde dry-run et. `schema.sql` yalnız build_schema.py
   ile üretilir. Migration versiyonu/readiness canlıda ayrı kontrol edilir.
4. Worker'ın claim davranışı değişiyorsa scheduled workflow'u durdur, çalışan
   işleri bitir/drain et. Yeni SQL ve yeni worker uyumluluğunu paketin rollout
   belgesinden kontrol et. Özellikle 012 eski worker'ı emekliye ayırır.
5. PR'ı birleştir; Vercel Git entegrasyonunun main commit'ini yayınlamasını bekle.
   Actions release smoke beklenen commit'i en fazla 10 dakika bekleyerek doğrular. Smoke kırmızıysa yeni tarama
   başlatma; önce şema ve yayın commit'ini kontrol et.
6. Yeni worker sürümünün schema preflight'ı geçtikten sonra schedule'u aç.
   İlk gerçek kullanıcı işinin kalp atışı, ilerleme ve maliyet kayıtlarını izle.

Manuel yalnız okuma smoke:

```sh
python scripts/smoke_release.py --url https://zeplin-lead-system.vercel.app --expected-commit COMMIT_SHA
python scripts/check_operations.py
```

Korunan preview için mevcut automation bypass secret sadece ortam değişkeni
`VERCEL_AUTOMATION_BYPASS_SECRET` üzerinden kullanılabilir; URL'ye eklenmez ve
loglanmaz. Login sayfası veya 403 başarılı smoke sayılmaz. Üretim smoke'u cookie
kullanmaz; kullanıcı rolünün uçtan uca kontrolü staging'de yapılır.

## Yedek alma ve geri yükleme provası

Yedekler müşteri iletişim bilgilerini ve uygulama kullanıcılarının parola hash'lerini
barındırır. Git'e, CI artifact'ına veya sohbete konulmaz. İzinler 0600; yeni dizin
0700. Bu dosya şifrelenmiş bir diskte veya kurumun şifreli yedek deposunda tutulmalı;
araç kendi başına şifreleme ya da dış depoya yükleme yapmaz.

`pg_dump`, `pg_restore`, `psql` sunucunun PostgreSQL ana sürümüyle eşleşmeli.
[PostgreSQL pg_dump belgesi](https://www.postgresql.org/docs/17/app-pgdump.html)
custom archive ve tutarlı snapshot davranışını açıklar.

Yetkili operatör bağlantıyı güvenli ortam değişkeninden yükler; bağlantı dizesi
komut argümanına veya belgeye yazılmaz. Supabase service role HTTP anahtarı bir
DB bağlantı parolası değildir. Direct/session pooler DB bağlantısı gerekir;
transaction pooler bu araçlar için kullanılmaz.

```sh
# BACKUP_DATABASE_URL güvenli yerel ortamda zaten tanımlı olmalı.
python scripts/database_backup.py backup --file backups/pre-release.dump
# RESTORE_DATABASE_URL ayrı, boş Supabase/deneme DB'sini göstermeli.
python scripts/database_backup.py restore --file backups/pre-release.dump
```

Yedek `public` şemasındaki tablolar/veri, sequence, fonksiyon, RLS ve grant'leri
birlikte alır. SHA-256 ve kaynak fingerprint içeren özel manifest oluşturur;
mevcut dosyayı ezmez. Restore checksum'u kontrol eder, aynı kaynak fingerprint'ini
ve dolu public hedefini reddeder. `--clean`/DROP kullanmaz; tek transaction'da ve
ilk SQL hatasında geri alarak restore eder. Sonra `schema_readiness()` doğrulanır.
Hedefte Supabase'in anon/authenticated/service_role rolleri önceden bulunmalı.

Kapsam dışı: Supabase Auth/Storage şemaları, bucket dosyaları, platform ayarları,
Vercel/GitHub secret'ları ve platform kullanıcı rolleri. Bunlar için sağlayıcının
proje yedeği/geri yükleme yöntemi ayrıca planlanır; bu uygulama dump'ı tam proje
felaket kurtarma yedeği olarak sunulmaz. Uygulama app_users tablosu kapsamdadır.

Prova sırasında sentetik kaynak ve ayrı boş hedef kullan. Restore edilen lead,
atanan kişi, temas geçmişi, task state, ledger ve schema versiyonunu karşılaştır;
RLS/grant'leri schema parity ile karşılaştır. Bozuk checksum ve dolu hedefin
reddedildiğini dene. Canlı veriyle provada hedef uygulamasını dış erişime açma,
worker ve Places cron'u çalıştırma. Kurtarma gerektiğinde önce ayrı hedefe
restore/prova, ardından açık bakım planıyla trafik yönlendirmesi yapılır.

Başlangıç operasyon hedefi: günlük yedek, son 7 günlük ve son 4 haftalık kopya;
RPO 24 saat, RTO 4 saat. Bunlar henüz ölçülmüş sağlayıcı garantileri değildir.
Yedekleme takvimi ve saklama dış depoda yapılandırılmadıkça otomatik yedekleme
aktif sayılmaz. Aylık restore provası ve her migration öncesi yedek gerekir.

## Hata ve geri dönüş

- Sağlık kontrolü 503: schema readiness ve migration sürümünü kontrol et.
- Smoke commit uyuşmuyor: doğru main deploy'u hazır mı, domain ona bağlı mı bak.
- Audit persistence hatası: başarılı satışı tekrar gönderme; servis/DB erişimini
  düzelt, eksik denetim kaydını ayrı incele.
- Queue/heartbeat alarmı: Actions worker run, lease, deneme sınırı ve panel hata
  mesajını kontrol et. Ücretli AI'yı teşhis için kör tekrar çalıştırma.
- Schema geri alınmaz. Önce uyumluluk değerlendirilir; forward fix tercih edilir.
  012 sonrası eski worker'a dönmek güvenli değildir. Vercel code rollback DB'yi
  veya GitHub worker kodunu geri almaz. Worker kapalı tutulur ve yeni uyumlu düzeltme
  yayınlanır. Veri restore üretim deploy'undan ayrı bir bakım işlemidir.

WP15 araçları yerelde sentetik DB ile prova edilebilir. Canlı yedek ve staging
kanıtı yalnız gerçek erişimle yapılmışsa yayın kaydına yazılır.

10 Ekim 2026 SQL snapshotı, yerel PostgreSQL 17 ve native archive geri yükleme
kanıtları için [yayın kaydı](releases/2026-10-10.md).
