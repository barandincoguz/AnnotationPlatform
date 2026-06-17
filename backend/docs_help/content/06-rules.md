# Önemli Kurallar

## 1. Kalite > Hız

Sistem **çok hızlı annotate ettiğini fark ederse** seni uyarır:

> "Yavaşla — son 5 dakikada 5 özelge tamamladın. Yaptığından emin misin?"

Bu uyarı bir ceza değil — kendine bir saniye dur, son birkaç özelgeyi gerçekten okudun mu, kanun atıflarını **atlamadan** çıkardın mı emin ol. Bu mesaj geldikten sonra hâlâ devam edebilirsin.

## 2. Eksik referans, yanlış referanstan iyidir

Bir kanun atfı görüyorsun ama **bent** belirsiz ya da "burada belki Geçici 67 maddesi kastediliyor olabilir" diye tahmin ediyorsan: **boş bırak**.

- ✅ Madde `5`, Fıkra `1`, Bent boş — tam doğru (özelge bent belirtmemişse)
- ❌ Madde `5`, Fıkra `1`, Bent `a` (tahmin) — yanlış kayıt, ileride arama sonucunu bozar

## 3. Etik

- **Yapay zekaya özelgeyi yazdırıp kopyala-yapıştır yapmak** teknik olarak engellenmiyor ama sistem kalıp tekrarını fark eder ve admin görür. Yapma. Senin kafanı geliştirmek için bu işi yapıyoruz; AI yardım alıyorsan referansı kendi gözünle doğrula.
- "Bu özelge çok zor" → **Atla** her zaman geçerli, ceza yok.
- **Hiçbir alanı zorla doldurma**: Madde belirsizse boş, Bent belirsizse boş. Kanun No veya Kanun Adı'ndan en az biri zorunlu — her referans en az bir kanunu işaret etmeli.

## 4. Şüpheli durumda

- Özelge metni bozuk gözüküyorsa (parse hatası, eksik sayfa) → **Atla**
- Özelge 2 sayfa ama PDF parse edilirken kayıp olmuş → **Atla**
- Konu ağır vergisel olduğu için tam emin değilsen → yine de oku, gözüne çarpan **somut atıfları** çıkar; emin olamadıklarını **yazma**.
- Atıf "Kanun" diyor ama hangi kanun olduğunu metinden çıkaramıyorsan → o referansı yazma; bağlamından emin olduklarını yaz.

## 5. Karakter limiti (Metinden alıntı için)

"Metinden alıntı" alanı zorunludur. Alıntı uzunluğu için:
- **300 karakter üzerinde** turuncu uyarı
- **600 üzerinde** kırmızı uyarı

Uzunluk uyarıları Kaydet işlemini tek başına engellemez. Atıfın geçtiği **tek
cümleyi** alıntılaman yeterli; tüm paragrafı kopyalama.

## 6. Mola ver

20 özelgeden sonra 5 dakika gözünü ekrandan ayır. Streak'in kırılmaz, gün sayılmaya devam eder. Vergi metni yoğun bir dildir; uzun süreli okuma hata oranını ciddi şekilde artırır.
