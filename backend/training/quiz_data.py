"""Domain-focused quiz questions for the training gate.

Format: each entry has `id`, `text`, `choices` (4 options), `correct_choice_idx`.
These questions avoid implementation terms and measure decisions an annotator
must make while reading an özelge.
"""
import json
import sqlite3

QUIZ_QUESTIONS: list[dict] = [
    {
        "id": "q01",
        "text": "Bir kanun atfı eklerken özelgeden ilgili cümleyi de alıntılamak neden zorunludur?",
        "choices": [
            "Belgenin daha uzun görünmesini sağlamak için.",
            "Atfın hangi ifadeden çıkarıldığını sonraki inceleyen kişinin doğrulayabilmesi için.",
            "Kanun adını otomatik olarak değiştirmek için.",
            "Belgenin tarihini belirlemek için.",
        ],
        "correct_choice_idx": 1,
    },
    {
        "id": "q02",
        "text": "Özelgede “Geçici 67'nci madde” yazıyorsa Madde alanına ne girilmelidir?",
        "choices": [
            "Geçici 5",
            "67",
            "Geçici 67",
            "Madde 67'nin tamamı",
        ],
        "correct_choice_idx": 2,
    },
    {
        "id": "q03",
        "text": "Kaynak veride gösterilen hazır kanun referanslarına nasıl yaklaşılmalıdır?",
        "choices": [
            "Kesin doğru kabul edilip aynen kaydedilmelidir.",
            "Yalnızca başlangıç ipucu olarak görülmeli, özelge metninden tek tek doğrulanmalıdır.",
            "Her durumda tamamen silinmelidir.",
            "Sadece kanun numarası varsa doğru kabul edilmelidir.",
        ],
        "correct_choice_idx": 1,
    },
    {
        "id": "q04",
        "text": "Özelgede aynı kanun maddesine ait aynı atıf iki kez görünüyorsa ne yapılmalıdır?",
        "choices": [
            "Aynı alıntı için iki özdeş referans kaydı oluşturulmalıdır.",
            "Tek bir referans kaydı oluşturulmalı; yinelenen özdeş kayıt eklenmemelidir.",
            "Doküman doğrudan atlanmalıdır.",
            "Kanun numarası boş bırakılmalıdır.",
        ],
        "correct_choice_idx": 1,
    },
    {
        "id": "q05",
        "text": "Bir özelge dokümanında hiçbir kanun atfı yoksa ne yapılmalı?",
        "choices": [
            "Doküman 'Atla' ile geçilmeli.",
            "Referans eklemeden kaydedilmelidir; atıf bulunmaması geçerli bir sonuçtur.",
            "Sahte bir referans ekleyip kaydedilmelidir.",
            "Kaynak verideki ilk referans kullanılmalıdır.",
        ],
        "correct_choice_idx": 1,
    },
    {
        "id": "q06",
        "text": "Kanun No ve Kanun Adı alanları için geçerli kural hangisidir?",
        "choices": [
            "Kanun No veya Kanun Adından en az biri zorunludur; ikisi birlikte verilirse tutarlı olmalıdır.",
            "Kanun No her zaman zorunludur; Kanun Adı tek başına yeterli değildir.",
            "İkisi de her durumda zorunludur.",
            "İkisi de boş bırakılabilir; yalnızca alıntı yeterlidir.",
        ],
        "correct_choice_idx": 0,
    },
    {
        "id": "q07",
        "text": "Bir dokümanı kaydetmeyi tamamladıktan sonra aynı dokümandaki çalışma kilidine ne olur?",
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
        "text": "Başka bir bursiyerin üzerinde çalıştığı dokümanı açmaya çalışırsan ne yapmalısın?",
        "choices": [
            "Aynı anda düzenlemeye devam edip önce kaydetmeye çalışmalısın.",
            "Kilit uyarısını dikkate alıp listeye dönerek başka bir doküman seçmelisin.",
            "Tarayıcıyı yenileyerek kilidi zorla almalısın.",
            "Diğer kullanıcının oturumunu kapatmalısın.",
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
