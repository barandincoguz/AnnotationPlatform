"""Static placeholder quiz questions for the training gate.

Format: each entry has `id`, `text`, `choices` (4 options), `correct_choice_idx`.
Admin override of these questions is out of scope for Paket 10 (planned for
Paket 11). For now, edit this file directly to update question content.

These 8 questions cover the most-needed concepts a bursiyer must know before
annotating real özelge documents:
  - Why source_text is required
  - Reference field semantics (kanun_no vs kanun_ad vs madde vs fikra vs bent)
  - Madde format ("Mükerrer 20", "Geçici 5")
  - is_diff_zero meaning
  - Duplicate-reference rule
  - Lock release timing
  - Skip vs save semantics
  - Empty-references-list legality
"""

QUIZ_QUESTIONS: list[dict] = [
    {
        "id": "q01",
        "text": "Bir referansta source_text alanı zorunludur. Aşağıdakilerden hangisi en doğru gerekçe?",
        "choices": [
            "Frontend'in alanı boş bırakmasını önlemek için.",
            "Sonraki kullanıcıların hangi metin parçasından çıkarıldığını görüp doğrulayabilmesi için.",
            "Veritabanı PRIMARY KEY kısıtlaması zorunlu kılıyor.",
            "Backup sistemi source_text alanına bakarak chunking yapıyor.",
        ],
        "correct_choice_idx": 1,
    },
    {
        "id": "q02",
        "text": "Madde alanı için aşağıdaki örneklerden hangisi GEÇERSİZDİR?",
        "choices": [
            "5",
            "Mükerrer 20",
            "Geçici 5",
            "Madde 5'in 1. fıkrasının a bendi",
        ],
        "correct_choice_idx": 3,
    },
    {
        "id": "q03",
        "text": "is_diff_zero=True ne anlama gelir?",
        "choices": [
            "Önceki kullanıcının bıraktığı referans listesi ile şu anki kayıt birebir aynı.",
            "Bu doküman henüz hiç anotasyonlanmamış.",
            "Kayıt sırasında bir hata oldu, hiçbir referans yazılmadı.",
            "Kullanıcı 'Atla' butonuna bastı.",
        ],
        "correct_choice_idx": 0,
    },
    {
        "id": "q04",
        "text": "Aynı dokümana aynı 6'lı tuple (kanun_no, kanun_ad, madde, fikra, bent, source_text) ile iki kez referans eklenirse ne olur?",
        "choices": [
            "İkincisi sessizce yok sayılır.",
            "Sistem 422 ile DuplicateReference hatası döndürür.",
            "Ledger'a iki ayrı satır olarak yazılır.",
            "İlk olan otomatik silinir.",
        ],
        "correct_choice_idx": 1,
    },
    {
        "id": "q05",
        "text": "Bir özelge dokümanında hiçbir kanun atfı yoksa ne yapılmalı?",
        "choices": [
            "Doküman 'Atla' ile geçilmeli.",
            "Boş bir referans listesi ([]) ile 'Sakla' edilmelidir — bu meşru bir durumdur.",
            "Sahte bir referans ekleyip kaydedilmelidir.",
            "Admin'e bildirim gönderilmelidir.",
        ],
        "correct_choice_idx": 1,
    },
    {
        "id": "q06",
        "text": "kanun_no ve kanun_ad birlikte verilirken hangi durum tipiktir?",
        "choices": [
            "kanun_no zorunlu, kanun_ad opsiyonel ama her ikisi de tutarlı olmalı (örn. 5520 → 'Kurumlar Vergisi Kanunu').",
            "Sadece kanun_ad yeterlidir; kanun_no opsiyonel.",
            "İkisi de zorunludur, eksik olursa 422 döner.",
            "İkisi de opsiyoneldir, source_text yeterlidir.",
        ],
        "correct_choice_idx": 0,
    },
    {
        "id": "q07",
        "text": "Bir doküman üzerinde 'Sakla' işlemi başarıyla tamamlandığında, kullanıcının dokümanı üzerindeki kilidiyle (lock) ne olur?",
        "choices": [
            "Kilit 5 dakika daha uzatılır.",
            "Kilit otomatik olarak serbest bırakılır.",
            "Kilit, kullanıcı 'Çıkış' yapana kadar kalır.",
            "Kilit yalnızca admin tarafından kaldırılabilir.",
        ],
        "correct_choice_idx": 1,
    },
    {
        "id": "q08",
        "text": "Aynı dokümanı iki bursiyer aynı anda anotasyonlamaya çalışırsa ne olur?",
        "choices": [
            "İkisi de aynı anda yazabilir, son kaydedenin verisi geçerli olur.",
            "İkincisi 409 Conflict alır ve modal ile 'Başka doc seç' yönlendirmesi yapılır.",
            "Sistem otomatik olarak ikincinin oturumunu kapatır.",
            "İkisinden hangisi 'Sakla'ya önce basarsa onun girişi yazılır, diğerininki sessizce kaybolur.",
        ],
        "correct_choice_idx": 1,
    },
]
