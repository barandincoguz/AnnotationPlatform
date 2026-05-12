# Sık Sorulan Sorular

## "Bir özelgede hiç kanun atfı yoksa ne yapacağım?"
Boş kaydet — hiç referans kartı açmadan `Sakla` yeterli. "Bu özelge atıf içermiyor" da değerli bir veri. Endişelenme, +1 XP alırsın.

## "Bir cümlede birden fazla atıf varsa (örn. 'VUK 229 ile KDV 35 birlikte')?"
Her atıf için **ayrı referans kartı** aç. İki ayrı kanunu tek karta sığdırma; sistem her kartı bağımsız bir referans olarak indeksliyor.

## "Geçici madde nasıl yazılır?"
Madde alanına `Geçici 67` yaz (boşlukla). "GVK G.67" gibi serbest format yazma. Mükerrer için de aynı: `Mükerrer 80`. Sistem her ikisinde de normalleştirme yapar ama tutarlılık için tam yaz.

## "Bent için '(a)' mı 'a' mı?"
Sadece `a`. Parantez veya nokta koyma. Sistem normalleştirme yapıyor ama temiz veri girmek herkes için iyi.

## "Kanun adını kısaltma olarak yazsam (KDV) çalışır mı?"
Backend kabul eder ama önerilmez. Tam ad yaz: `Katma Değer Vergisi Kanunu`. Arama indeksi tutarlılık için tam ada bakıyor.

## "Aynı özelgeyi sürekli görüyorum, bu normal mi?"
Hayır. Eğer bir özelge sana 3+ kez geliyorsa admin'e söyle — shuffle algoritmasında bir bug olabilir.

## "Yanlışlıkla tamamlandı dedim, geri alabilir miyim?"
Evet. Aynı özelge üstüne tıkla → "Tamamlandıyı kaldır" butonuna bas. Aksiyon loglara kaydedilir ama kötü bir şey değil.

## "Şifremi unuttum"
Şu an "şifre sıfırla" self-service akışı yok. Admin'e başvur, sana yeni şifre verir veya admin paneli üzerinden hesabını sıfırlar.

## "Yazdığım alıntı çok uzun oldu, kırmızı uyarı geldi ama Sakla çalışıyor. Hata mı var?"
Hata yok — kırmızı uyarı sadece "kısalt" rica eder, blocking değil. Yine de o uyarıyı dikkate al; sadece atıfın geçtiği cümleyi al, tüm paragrafı kopyalama.

## "Önceki bursiyerin yazdığı her referansı beğeniyorum, +5 hak ediyor muyum?"
Hayır. Sadece **sen `Tamamlandı` butonuna bastığında** +5 alırsın. Pasif kabul (referanslar zaten dolu olduğu için Sakla'ya basmak) +1'dir. Tamamlandı işareti referansların güvenilir olduğuna dair açık beyandır, kullan.

## "Ekranda hep aynı isim 'çalışıyor' yazıyor"
Üst barda online bursiyerler ve onların açtıkları özelgeler görünür. Bir kullanıcı 5 dakikadan uzun süre hareketsiz kalırsa kilit otomatik düşer. Sen tıkladığında hâlâ kilitli görünüyorsa sayfayı yenile.

## "Atla ile Skip arasında fark var mı?"
İkisi aynı şey — UI'da sadece "Atla" yazar.

## "Bir referansın opsiyonel alanlarını boş bırakırsam o referans 'eksik' sayılır mı?"
Hayır. Opsiyonel alanlar tam olarak bu yüzden opsiyonel — özelge belirtmemişse sen de yazma. "Eksik bilgi" eksik olarak kaydedilir, "yanlış tahmin" değil.

## "Source text (metinden alıntı) alanını her zaman doldurmalı mıyım?"
Hayır, opsiyonel. Faydalı bir traceability sinyali ama doldurmazsan annotation eksik sayılmaz. Vaktinin yetmediği durumlarda atla.

## "Eğitimi atladım/Eğitimi geçemedim, ne olacak?"
Eğitimi atladıysan (kırmızı "Eğitimi geç" linki) hesabın aktif kalır ama admin panelinde flag'lenir. 3 deneme hakkını kaybettiysen admin'in seni resetlemesi gerekir.
