# Chain Review — Birden Fazla Bursiyer

## Akış

A bursiyer bir dokümanı annotate ederse, B bursiyer aynı dokümanı açtığında A'nın yazdığı 3 soru zaten textarea'larda dolu görünür. Ayrıca her sorunun yanında **"by Ahmet · 2 saat önce"** gibi attribution etiketi olur.

B ne yapabilir:
- A'nın sorularını **olduğu gibi kabul edip** Sakla → diff = 0 (değişiklik yok)
- A'nın sorularını **düzenleyip** Sakla → diff > 0 (sistem hangi alanın değiştiğini loglar)
- A'nın sorularını **silip kendi sorularını** yazıp Sakla → diff = 3

Sonra C gelir, B'nin son halini görür ve aynı şekilde devam eder. Zincir böyle uzar.

## "Tamamlandı" Tag'i

`diff = 0` olduğunda (yani sen veya başka biri öncekinin üzerinde değişiklik yapmadıysa), arayüzde **"Bu doküman tamamlandı olarak işaretle"** butonu çıkar. Tıklarsan ✓ rozeti dokümana eklenir, listede görünür. Bu **kilit değil** — sonraki bursiyer hâlâ düzenleyebilir, ama tamamlandı işareti rehber niteliğinde durur.

Tamamlandı tag'i kazandığın **+5 XP** demek (normal Sakla +1).

## Eşzamanlı Çalışma

Sen `doc_42`'yi açtığında bir bursiyer kilit alır. Üst bardan herkese "Mehmet doc_42'de çalışıyor (3dk önce başladı)" bildirimi gider. Başka bir bursiyer aynı dokümana tıklarsa "şu an X kullanıyor, başka doküman seç" mesajı görür. Sen 5dk hareketsiz kalırsan veya sekmeyi kapatırsan kilit otomatik kalkar.
