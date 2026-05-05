# Sık Sorulan Sorular

## "Aynı dokümanı sürekli görüyorum, bu normal mi?"
Hayır. Eğer bir doküman sana 3+ kez geliyorsa admin'e söyle — shuffle algoritmasında bir bug olabilir.

## "Yanlışlıkla tamamlandı dedim, geri alabilir miyim?"
Evet. Aynı doküman üstüne tıkla → "Tamamlandıyı kaldır" butonuna bas. Action loglara kayıt edilir ama kötü bir şey değil.

## "Şifremi unuttum"
Şu an "şifre sıfırla" akışı yok. Admin'e başvur, sana yeni şifre verir. (Paket 11'de admin panelden bunu kendi yapabilir.)

## "Yazdığım soru çok uzun oldu, kırmızı uyarı geldi ama Sakla çalışıyor. Hata mı var?"
Hata yok — kırmızı uyarı sadece "kısalt" rica eder, blocking değil. Yine de o uyarıyı dikkate al; çok uzun sorular sonradan arama indeksine kötü etki ediyor.

## "Diğer bursiyerlerin yazdığı her soruyu beğeniyorum ama 'Sakla' diyorum, +5 hak ediyor muyum?"
Hayır. Sadece **sen `is_completed` butonuna bastığında** +5 alırsın. Pasif kabul (boş textarea'larda dolu cevap olduğu için Sakla'ya basmak) +1'dir. Ama "evet bu cevap doğru" hissini ifade etmek için tamamlandı işareti var, kullan.

## "Ekranda hep aynı isim 'çalışıyor' yazıyor"
Üst barda online bursiyerler ve onların açtıkları dokümanlar görünür. Bir kullanıcı 5 dakikadan uzun süre hareketsiz kalırsa kilit otomatik düşer. Sen tıkladığında hâlâ kilitli görünüyorsa sayfayı yenile.

## "Atla ile Skip arasında fark var mı?"
İkisi aynı şey — UI'da sadece "Atla" yazar.
