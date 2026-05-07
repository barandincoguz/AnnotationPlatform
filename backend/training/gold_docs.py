"""Code-baseline gold-doc list for the training annotation challenge.

These 3 entries are PLACEHOLDER samples shipped with the codebase. The
expected production gold set will be loaded via the CLI subcommand
`python -m backend.cli import-gold-docs <path>` as overrides in the
`training_gold_doc_overrides` table — see backend/cli.py and the hybrid
resolver in `backend.training.service.get_active_gold_docs`.

Format:
  gold_id            — stable identifier (used by overrides table)
  content            — full özelge text the user reads while annotating
  expected_concepts  — list of partial-tuple dicts; subset semantics:
                       a user reference matches a concept iff every
                       non-empty key in the concept is identically
                       present in the user's reference. source_text
                       is never compared.
  min_concept_count  — minimum number of concepts the user must hit
                       to pass this gold doc.
"""

GOLD_DOCS: list[dict] = [
    {
        "gold_id": "sample_kvk_5",
        "content": (
            "Mükellef, Kurumlar Vergisi Kanunu'nun 5'inci maddesinin 1. fıkrasının (a) bendi "
            "uyarınca iştirak kazançları istisnasından faydalanıp faydalanamayacağını sormaktadır. "
            "Anılan madde hükmüne göre, tam mükellefiyete tabi başka bir kurumun sermayesine "
            "katılım nedeniyle elde edilen kâr payları kurumlar vergisinden müstesnadır."
        ),
        "expected_concepts": [
            {"kanun_no": "5520", "madde": "5"},
            {"kanun_no": "5520", "madde": "5", "fikra": "1", "bent": "a"},
        ],
        "min_concept_count": 1,
    },
    {
        "gold_id": "sample_kdv_29",
        "content": (
            "Mükellef tarafından yapılan ihracat işlemine ilişkin olarak Katma Değer Vergisi "
            "Kanunu'nun 29. maddesi 1. fıkrasının (a) bendi gereğince yüklenilen KDV'nin iadesinin "
            "talep edilebileceği belirtilmektedir. Aynı kanunun 32. maddesi de bu kapsamda "
            "değerlendirilebilir."
        ),
        "expected_concepts": [
            {"kanun_no": "3065", "madde": "29"},
            {"kanun_no": "3065", "madde": "32"},
        ],
        "min_concept_count": 1,
    },
    {
        "gold_id": "sample_gvk_geçici_67",
        "content": (
            "Hisse senedi alım-satım kazançları için Gelir Vergisi Kanunu'nun Geçici 67'nci maddesi "
            "uyarınca tevkifat uygulaması söz konusudur. Aynı kanunun mükerrer 80'inci maddesi de "
            "değer artış kazançlarını düzenlemektedir."
        ),
        "expected_concepts": [
            {"kanun_no": "193", "madde": "Geçici 67"},
            {"kanun_no": "193", "madde": "Mükerrer 80"},
        ],
        "min_concept_count": 1,
    },
]
