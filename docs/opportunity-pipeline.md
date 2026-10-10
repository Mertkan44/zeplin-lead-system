# WP13 — Satış fırsatları ve aşama geçmişi

## Paneldeki davranış

Pipeline yalnız oluşturulmuş satış fırsatlarını gösterir. Bu sürümde bir işletmenin
bir fırsatı vardır. Araştırma hazırlığı ayrı rozet olarak görünür; araştırma durumu
satış aşamasını belirlemez. Eski işletmelere veya eski görüşmelere otomatik fırsat,
tutar veya aşama geçmişi üretilmez.

Aşamalar: Yeni fırsat → Temas → Keşif → Teklif → Karar → Kazanıldı / Kaybedildi.
Atanmış satış kullanıcısı kendi aktif atamasında, yönetici tüm işletmelerde işlem
yapabilir. Tamamlanan atamanın eski sahibi fırsatı ve geçmişini okuyabilir; başka
bir kişiye devredilirse okuma ve önceki işlemi tekrar alma erişimi de kapanır.

Kartlar işletme, ana hizmet, sorumlu, son temas, takip, aşamada geçen süre ve gerçek
fırsat tutarını gösterir. Özet yalnız bilinen açık fırsat tutarlarını toplar; eksik
tutar sayısını ayrıca gösterir. AI tahmini tutar olarak kullanılmaz. “Düzenle”
aynı aşamada hizmeti/tutarı değiştirebilir; kazanım tutarını sonradan tamamlamak
ikinci bir kazanım veya yeni görüşme oluşturmaz.

Sürükleme ve aşama menüsü aynı formu açar. Sunucu onaylamadan kart taşınmaz.
Kaybedildi ve geriye dönüş için neden gerekir. Kazanıldı için tutar veya açıkça
“Tutar henüz bilinmiyor” seçilir. Kapanış aktif atamayı tamamlar ve eski takibi
kaldırır. Yeniden açma yalnız yönetici, neden ve Yeni fırsat aşamasıyla yapılır;
bu işlem atama veya takip tarihi oluşturmaz. Bunlar ayrıca planlanır. Sonraki
not/araştırma işlemi iptal edilen eski takip tarihini geri getirmez.

Yeni görüşme sonuçları mevcut atomik işlem içinden ortak aşama geçişini kullanır:

| Görüşme sonucu | Fırsat aşaması |
| --- | --- |
| Cevap yok / Daha sonra | Temas |
| İlgileniyor | Keşif |
| Teklif istiyor | Teklif |
| Kazanıldı | Kazanıldı |
| Kaybedildi / İlgilenmedi | Kaybedildi |
| Yanlış numara | Ticari aşama değiştirilmez; mevcut doğrulama akışı sürer |

Yeni bir cevapsız arama açık fırsatın Keşif/Teklif/Karar aşamasını geriye götürmez.
Kapanmış fırsatı görüşme sonucu sessizce açamaz. Önce yönetici yeniden açar.
Eski istemcilerin görüşme istekleri aynı API biçimiyle çalışır; onların eksik
kayıp nedeni veya bilinmeyen kazanım tutarı boş/bilinmiyor gösterilir. Güncel panel
kayıp nedeni ister ve görüşmeyle kazanımda tutarın eksik olduğunu açıklar.

Aşama, tutar ve hizmet değişiklikleri revizyon, önceki/yeni aşama, aktör, kaynak,
not ve İstanbul saatine göre zamanla geçmişte görünür. Ticari geçiş ayrı olaydır;
telefon/mesaj/görüşme yapılmış gibi sayılmaz. Satış metriklerinde manuel kapanış
ve görüşme kazanımı aynı işletme için tekil sayılır.

## Yayın sırası

1. WP12'nin `012_worker_lifecycle.sql` geçişini ve [işçi yayın adımlarını](worker-rollout.md)
   tamamla. Bu paketin 013 migration'ı WP12'nin hazırlık kontrollerini değiştirmez.
2. [Operasyon rehberindeki](operations.md) yedek ve yayın öncesi kontrolleri yap.
3. `supabase/migrations/013_opportunity_pipeline.sql` dosyasını uygula. Tekrar
   uygulanabilir. Şema paketi yalnız `scripts/build_schema.py` ile üretilir.
4. `opportunity_schema_readiness()` kontrolleri true olmalı. Uygulama bu sonucu
   mevcut `schema_readiness()` sonucu ile birleştirir; işçi kontrolü başarısızsa
   fırsat kontrolü onu gizleyemez.
5. Bu paket PR'ının CI kontrolleri yeşilken main'e birleştir; Vercel'in main commit'ini
   yayınlamasını bekle. `scripts/smoke_release.py --help` ile yayın kontrolünü çalıştır.
6. Ayrı test işletmesiyle oluşturma, aşama değişikliği, tekrar gönderim, eski form
   409, yetkisiz kullanıcı, kayıp nedeni, kazanım/takip kapanışı ve yönetici yeniden
   açmasını kontrol et. Gerçek müşteriler üzerinde deneme geçmişi üretme.

013 eklemelidir; önceki panel temel CRM işlemlerini sürdürebilir ancak kapanmış
fırsatı eski durum menüsüyle açmaya çalışırsa sunucu kontrollü 409 döndürür.
WP12'nin eski işçisi migration 012 sonrasında geri yayınlanamaz. Veritabanı geri
alma ile kod geri alma ayrı işlemlerdir; tablo/geçmiş silerek geri alma yapma.

## Doğrulama

Birim testleri API'nin aktörü/rolü sunucudan almasını, alan doğrulamasını,
hata kodlarını ve metrikleri kontrol eder. SQL davranış testleri atomik kapanışı,
kilitlenen sürümleri, erişim devrini, tekrar gönderimi, geçmiş hatasında rollback'i
ve iptal edilmiş takiplerin geri gelmemesini kontrol eder. Şema testi taze kurulum
ve dört tarihsel yükseltmeyi iki kez uygular. 012+013 birlikte de aynı testlerden
geçirilir. Playwright testleri oluşturma, mobil menü/geçmiş, kapanış formu,
kaydetme hatası ve 409 sonrası alanların korunmasını kontrol eder.
