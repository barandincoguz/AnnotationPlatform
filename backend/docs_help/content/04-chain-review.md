# Chain Review — Birden Fazla Bursiyer

## Akış

A bursiyer bir özelgeyi annotate ederse, B bursiyer aynı özelgeyi açtığında A'nın çıkardığı **referans kartları zaten dolu** görünür. Her kartın yanında **"by Ahmet · 2 saat önce"** gibi attribution etiketi olur.

B ne yapabilir:

- A'nın referanslarını **olduğu gibi kabul edip** Kaydet → diff = 0 (değişiklik yok)
- A'nın bir referansındaki alanları **düzenleyip** Kaydet → diff > 0 (sistem hangi alanın değiştiğini kaydeder)
- A'nın kartlarını **silip kendi referanslarını** yazıp Kaydet → değişiklikler sürüm geçmişine yazılır
- A'nın eksik bıraktığı bir atfı fark edip **yeni bir kart ekleyip** Kaydet → yeni referans kaydedilir

Sonra C gelir, B'nin son halini görür ve aynı şekilde devam eder. Zincir böyle uzar; her gözden geçirme bir önceki katmanın üstüne yazılır.

## "Tamamlandı" tag'i

Referansların geçerliyse **Tamamla** düğmesiyle özelgeyi tamamlandı olarak
işaretleyebilirsin. Doküman daha sonra **Tamamlanan** sekmesinde görünür.

Bu **kilit değil** — sonraki bursiyer hâlâ düzenleyebilir, ama tamamlandı işareti referansların güvenilir olduğunu gösteren bir rehber niteliğindedir.

Tamamlama işlemi **+5 XP** kazandırır (normal Kaydet +1).

## Ne zaman değiştirir, ne zaman koruyun?

- ✅ Önceki bursiyer **kanun adını kısaltmış** ("KDV") → tam adı yaz ("Katma Değer Vergisi Kanunu")
- ✅ Önceki bursiyer **fıkrayı yazmamış** ama özelge metninde "birinci fıkra" diyor → ekle
- ✅ Önceki bursiyer bir referans kartını **eksik bırakmış** (özelgede 3 atıf var, A sadece 2 çıkarmış) → 3'üncüyü ekle
- ⚠️ Önceki bursiyer **bent için `(a)` yazmış** ama doğru format `a` → düzelt
- ❌ Sadece **bir terimi şahsi tercih** olarak değiştirme (örn. "Türk Borçlar Kanunu" → "TBK") — kanun adı tam yaz, kısaltma kullanma

## Eşzamanlı çalışma

Sen `doc_42`'yi açtığında otomatik kilit alırsın. Üst bardan herkese "Mehmet doc_42'de çalışıyor (3dk önce başladı)" bildirimi gider. Başka bir bursiyer aynı özelgeye tıklarsa "şu an X kullanıyor, başka özelge seç" mesajı görür. Sen 5dk hareketsiz kalırsan veya sekmeyi kapatırsan kilit otomatik kalkar; lock kalmadan başka bursiyer açabilir.
