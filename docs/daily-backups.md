# Günlük şifreli yedekleme

Akış hazırdır; `BACKUP_ENABLED=false` iken yedek işi atlanır. Günlük yedek
aldığı ancak ilk gerçek başarılı run ve restore provası tamamlanınca söylenir.
Manuel workflow varsayılanı `rehearsal`: yalnız sentetik DB ve geçici anahtar
kullanır, production secrets almaz. `production` seçimi ayrıca etkinlik koşulunu
ister. Böylece şifreleme/açma/restore ve artifact yükleme yolu güvenle prova edilir.
Supabase hesabı 13 Ekim 2026 kontrolünde Free plandır; Pro'nun otomatik
[sağlayıcı yedeği](https://supabase.com/docs/guides/platform/backups) etkin değildir.

`Encrypted database backup` her gün İstanbul 02:30'da çalışacak şekilde
tanımlıdır. PostgreSQL 17 native archive ve manifest önce doğrulanır; ikisi
bir tar içine alınarak [age](https://github.com/FiloSottile/age) ile şifrelenir.
GitHub artifact'ına yalnız `.tar.age` ve ciphertext SHA-256 metadata yüklenir.
Günlük kopya 7, İstanbul takviminde pazar kopyası 28 gün tutulur. PR kodu
secret almaz; yalnız main çalışır. Özel anahtar CI'ya veya Git'e verilmez.

Hazırlanan public recipient `BACKUP_AGE_RECIPIENT` repository variable'ındadır.
Özel açma anahtarı yerelde `backups/keys/zeplin.agekey` dosyasındadır (0600,
dizin 0700, Git dışında). Kaybolursa şifreli yedek açılamaz; parola yöneticinde
veya güvenli ayrı bir ortamda kopyası saklanmalıdır. Sohbete yapıştırılmaz.

## Kullanıcının bir kez yapacağı kurulum

1. Supabase projesinde **Connect** → **Session pooler** bağlantı dizesini al.
   Port 5432 olmalı; transaction pooler 6543 kullanılmaz. `[YOUR-PASSWORD]`
   alanına kendi DB parolan girilir; özel URI karakterleri encode edilir.
   Bu bilgi Supabase service-role HTTP anahtarı değildir.
2. [GitHub Actions secrets](https://github.com/Mertkan44/zeplin-lead-system/settings/secrets/actions)
   sayfasında `BACKUP_DATABASE_URL` adlı repository secret'a bağlantıyı ekle.
   Bağlantıyı sohbete, .md dosyasına veya kaynak koda koyma.
3. Özel yedek açma anahtarını güvenli ayrı bir yere kopyala. Sonra kurulumun
   tamamlandığını belirt; ilk backup, açma ve boş yerel hedefte restore kontrolü
   yapılır, ardından `BACKUP_ENABLED=true` ile schedule etkinleştirilir.

GitHub'ın artifact saklama/Actions limitleri ayrıca geçerlidir; ayrı ücretli
depo veya plan satın alınmadı. Actions bildirimleri hesap ayarlarına bağlıdır.
Repo/artifact silinmesi ya da saklama süresi sonrası kopya kaybolabilir;
haftalık şifreli kopyaları ayrıca indirmek bağımsız kurtarma noktası sağlar.

## Geri yükleme

Ciphertext sidecar SHA-256 değeri önce kontrol edilir. Açma yerelde özel
anahtarla yapılır; geçici dizin 0700, dosyalar 0600 tutulur:

```sh
python scripts/decrypt_backup.py --file BACKUP.tar.age --identity backups/keys/zeplin.agekey --directory backups/restore
```

Araç yalnız iki normal dosyayı kabul eder; link/dizin/traversal üyelerini
reddeder, native archive checksum'unu doğrular ve mevcut dizine yazmaz. Restore hedefi ayrı
boş DB'dir ve üç Supabase rolü önceden hazırlanır:

```sh
# RESTORE_DATABASE_URL güvenli ortamda tanımlı; kaynak/üretim hedef gösterilmez.
python scripts/database_backup.py restore --file backups/restore/database.dump
```

Mevcut araç checksum'u kontrol eder; kaynak DB'ye ve dolu hedefe restore'u
reddeder. İşlem tek transaction'dadır. Scope yalnız public uygulama şemasıdır;
platform Auth/Storage dosyaları/ayarları ve secrets ayrıca korunmalıdır.
Canlı üretime restore otomatik yapılmaz.
