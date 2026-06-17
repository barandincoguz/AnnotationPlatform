# Referans Normalizasyonu ve Validasyon İyileştirmeleri Teknik Raporu

**Tarih:** 13 Haziran 2026  
**Hazırlayan:** Ahmet Baran Dinçoguz  
**Konu:** Geri Bildirimler Doğrultusunda Geliştirilen Referans Doğrulama, Normalizasyon ve Veri Kalitesi İyileştirme Yapısı  

---

## 1. Giriş ve Sorun Tanımı
Anotasyon platformunda kullanıcıların (etiketleyicilerin) serbest metin girişlerinden veya farklı klavye düzenlerinden kaynaklanan yazım farklılıkları, veri tabanında tutarsız atıflara ve arama/mükerrerlik kontrollerinin bozulmasına yol açmaktaydı. Ayrıca, veri giriş kalitesini ölçmek ve yapay/uydurma verilerin sisteme girmesini engellemek amacıyla alıntı doğrulaması yapılması ihtiyacı doğmuştur. Bu sorunları çözmek üzere platformda kapsamlı bir **Doğrulama, Normalizasyon ve Karşılaştırma Katmanı** hayata geçirilmiştir.

---

## 2. Geliştirilen İyileştirmeler ve Teknik Detaylar

### A. Türkçe Karakter ve Yazım Varyasyonları Normalizasyonu
* Farklı klavye düzenlerinden dolayı oluşabilecek karakter uyumsuzluklarını gidermek amacıyla evrensel bir dönüşüm sistemi kurulmuştur.
* `ı/İ/ğ/ü/ş/ö/ç` gibi Türkçe karakterler arka planda standart bir ASCII anahtarına dönüştürülerek normalize edilir.
* Bu sayede bitişik veya hatalı yazımlar dahi (örn: `VUKKANUNU`, `GELIRVERGISIKANUNU`) doğru şekilde eşleştirilip standart isimlerine (`Vergi Usul Kanunu`, `Gelir Vergisi Kanunu`) dönüştürülebilir. Sistem toplamda **8 farklı kanun kısaltmasını** ve **14 farklı yazım varyasyonunu** desteklemektedir.

### B. Madde Formatlarının Otomatik Ayrıştırılması (Complex Madde Parsing)
* Kullanıcılar madde alanına birleşik veya karmaşık formatlar girdiğinde, sistem alandan çıktığı anda (`onBlur` olayıyla) bunu otomatik olarak ayrıştırarak ilgili alanlara dağıtır:
  * `16/1-a` $\rightarrow$ Madde: `16`, Fıkra: `1`, Bent: `a` (Tam Format)
  * `17/5` $\rightarrow$ Madde: `17`, Fıkra: `5`, Bent: `(boş)` (Madde + Fıkra)
  * `17-a` $\rightarrow$ Madde: `17`, Fıkra: `(boş)`, Bent: `a` (Madde + Bent)
  * `13/a` $\rightarrow$ Madde: `13`, Fıkra: `(boş)`, Bent: `a` (Madde + Bent)
* Geçersiz veya belirsiz formatlarda (örn: `17--a`) kullanıcıya anında kırmızı hata uyarısı gösterilir ve formun hatalı kaydedilmesi engellenir.

### C. Kanun Numarası ve Adı Temizliği
* Kanun numarası girişlerindeki gereksiz boşluk, nokta, tire gibi karakterler temizlenir: `" 213. "` $\rightarrow$ `"213"`.
* Kanun adı kısaltmaları otomatik olarak tam isimlerine genişletilir (Örn: `VUK` $\rightarrow$ `Vergi Usul Kanunu`, `KVK` $\rightarrow$ `Kurumlar Vergisi Kanunu`).

### D. Fıkra ve Bent Alanlarında Akıllı Temizlik
* Parantez, tırnak, nokta gibi gürültülü karakterler temizlenir: `(a)` $\rightarrow$ `a`, `(A).` $\rightarrow$ `a`.
* 1'den 10'a kadar olan Türkçe sıra sayı sıfatları otomatik olarak sayısal karşılıklarına dönüştürülür: `birinci` $\rightarrow$ `1`, `ikinci` $\rightarrow$ `2`.

### E. Gevşek Alıntı Doğrulaması (Fuzzy Source Text Validation - Mert Temür Geri Bildirimi)
Kullanıcıların **Metinden Alıntı (source_text)** alanına tamamen uydurma veya geçersiz veri girmesini engellemek amacıyla, Mert Temür'ün geri bildirimi doğrultusunda gevşek bir doğrulama algoritması entegre edilmiştir. 
* **Çalışma Prensibi:** Kullanıcı alıntı metnini girerken, girilen metin ile belgenin ham metni (`pdf_text`) karşılaştırılır.
* **Fuzzy Normalizasyon:** Karşılaştırmadan önce her iki metin de küçük harfe dönüştürülür, Türkçe karakterler standartlaştırılır, tüm noktalama işaretleri ve boşluklar silinerek bitişik dizeler haline getirilir.
* **İki Kademeli Kontrol:**
  1. *Temizlenmiş Alt Dize Kontrolü:* Temizlenen alıntı, temizlenen dokümanın içinde tam alt dize olarak aranır. Bulunursa eşleşme başarılı kabul edilir.
  2. *Kelime Oranı Kontrolü (Fallback):* Alt dize eşleşmesi başarısız olursa (örneğin kullanıcı araya `...` veya ek kelimeler koyduysa), alıntıdaki en az 3 karakterli kelimelerin dokümanda bulunma oranı hesaplanır. Kelimelerin **%80'i veya daha fazlası** dokümanda geçiyorsa eşleşme geçerli sayılır.
* **Geri Bildirim Arayüzü:** Eşleşme başarısız olduğunda kullanıcıya kaydetmeyi engellemeyen ancak uyarı niteliğinde olan sarı renkli görsel uyarı gösterilir: *"Alıntı metni özelge gövdesinde bulunamadı. Lütfen kopyalamanın doğru yapıldığından emin olun."*

### F. Güvenlik, Validasyon ve Mükerrer Kayıt Engelleme
* Her referans kaydı öncesinde zorunlu alan kontrolleri yapılır. Normalizasyon sonrasında aynı değerlere sahip mükerrer referansların kaydedilmesi sunucu tarafında engellenerek `422` hata koduyla reddedilir.
* Aynı kanun ailesine ait hem spesifik hem de genel referanslar birlikte kaydedilmek istendiğinde; backend genel olan referansı otomatik olarak bastırır (suppress eder) ve kayıt kirliliğini önler.

---

## 3. Test ve Güvence
* Tüm normalizasyon, ayrıştırma ve fuzzy eşleşme kuralları hem frontend (**Vitest**) hem backend (**pytest**) katmanlarında olmak üzere toplamda **40'tan fazla test fonksiyonu** ile koruma altına alınmıştır.
* CI (Sürekli Entegrasyon) hattına entegre edilen bu testler, her deploy öncesinde otomatik olarak çalıştırılarak sistemin kararlılığı güvence altına alınmaktadır.
