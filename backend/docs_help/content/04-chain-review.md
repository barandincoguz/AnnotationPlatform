# Chain Review — Birden Fazla Bursiyer

## Akış

A bursiyer bir özelgeyi annotate ederse, B bursiyer aynı özelgeyi açtığında A'nın çıkardığı **referans kartları zaten dolu** görünür. Her kartın yanında **"by Ahmet · 2 saat önce"** gibi attribution etiketi olur.

B ne yapabilir:

- A'nın referanslarını **olduğu gibi kabul edip** Sakla → diff = 0 (değişiklik yok)
- A'nın bir referansındaki alanları **düzenleyip** Sakla → diff > 0 (sistem hangi alanın değiştiğini loglar: örn. Madde alanı `5` iken `5/1` olduysa)
- A'nın kartlarını **silip kendi referanslarını** yazıp Sakla → diff = referans sayısı
- A'nın eksik bıraktığı bir atıfı fark edip **yeni bir kart ekleyip** Sakla → diff = 1

Sonra C gelir, B'nin son halini görür ve aynı şekilde devam eder. Zincir böyle uzar; her gözden geçirme bir önceki katmanın üstüne yazılır.

## "Tamamlandı" tag'i

`diff = 0` olduğunda (yani sen veya başka biri öncekinin üzerinde değişiklik yapmadıysa), arayüzde **"Bu özelgeyi tamamlandı olarak işaretle"** butonu çıkar. Tıklarsan ✓ rozeti özelgeye eklenir, listede görünür.

Bu **kilit değil** — sonraki bursiyer hâlâ düzenleyebilir, ama tamamlandı işareti referansların güvenilir olduğunu gösteren bir rehber niteliğindedir.

Tamamlandı tag'i kazandığın **+5 XP** demek (normal Sakla +1).

## Ne zaman değiştirir, ne zaman koruyun?

- ✅ Önceki bursiyer **kanun adını kısaltmış** ("KDV") → tam adı yaz ("Katma Değer Vergisi Kanunu")
- ✅ Önceki bursiyer **fıkrayı yazmamış** ama özelge metninde "birinci fıkra" diyor → ekle
- ✅ Önceki bursiyer bir referans kartını **eksik bırakmış** (özelgede 3 atıf var, A sadece 2 çıkarmış) → 3'üncüyü ekle
- ⚠️ Önceki bursiyer **bent için `(a)` yazmış** ama doğru format `a` → düzelt
- ❌ Sadece **bir terimi şahsi tercih** olarak değiştirme (örn. "Türk Borçlar Kanunu" → "TBK") — kanun adı tam yaz, kısaltma kullanma

## Eşzamanlı çalışma

Sen `doc_42`'yi açtığında otomatik kilit alırsın. Üst bardan herkese "Mehmet doc_42'de çalışıyor (3dk önce başladı)" bildirimi gider. Başka bir bursiyer aynı özelgeye tıklarsa "şu an X kullanıyor, başka özelge seç" mesajı görür. Sen 5dk hareketsiz kalırsan veya sekmeyi kapatırsan kilit otomatik kalkar; lock kalmadan başka bursiyer açabilir.
