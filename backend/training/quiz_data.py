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
import json
import sqlite3

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
            "Boş bir referans listesi ([]) ile 'Kaydet' işlemi yapılmalıdır — bu meşru bir durumdur.",
            "Sahte bir referans ekleyip kaydedilmelidir.",
            "Admin'e bildirim gönderilmelidir.",
        ],
        "correct_choice_idx": 1,
    },
    {
        "id": "q06",
        "text": "Kanun No ve Kanun Adı alanları için geçerli kural hangisidir?",
        "choices": [
            "Kanun No veya Kanun Adından en az biri zorunludur; ikisi birlikte verilirse tutarlı olmalıdır.",
            "Kanun No her zaman zorunludur; Kanun Adı tek başına yeterli değildir.",
            "İkisi de zorunludur, eksik olursa 422 döner.",
            "İkisi de opsiyoneldir, source_text yeterlidir.",
        ],
        "correct_choice_idx": 0,
    },
    {
        "id": "q07",
        "text": "Bir doküman üzerinde 'Kaydet' işlemi başarıyla tamamlandığında, kullanıcının doküman üzerindeki kilidine ne olur?",
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
            "İkincisi kilit çakışması görür ve 'Listeye dön' ile başka bir doküman seçebilir.",
            "Sistem otomatik olarak ikincinin oturumunu kapatır.",
            "İkisinden hangisi 'Kaydet'e önce basarsa onun girişi yazılır, diğerininki sessizce kaybolur.",
        ],
        "correct_choice_idx": 1,
    },
]


def get_active_quiz_questions(db: sqlite3.Connection) -> list[dict]:
    """Hybrid resolver: code baseline (QUIZ_QUESTIONS) + DB overrides
    (training_quiz_overrides). Symmetric with
    backend.training.service.get_active_gold_docs.

    Resolution rules:
      - For every code-baseline entry:
          * Override row with is_deleted=1 → exclude.
          * Override row present → merge (override fields win; NULL means
            fall back to code).
          * Otherwise → use code entry as-is.
      - For every override row with source='custom' AND is_deleted=0 AND
        question_id NOT in code baseline → append.
    """
    rows = db.execute(
        "SELECT question_id, is_deleted, text, choices_json, "
        "correct_choice_idx, source FROM training_quiz_overrides"
    ).fetchall()
    overrides = {r["question_id"]: r for r in rows}

    out: list[dict] = []
    seen: set[str] = set()
    for code in QUIZ_QUESTIONS:
        qid = code["id"]
        ov = overrides.get(qid)
        if ov is not None and ov["is_deleted"]:
            continue
        if ov is not None:
            text = ov["text"] if ov["text"] is not None else code["text"]
            choices = (
                json.loads(ov["choices_json"]) if ov["choices_json"] is not None
                else code["choices"]
            )
            cci = (
                ov["correct_choice_idx"] if ov["correct_choice_idx"] is not None
                else code["correct_choice_idx"]
            )
            out.append({
                "id": qid, "text": text,
                "choices": choices, "correct_choice_idx": cci,
            })
        else:
            out.append(dict(code))
        seen.add(qid)

    for qid, ov in overrides.items():
        if ov["source"] == "custom" and not ov["is_deleted"] and qid not in seen:
            out.append({
                "id": qid,
                "text": ov["text"],
                "choices": json.loads(ov["choices_json"]) if ov["choices_json"] else [],
                "correct_choice_idx": (
                    ov["correct_choice_idx"] if ov["correct_choice_idx"] is not None else 0
                ),
            })

    return out
