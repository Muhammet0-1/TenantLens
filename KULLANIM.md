# TenantLens · Türkçe kullanım

TenantLens, farklı kullanıcı ve şirket hesaplarının API kaynaklarına erişimini
tanımladığın izin matrisiyle karşılaştırır. Kimlik ön kontrolü ve izinli baseline
doğrulanmadan kaynak hakkında kesin bir izin sonucu üretmez.

## İlk çalıştırma

Python 3.11 veya üzeri gerekiyor. Hazır ZIP'te panel derlenmiş olarak bulunur;
ilk çalıştırma için pip, npm veya paket kayıtlarına ağ erişimi gerekmez.

ZIP'i aç, terminalde `TenantLens` klasörüne gir ve çalıştır:

```fish
cd TenantLens
python3 -m tenantlens serve --demo
```

Tarayıcıda **http://127.0.0.1:8765** adresini aç. Durdurmak için terminalde
`Ctrl+C` kullan. Windows'ta Python Launcher varsa `python3` yerine `py -3` yaz.

Port doluysa:

```fish
python3 -m tenantlens serve --demo --port 9000
```

Bu durumda panel 9000, demolar 9001–9003 portlarını kullanır. Farklı bir demo
portuyla başlarken eski proje hedeflerini korumak yerine yeni bir çalışma alanı
istersen `--state-dir .tenantlens-9000` ekle.

## Demoları sırayla dene

| Proje | Beklenen sonuç | Açıklama |
| --- | --- | --- |
| Demo · Veri sızıntısı | 6 karşılandı, 3 ihlal | Fatura uç noktalarında şirket sınırı uygulanmıyor. |
| Demo · Düzeltilmiş | 9 karşılandı | Şirket sınırı ve yönetici kuralı uygulanıyor. |
| Demo · Geçersiz oturum | 4 karşılandı, 5 belirsiz | Bora'nın kimliği doğrulanamıyor; onun baseline olduğu kaynak da belirsiz. |

**Testi çalıştır** düğmesine bas. Sonuç geldikten sonra herhangi bir hücrenin
sonuç etiketine tıkla. Örneğin hatalı demoda **Bora'nın faturası / Ayşe** hücresi,
yabancı şirkete ait faturanın `id` ve `organization_id` alanlarıyla erişim
ihlali kanıtını gösterir.

**Bulgular** ekranından HTML veya JSON raporu indir. **Çalışma geçmişi**, her
testin o anki yapılandırmasını ayrı bir kopyayla saklar. Eski bir çalışmayı
açtığında matris salt okunur; **Güncel tanımı aç** ile düzenlemeye dönersin.

## Proje oluşturma ve düzenleme

- **Yeni proje** mevcut tanımın kopyasından bir taslak oluşturur. Proje yoksa bir
  hesap ve örnek kaynakla başlar. Kaydetmeden önce adı, hedefi ve hesapları düzenle.
- **Hesaplar** ekranında kullanıcı adı, şirket ID, rol etiketi ve `auth_env`
  referansını düzenle. **Kimlik ön kontrolü** hesabın JSON kimlik koşullarını açar.
- Matrisin hücrelerindeki **İzinli / Yasak** seçimi, beklenen politika kuralıdır.
- **Kaynak ekle** veya kaynak satırındaki kalem, GET yolu, baseline ve başarı
  kanıtı koşullarını düzenler. Tanım uygulanırken sunucuda doğrulanır.
- **Proje tanımı** ekranı hedefi, limitleri ve tüm JSON'u düzenlemeye izin verir.
  JSON değişikliğinden sonra **JSON doğrula ve uygula**, ardından **Kaydet** kullan.
- JSON içe aktarmak önce doğrulanmış bir taslak açar. Kaydetmeden mevcut tanımı
  değiştirmez. Aynı ID ile kaydetmek ilgili tanımı günceller.

Her kaynakta en az bir **İzinli** hesabı baseline seçmelisin. Kaynak başarı
kanıtı, beklenen kaynağı ayırt eden alanları içermeli: örneğin `/id` ve
`/organization_id`. Sadece `/success: true` gibi genel bir koşul yanlış kaynağı
ayırt edemeyebilir.

## Kendi API'ni bağlama

`examples/custom-project.json` iki ayrı şirketteki hesaplar için başlangıç
örneğidir. Yer tutucu hedefi, `/api/whoami` yolunu ve yanıt alanlarını kendi
API'nin gerçek sözleşmesine göre değiştir.

Token değerleri proje dosyasında bulunmaz. Sunucuya ortam değişkeni olarak
verilir. Fish terminalinde, tokenı komut satırı geçmişine yazmadan:

```fish
read --silent --prompt-str 'User A token: ' token_a
set -gx TENANTLENS_USER_A_TOKEN $token_a
set -e token_a
read --silent --prompt-str 'User B token: ' token_b
set -gx TENANTLENS_USER_B_TOKEN $token_b
set -e token_b
python3 -m tenantlens serve
```

Panelde JSON'u içe aktar ve kaydet. **Token hazır**, yalnızca değişkenin mevcut
olduğunu gösterir; tokenın geçerli olduğunu testteki kimlik ön kontrolü belirler.
Başka terminalde değiştirilen ortam değişkenleri çalışan sunucuya geçmez;
sunucuyu yeni değişkenlerle tekrar başlat.

Gerçek API kullanırken `--demo` ekleme. Hedefe gönderilen kimlik bilgisi
`Authorization: Bearer …` başlığıdır. v0.1, GET ve Bearer kullanımını destekler.

## Sonuçları doğru yorumlama

| Sonuç | Anlamı |
| --- | --- |
| Beklenti karşılandı / PASS | Tanımladığın kontrol gerekli ön doğrulamalarla beklentiyi karşıladı. |
| İzin ihlali / VIOLATION | Yasak erişim başarı kanıtını sağladı veya beklenen izinli erişim açıkça reddedildi. |
| Belirsiz / INCONCLUSIVE | Kimlik, baseline, oturum veya kanıt yeterli değildi. |
| Çalıştırma hatası / ERROR | Bağlantı, zaman, yanıt boyutu veya hedef sunucu hatası oluştu. |

`expected_allow_denied` bir politika uyuşmazlığıdır; tek başına sömürülebilir
güvenlik açığı demek değildir. `401`, giriş sayfası ve doğrulanmamış `404`,
otomatik olarak başarılı bir erişim engeli sayılmaz. `403/404` ret kontrolü
geçerli kimlik ve başarılı kaynak baseline'ı gerektirir.

## Terminal kullanımı ve testler

```fish
python3 -m tenantlens check --demo fixed --output reports
python3 -S -m unittest discover -s tests -v
```

CLI çıkış kodları: `0` beklentiler karşılandı, `1` ihlal var, `2` belirsiz/hata
var veya yapılandırma başlatılamadı. Hatalı demoda `1` almak beklenen davranıştır.

Panelin kaynak kodunu değiştirmek istersen Node 22.12+ veya 24 ile:

```fish
cd web
npm ci
npm run build
npx playwright install chromium
npm run test:browser
```

Bu geliştirme adımları paket indirmeyi gerektirir. Hazır paneli kullanmak için
bu adımları çalıştırman gerekmez.

## GitHub'a eklemeden önce

Kaynak kod, testler, hazır panel, örnekler, belgeler, MIT lisansı ve CI dosyası
pakette bulunur. `.gitignore` gerçek token ortam dosyalarını, SQLite verisini,
rapor klasörünü ve `node_modules` klasörünü dışarıda bırakır. GitHub'a gönderirken
gerçek hedef/hesap bilgilerini veya özel test raporlarını ayrıca ekleme.

Kalıcı çalışma verisi varsayılan olarak `.tenantlens/tenantlens.sqlite3`
dosyasındadır. Proje silmek geçmiş çalışmalarını silmez. Panelden indirilen
raporlar, seçtiğin hedef/kaynak ve kanıt değerlerini içerebilir; paylaşmadan önce
bu içeriği incele.
