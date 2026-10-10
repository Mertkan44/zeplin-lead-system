# Ekip, hizmetler ve kişisel ayarlar (WP14)

`/team` yalnız yöneticilere açıktır. Kişi ekleme ve düzenleme; ad, e-posta,
rol, aktif durum, unvan, isteğe bağlı HTTPS fotoğrafı ve şifreyi kapsar.
Rol ve aktif durum tek veritabanı komutunda kaydedilir. E-posta düzenlemede
sabit kalır; hesap kapatma, görevleri otomatik devretmez. “Atamaları gör”
kişinin lead listesini açar; mevcut atama akışıyla sorumluyu değiştir.

Görev yükü aktif atamaların sayısıdır; geciken sayı takip tarihi gelmiş aktif
atamaları gösterir. Bu değerler performans veya kazanılmış fırsat sayısı değildir.
Pasif hesaplar ekip listesinde kalır, giriş yapamaz ve yeni atama seçiminde görünmez.

## Güvenlik ve eşzamanlı düzenleme

- Son aktif yönetici pasifleştirilemez, satış rolüne indirilemez veya silinemez.
  RPC, kullanıcı satırından önce ortak transaction kilidini alır ve yöneticinin
  güncel yetkisini veritabanında yeniden kontrol eder. Eski doğrudan yazmaları
  da trigger korur; eşzamanlı legacy işlemlerden biri transaction hatası alabilir.
- Düzenleme `expected_updated_at` ile eski formu reddeder. Çakışmada formdaki
  seçimler korunur; “Güncel bilgileri al” yalnız sürümü yeniler. Kullanıcı
  seçimlerini kontrol ederek yeniden kaydeder.
- `idempotency_key` UUID olmalıdır. Aynı içerikli başarısız ağ isteğinin yeniden
  gönderimi aynı anahtarı kullanır; başarılı komut, audit ve replay kaydı tek
  transaction içindedir. İçerik değişince yeni anahtar kullanılır. Şifre özeti
  rastgele salt kullansa da request digest sabittir; digest `SESSION_SECRET`
  ile HMAC'tir. Düz şifre ve password hash cevaplara/audit'e girmez.
- RPC'ler `service_role` içindir; `anon` ve `authenticated` çalıştıramaz.
  Uygulama mevcut HttpOnly cookie kimlik doğrulamasını kullanır. DB işlemi
  istemcinin gönderdiği actor'a güvenmez; sunucu doğrulanmış oturumdan alır.
- Hesap güncellemesi `updated_at` sürümünü değiştirir ve o hesabın eski
  oturumlarını geçersiz kılar. Kendi hesabını değiştiren yönetici yeniden girer.
  Sürüm taşımayan eski kullanıcı cookie'leri de yeniden giriş gerektirir.

## Hesabım ve hizmet kataloğu

`/profile` hesap bilgilerini, gerçek tema/satır aralığı tercihlerini ve kendi
şifresini değiştirme formunu içerir. Tema ve yoğunluk yalnız bu tarayıcıda
saklanır; CRM veya şifre tarayıcı depolarına yazılmaz. Şifre 12–128 karakter
olmalıdır. Mevcut şifre doğrulanır, denemeler rate limit'e tabidir; eski hash ve
hesap sürümü transaction içinde yeniden kontrol edilir. Başarılı değişim tüm
eski oturumları sonlandırır ve istemci sorgu önbelleğini temizler.

Hatırlatmalar mevcut Bugün/Takip ekranlarındadır; e-posta veya push bildirimi
uygulanmış gibi gösterilmez. Ekip düzenlemesi hesap ekranından ayrıdır.

`/hizmetler` genel kataloğu CRM verisi yokken de gösterir. Her kartta sahibi,
kategori, teslimat, kapsam dışı işler, önerinin bulguları, keşif soruları ve fiyat
onayı yer alır. Açılır kapsam bölümü kataloğun mevcut kapsamını gösterir; mevcut
katalogda ayrı bir kapsam URL'si yoktur. Lead'e özel kanıtlar lead detayında kalır.
Discovery-only hizmetler görüşmede doğrulanır; kötü website skoru tek başına özel
yazılım ihtiyacı sayılmaz. Fiyat uydurulmaz, onaysız tutar sıfır gelir gösterilmez.
Eşleşme sayıları yalnız erişilebilen leadler içindir; veri alınamamışsa `—` görünür.
Hizmet kuralları ve katalog sürümü bu paketle değiştirilmez.

## Mevcut API üzerindeki sözleşme

Yeni serverless dosyası yoktur; toplam fonksiyon sayısı 11 kalır.

- `GET /api/users?view=team`: yönetici, aktif/pasif üyeler ve görev yükleri.
- `POST /api/users?view=team`: yeni kişi; `idempotency_key`, `email`, `name`,
  `role`, boolean `active`, `password`; isteğe bağlı `title`, `avatar_url`.
- `PATCH /api/users?view=team`: aynı alanlar, zorunlu `expected_updated_at`;
  şifre boş/belirtilmemişse korunur. Plain POST/PATCH de bu güvenli komutu kullanır.
- `PATCH /api/users?view=account`: yalnız `current_password`, `new_password`,
  `expected_updated_at`. Başkasının e-postası veya rol alanı kabul edilmez.
- Plain `GET /api/users` mevcut atama seçimiyle uyumludur; satış kullanıcılarına
  diğer kişilerin e-postalarını ve pasif hesapları döndürmez.

400 doğrulama hatası, 403 yetki hatası, 409 eski sürüm/son yönetici/tekrarlanan
e-posta çatışmasıdır. Yönetim ekranı tekrar denemede formu korur.

## Yayın ve doğrulama

Bu paket main'den bağımsız hazırlanmıştır. Canlıda halen 011 varsa WP12'nin
worker durdurma/drain ve yedek prosedürünü uygulayıp **012 → 013 → 014** sırasını
izle. Her paketin branch'i main'e alınırken önceki paketleri içerecek şekilde
güncellenmeli; `schema.sql` yeniden üretilmeli, tüm testler ve CI yeniden geçmelidir.
014'ün readiness RPC'si 012/013 kontrollerine eklenir; onların yerini almaz.
Sağlık kontrolü en az 014 ve çalışan ekip korumalarını ister. SQL erişimi olmadan
PR'ın yeşil olması canlı migration'ın uygulanmış olduğunu kanıtlamaz.

```bash
venv/bin/python -m unittest discover -s tests
npm --prefix web run build
RUN_E2E=1 venv/bin/python -m unittest discover -s tests/e2e
python scripts/build_schema.py --check
python scripts/schema_parity.py --dsn <throwaway-postgres-dsn>
python scripts/backup_rehearsal.py --dsn <throwaway-postgres-dsn>
python scripts/team_concurrency.py --dsn <throwaway-postgres-dsn>
```

SQL davranış testleri atomic kayıt/audit rollback, create replay, eski form,
DB yetki kontrolü, son yönetici, şifre/oturum sürümü ve private ACL'leri sınar.
Concurrency testi RPC, legacy ve repeatable-read yarışlarını ayrı sınar.
Tarayıcı testleri kayıtta hata/tekrar/409, formun korunması, yoğunluk tercihi,
şifre sonrası giriş ve satış yetki sınırını sınar. Görsel kontrol beş genişlikte
(1440/1280/768/390/320), iki temada sentetik verilerle yapılır.
