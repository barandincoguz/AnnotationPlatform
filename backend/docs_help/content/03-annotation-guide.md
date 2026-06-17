# Anotasyon Rehberi — Kanun Atıfı Nasıl Çıkarılır

Her referans kaydı bir kanun atfını temsil eder. **Kanun No** veya **Kanun Adı**
alanlarından en az biri ve **Metinden Alıntı** zorunludur. Madde, Fıkra ve Bent
özelgede belirtilmiyorsa boş bırakılabilir.

## Alanların ne anlama geldiği

### Kanun No
Kanunun sayısı. Özelgede "5520 sayılı Kanun" gibi geçer.

| Kısaltma | Kanun No | Kanun Adı |
|---|---|---|
| KVK | 5520 | Kurumlar Vergisi Kanunu |
| GVK | 193 | Gelir Vergisi Kanunu |
| KDV | 3065 | Katma Değer Vergisi Kanunu |
| VUK | 213 | Vergi Usul Kanunu |
| ÖTV | 4760 | Özel Tüketim Vergisi Kanunu |
| DV | 488 | Damga Vergisi Kanunu |
| Harçlar | 492 | Harçlar Kanunu |
| AATUHK | 6183 | Amme Alacaklarının Tahsil Usulü Hakkında Kanun |
| TTK | 6102 | Türk Ticaret Kanunu |
| TBK | 6098 | Türk Borçlar Kanunu |
| İYUK | 2577 | İdari Yargılama Usulü Kanunu |

### Kanun Adı
Kanunun tam veya yaygın adı (örn. "Kurumlar Vergisi Kanunu"). Bazı özelgeler sadece kısaltma kullanır ("KVK 5/1-a uyarınca..."); bu durumda kanun adını yine tam yaz, kısaltma değil. Sistem normalleştirme yapıyor ama tutarlılık için tam ad daha iyi.

### Madde
Kanunun atıf yapılan **madde numarası**. Örn. "5'inci madde" → `5`.

Özel formatlar:
- "Geçici 67'nci madde" → `Geçici 67`
- "Mükerrer 80" → `Mükerrer 80`
- "Mükerrer Geçici 1" → `Mükerrer Geçici 1`

Boşluklarda dert etme; sistem normalleştiriyor.

### Fıkra
Madde altındaki **fıkra numarası**. Sayı olarak yaz: `1`, `2`, `3` (romen "(1)" değil).

### Bent
Fıkra altındaki **bent harfi/numarası**. Genellikle `a`, `b`, `c` gibi tek harf; bazen `1`, `2` rakam olabilir. Küçük harfle yaz, parantez/nokta koyma.

### Metinden alıntı (zorunlu)
Özelgenin tam o atıfı yaptığı cümleyi veya kısa parçayı kopyala. Bu alan,
referansın kaynağının sonraki kullanıcı tarafından doğrulanabilmesi için
zorunludur.

## Örnek 1 — Klasik atıf

**Özelge metninde:**
> "5520 sayılı Kurumlar Vergisi Kanunu'nun 5'inci maddesinin birinci fıkrasının (a) bendi uyarınca tam mükellefiyete tabi kurumların..."

**Senin oluşturacağın referans:**

| Alan | Değer |
|---|---|
| Kanun No | `5520` |
| Kanun Adı | `Kurumlar Vergisi Kanunu` |
| Madde | `5` |
| Fıkra | `1` |
| Bent | `a` |
| Metinden alıntı | "5520 sayılı Kurumlar Vergisi Kanunu'nun 5'inci maddesinin birinci fıkrasının (a) bendi" |

## Örnek 2 — Geçici madde

**Özelge metninde:**
> "...193 sayılı Gelir Vergisi Kanunu'nun Geçici 67'nci maddesi kapsamında stopaj..."

**Referans:**

| Alan | Değer |
|---|---|
| Kanun No | `193` |
| Kanun Adı | `Gelir Vergisi Kanunu` |
| Madde | `Geçici 67` |
| Fıkra | (boş) |
| Bent | (boş) |

Fıkra/bent belirtilmemişse boş bırak — yanlış tahmin etmektense eksik bırakmak doğru.

## Örnek 3 — Sadece kısaltma + madde

**Özelge metninde:**
> "...KDV Kanunu 17/4-g istisnası kapsamında..."

**Referans:**

| Alan | Değer |
|---|---|
| Kanun No | `3065` |
| Kanun Adı | `Katma Değer Vergisi Kanunu` |
| Madde | `17` |
| Fıkra | `4` |
| Bent | `g` |

Kısaltmayı açarak yaz. "KDV" yazma — `Katma Değer Vergisi Kanunu` yaz.

## Örnek 4 — Birden fazla atıf

Bir özelge birden fazla kanuna/maddeye atıf yapabilir. Her atıf için **ayrı bir referans kartı** aç. Örnek:

> "...213 sayılı VUK'un 229'uncu maddesi ile 3065 sayılı KDV Kanunu'nun 35'inci maddesi birlikte değerlendirildiğinde..."

Bu cümle için **2 referans kartı** açarsın:
1. VUK 229 (Kanun No 213, Madde 229)
2. KDV 35 (Kanun No 3065, Madde 35)

## Örnek 5 — Sıfır atıf

Bazı özelgeler sadece olgusal açıklama içerir ve hiçbir somut kanun maddesine atıf yapmaz. Bu durumda **hiç referans eklemeden Kaydet** diyebilirsin. Sistem "boş kaydı" da değerli bir veri olarak işler.

## Yapmaman gerekenler

- ❌ "5/1-a" gibi serbest formatta tek alana yapıştırma → her parçayı ayrı alana yaz
- ❌ Atıfı tahmin etme: madde belirtilmemişse Madde alanını boş bırak
- ❌ Bent için "(a)" yazma → sadece `a`
- ❌ Fıkra için "birinci" yazma → `1`
- ❌ Kanun No'yu kanun adıyla karıştırma: 5520 numara, KVK ad

## Önemli

Bursiyer arkadaşların aynı özelgeye farklı sayıda referans çıkarmış olabilir. Onları "yanlış" olarak görme — bazen yorum farkı olur (örn. dolaylı atıf sayılır mı?). Eklemen/değiştirmen gereken bir şey varsa yap, aksi halde olduğu gibi kabul edip devam et.
