"""Pure-function reference normalization, deduping, and set-semantic diff."""

import re
import unicodedata
from typing import Optional

REFERENCE_FIELDS = (
    "kanun_no",
    "kanun_ad",
    "madde",
    "fikra",
    "bent",
    "source_text",
)

ORDINAL_MAP = {
    "BIRINCI": "1",
    "IKINCI": "2",
    "UCUNCU": "3",
    "DORDUNCU": "4",
    "BESINCI": "5",
    "ALTINCI": "6",
    "YEDINCI": "7",
    "SEKIZINCI": "8",
    "DOKUZUNCU": "9",
    "ONUNCU": "10",
}

LAW_ABBREVIATIONS = {
    "VUK": "Vergi Usul Kanunu",
    "GVK": "Gelir Vergisi Kanunu",
    "KDVK": "Katma Değer Vergisi Kanunu",
    "KDV": "Katma Değer Vergisi Kanunu",
    "KVK": "Kurumlar Vergisi Kanunu",
    "OTVK": "Özel Tüketim Vergisi Kanunu",
    "OTV": "Özel Tüketim Vergisi Kanunu",
    "DVK": "Damga Vergisi Kanunu",
    "HK": "Harçlar Kanunu",
    "AATUHK": "Amme Alacaklarının Tahsil Usulü Hakkında Kanun",
    "AATUK": "Amme Alacaklarının Tahsil Usulü Hakkında Kanun",
    "MTVK": "Motorlu Taşıtlar Vergisi Kanunu",
    "MTV": "Motorlu Taşıtlar Vergisi Kanunu",
    "BGK": "Belediye Gelirleri Kanunu",
    "GK": "Gümrük Kanunu",
    "EVK": "Emlak Vergisi Kanunu",
    "GIVK": "Gider Vergileri Kanunu",
    "GIV": "Gider Vergileri Kanunu",
    "VIVK": "Veraset ve İntikal Vergisi Kanunu",
    "VIV": "Veraset ve İntikal Vergisi Kanunu",
    "KVKK": "Kişisel Verilerin Korunması Kanunu",
    "SBK": "Serbest Bölgeler Kanunu",
    "TGBK": "Teknoloji Geliştirme Bölgeleri Kanunu",
    "SSGSSK": "Sosyal Sigortalar ve Genel Sağlık Sigortası Kanunu",
    "SGK": "Sosyal Sigortalar ve Genel Sağlık Sigortası Kanunu",
    "IK": "İş Kanunu",
    "TTK": "Türk Ticaret Kanunu",
    "TMK": "Türk Medeni Kanunu",
    "TBK": "Türk Borçlar Kanunu",
    "HMK": "Hukuk Muhakemeleri Kanunu",
    "CMK": "Ceza Muhakemesi Kanunu",
    "TCK": "Türk Ceza Kanunu",
    "IIK": "İcra ve İflas Kanunu",
    "DMK": "Devlet Memurları Kanunu",
    "IYUK": "İdari Yargılama Usulü Kanunu",
    "IYK": "İdari Yargılama Usulü Kanunu",
}

LAW_NUMBER_BY_NAME = {
    "Vergi Usul Kanunu": "213",
    "Gelir Vergisi Kanunu": "193",
    "Kurumlar Vergisi Kanunu": "5520",
    "Katma Değer Vergisi Kanunu": "3065",
    "Özel Tüketim Vergisi Kanunu": "4760",
    "Damga Vergisi Kanunu": "488",
    "Harçlar Kanunu": "492",
    "Amme Alacaklarının Tahsil Usulü Hakkında Kanun": "6183",
    "Motorlu Taşıtlar Vergisi Kanunu": "197",
    "Belediye Gelirleri Kanunu": "2464",
    "Gümrük Kanunu": "4458",
    "Emlak Vergisi Kanunu": "1319",
    "Gider Vergileri Kanunu": "6802",
    "Veraset ve İntikal Vergisi Kanunu": "7338",
    "Kişisel Verilerin Korunması Kanunu": "6698",
    "Serbest Bölgeler Kanunu": "3218",
    "Teknoloji Geliştirme Bölgeleri Kanunu": "4691",
    "Sosyal Sigortalar ve Genel Sağlık Sigortası Kanunu": "5510",
    "İş Kanunu": "4857",
    "Türk Ticaret Kanunu": "6102",
    "Türk Medeni Kanunu": "4721",
    "Türk Borçlar Kanunu": "6098",
    "Hukuk Muhakemeleri Kanunu": "6100",
    "Ceza Muhakemesi Kanunu": "5271",
    "Türk Ceza Kanunu": "5237",
    "İcra ve İflas Kanunu": "2004",
    "Devlet Memurları Kanunu": "657",
    "İdari Yargılama Usulü Kanunu": "2577",
}

LAW_NAME_ALIASES = {
    "VERGIUSULKANUNU": "Vergi Usul Kanunu",
    "VERGIUSUL": "Vergi Usul Kanunu",
    "VUKKANUNU": "Vergi Usul Kanunu",
    "GELIRVERGISIKANUNU": "Gelir Vergisi Kanunu",
    "GELIRVERGISI": "Gelir Vergisi Kanunu",
    "GVKKANUNU": "Gelir Vergisi Kanunu",
    "KURUMLARVERGISIKANUNU": "Kurumlar Vergisi Kanunu",
    "KURUMLARVERGISI": "Kurumlar Vergisi Kanunu",
    "KVKKANUNU": "Kurumlar Vergisi Kanunu",
    "KATMADEGERVERGISIKANUNU": "Katma Değer Vergisi Kanunu",
    "KATMADEGERVERGISI": "Katma Değer Vergisi Kanunu",
    "KATMADEGERVERGISIKDVKANUNU": "Katma Değer Vergisi Kanunu",
    "KDVKANUNU": "Katma Değer Vergisi Kanunu",
    "KDVKANUN": "Katma Değer Vergisi Kanunu",
    "OZELTUKETIMVERGISIKANUNU": "Özel Tüketim Vergisi Kanunu",
    "OZELTUKETIMVERGISI": "Özel Tüketim Vergisi Kanunu",
    "OTVKANUNU": "Özel Tüketim Vergisi Kanunu",
    "DAMGAVERGISIKANUNU": "Damga Vergisi Kanunu",
    "DAMGAVERGISI": "Damga Vergisi Kanunu",
    "DVKKANUNU": "Damga Vergisi Kanunu",
    "HARCLARKANUNU": "Harçlar Kanunu",
    "HARCLAR": "Harçlar Kanunu",
    "HKKANUNU": "Harçlar Kanunu",
    "AMMEALACAKLARININTAHSILUSULUHAKKINDAKANUN": "Amme Alacaklarının Tahsil Usulü Hakkında Kanun",
    "AMMEALACAKLARININTAHSILUSULUHAKKINDAKANUNU": "Amme Alacaklarının Tahsil Usulü Hakkında Kanun",
    "AMMEALACAKLARININTAHSILUSULU": "Amme Alacaklarının Tahsil Usulü Hakkında Kanun",
    "AATUHKKANUNU": "Amme Alacaklarının Tahsil Usulü Hakkında Kanun",
    "AATUKKANUNU": "Amme Alacaklarının Tahsil Usulü Hakkında Kanun",
    "MOTORLUTASITLARVERGISIKANUNU": "Motorlu Taşıtlar Vergisi Kanunu",
    "MOTORLUTASITLARVERGISI": "Motorlu Taşıtlar Vergisi Kanunu",
    "MTVKANUNU": "Motorlu Taşıtlar Vergisi Kanunu",
    "MTVKKANUNU": "Motorlu Taşıtlar Vergisi Kanunu",
    "BELEDIYEGELIRLERIKANUNU": "Belediye Gelirleri Kanunu",
    "BELEDIYEGELIRLERI": "Belediye Gelirleri Kanunu",
    "BGKKANUNU": "Belediye Gelirleri Kanunu",
    "GUMRUKKANUNU": "Gümrük Kanunu",
    "GUMRUK": "Gümrük Kanunu",
    "GKKANUNU": "Gümrük Kanunu",
    "EMLAKVERGISIKANUNU": "Emlak Vergisi Kanunu",
    "EMLAKVERGISI": "Emlak Vergisi Kanunu",
    "EVKKANUNU": "Emlak Vergisi Kanunu",
    "GIDERVERGILERIKANUNU": "Gider Vergileri Kanunu",
    "GIDERVERGILERI": "Gider Vergileri Kanunu",
    "GIVKKANUNU": "Gider Vergileri Kanunu",
    "VERASETVEINTIKALVERGISIKANUNU": "Veraset ve İntikal Vergisi Kanunu",
    "VERASETVEINTIKALVERGISI": "Veraset ve İntikal Vergisi Kanunu",
    "VIVKKANUNU": "Veraset ve İntikal Vergisi Kanunu",
    "KISISELVERILERINKORUNMASIKANUNU": "Kişisel Verilerin Korunması Kanunu",
    "KISISELVERILERINKORUNMASI": "Kişisel Verilerin Korunması Kanunu",
    "KVKKKANUNU": "Kişisel Verilerin Korunması Kanunu",
    "SERBESTBOLGELERKANUNU": "Serbest Bölgeler Kanunu",
    "SERBESTBOLGELER": "Serbest Bölgeler Kanunu",
    "SBKKANUNU": "Serbest Bölgeler Kanunu",
    "TEKNOLOJIGELISTIRMEBOLGELERIKANUNU": "Teknoloji Geliştirme Bölgeleri Kanunu",
    "TEKNOLOJIGELISTIRMEBOLGELERI": "Teknoloji Geliştirme Bölgeleri Kanunu",
    "TGBKKANUNU": "Teknoloji Geliştirme Bölgeleri Kanunu",
    "SOSYALSIGORTALARVEGENELSAGLIKSIGORTASIKANUNU": "Sosyal Sigortalar ve Genel Sağlık Sigortası Kanunu",
    "SOSYALSIGORTALARVEGENELSAGLIKSIGORTASI": "Sosyal Sigortalar ve Genel Sağlık Sigortası Kanunu",
    "SSGSSKKANUNU": "Sosyal Sigortalar ve Genel Sağlık Sigortası Kanunu",
    "SGKKANUNU": "Sosyal Sigortalar ve Genel Sağlık Sigortası Kanunu",
    "ISKANUNU": "İş Kanunu",
    "IS": "İş Kanunu",
    "IKKANUNU": "İş Kanunu",
    "TURKTICARETKANUNU": "Türk Ticaret Kanunu",
    "TURKTICARET": "Türk Ticaret Kanunu",
    "TTKKANUNU": "Türk Ticaret Kanunu",
    "TURKMEDENIKANUNU": "Türk Medeni Kanunu",
    "TURKMEDENI": "Türk Medeni Kanunu",
    "TMKKANUNU": "Türk Medeni Kanunu",
    "TURKBORCLARKANUNU": "Türk Borçlar Kanunu",
    "TURKBORCLAR": "Türk Borçlar Kanunu",
    "TBKKANUNU": "Türk Borçlar Kanunu",
    "HUKUKMUHAKEMELERIKANUNU": "Hukuk Muhakemeleri Kanunu",
    "HUKUKMUHAKEMELERI": "Hukuk Muhakemeleri Kanunu",
    "HMKKANUNU": "Hukuk Muhakemeleri Kanunu",
    "CEZAMUHAKEMESIKANUNU": "Ceza Muhakemesi Kanunu",
    "CEZAMUHAKEMESI": "Ceza Muhakemesi Kanunu",
    "CMKKANUNU": "Ceza Muhakemesi Kanunu",
    "TURKCEZAKANUNU": "Türk Ceza Kanunu",
    "TURKCEZA": "Türk Ceza Kanunu",
    "TCKKANUNU": "Türk Ceza Kanunu",
    "ICRAVEIFLASKANUNU": "İcra ve İflas Kanunu",
    "ICRAVEIFLAS": "İcra ve İflas Kanunu",
    "IIKKANUNU": "İcra ve İflas Kanunu",
    "DEVLETMEMURLARIKANUNU": "Devlet Memurları Kanunu",
    "DEVLETMEMURLARI": "Devlet Memurları Kanunu",
    "DMKKANUNU": "Devlet Memurları Kanunu",
    "IDARIYARGILAMAUSULUKANUNU": "İdari Yargılama Usulü Kanunu",
    "IDARIYARGILAMAUSULU": "İdari Yargılama Usulü Kanunu",
    "IYUKKANUNU": "İdari Yargılama Usulü Kanunu",
}

KNOWN_ABBREVIATIONS = [
    "AATUHK", "SSGSSK", "TGBK", "AATUK", "MTVK", "GIVK", "VIVK", "KVKK", "IYUK", "KDVK", "OTVK",
    "VUK", "GVK", "KDV", "KVK", "OTV", "DVK", "MTV", "BGK", "EVK", "GIV", "VIV", "SBK", "SGK",
    "TTK", "TMK", "TBK", "HMK", "CMK", "TCK", "IIK", "DMK", "IYK", "HK", "GK", "IK"
]

RE_NON_NO_CHARS = re.compile(r"[^0-9A-Za-z/-]+")
RE_MULTI_SPACE = re.compile(r"\s+")


class InvalidReference(ValueError):
    """source_text missing or empty."""


class DuplicateReference(ValueError):
    """Two refs in the same list have identical canonical keys."""


def _clean(value: Optional[object]) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def collapse_ws(text: str) -> str:
    return RE_MULTI_SPACE.sub(" ", text).strip()


def normalize_kanun_no(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = RE_NON_NO_CHARS.sub("", collapse_ws(str(value)))
    cleaned = cleaned.strip("/-")
    return cleaned if cleaned else None


def _normalize_turkish_key(text: str) -> str:
    # Lowercase and replace Turkish dotless ı and capital İ first
    t = (
        text.lower()
        .replace("ı", "i")
        .replace("ş", "s")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ö", "o")
        .replace("ç", "c")
    )
    value = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^A-Za-z0-9]+", "", value).upper()
    return value


def clean_parentheses(text: str) -> str:
    # Remove anything inside parentheses, brackets or braces, e.g. (KVK) -> ""
    return re.sub(r"\s*[\(\[\{][^\(\)\[\]\{\}]*[\)\]\}]\s*", " ", text)


def normalize_kanun_adi(text: Optional[str], kanun_no: str = "") -> Optional[str]:
    if not text:
        return None
    
    # 1. Clean parenthetical expressions like "Kurumlar Vergisi (KVK) Kanunu" -> "Kurumlar Vergisi Kanunu"
    cleaned = clean_parentheses(text)
    raw = collapse_ws(cleaned)
    if not raw:
        return None
        
    upper_key = _normalize_turkish_key(raw)
    
    # 2. Try direct match
    if upper_key in LAW_ABBREVIATIONS:
        return LAW_ABBREVIATIONS[upper_key]
    if upper_key in LAW_NAME_ALIASES:
        return LAW_NAME_ALIASES[upper_key]
        
    # 3. Try matching abbreviation + suffix (e.g. KVK'nın -> KVKNIN -> KVK)
    suffix_pattern = r"^(?:NIN|NUN|IN|UN|YA|YE|A|E|YI|YU|I|U|DA|DE|TA|TE|DAN|DEN|TAN|TEN|CA|CE|LAR|LER|LARI|LERI|LARIN|LERIN|LARINA|LERINE|LARININ|LERININ|LARINDA|LERINDE|LARINDAN|LERINDAN|LERINDEN|LARINI|LERINI|LARICA|LERICE|NU|NI|NA|NE|NDA|NDE|NDAN|NDEN|CA|CE|LA|LE)*$"
    for abbr in KNOWN_ABBREVIATIONS:
        if upper_key.startswith(abbr):
            suffix = upper_key[len(abbr):]
            if re.match(suffix_pattern, suffix):
                abbr_val = LAW_ABBREVIATIONS.get(abbr)
                if abbr_val:
                    return abbr_val
                    
    # 4. Try matching law name ending with "KANUN..." + suffix (e.g. Kurumlar Vergisi Kanununun -> KURUMLARVERGISIKANUNUNUN -> KURUMLARVERGISIKANUNU)
    suffix_pat_non_anchored = r"(?:NIN|NUN|IN|UN|YA|YE|A|E|YI|YU|I|U|DA|DE|TA|TE|DAN|DEN|TAN|TEN|CA|CE|LAR|LER|LARI|LERI|LARIN|LERIN|LARINA|LERINE|LARININ|LERININ|LARINDA|LERINDE|LARINDAN|LERINDAN|LERINDEN|LARINI|LERINI|LARICA|LERICE|NU|NI|NA|NE|NDA|NDE|NDAN|NDEN|CA|CE|LA|LE)*"
    replaced_key = re.sub(r"KANUN" + suffix_pat_non_anchored + r"$", "KANUNU", upper_key)
    if replaced_key in LAW_NAME_ALIASES:
        return LAW_NAME_ALIASES[replaced_key]
        
    # 5. Try matching law name base (without "KANUNU") + suffix (e.g. Kurumlar Vergisi'nde -> KURUMLARVERGISINDE -> KURUMLARVERGISI)
    for alias_key, canonical in LAW_NAME_ALIASES.items():
        if not alias_key.endswith("KANUNU") and not alias_key.endswith("KANUN"):
            if upper_key.startswith(alias_key):
                suffix = upper_key[len(alias_key):]
                if re.match(suffix_pattern, suffix):
                    return canonical
                    
    return raw


def normalize_identifier(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    raw = collapse_ws(str(value)).strip("()[]{}., '\"`")
    key = _normalize_turkish_key(raw)
    if not raw:
        return None
    if key in ORDINAL_MAP:
        return ORDINAL_MAP[key]
    if any(ch.isalpha() for ch in raw):
        return raw.lower()
    return raw


def normalize_madde(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    raw = collapse_ws(str(value))
    raw = re.sub(r"^madd\w*\s+", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*madd\w*$", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"(?:[iıuü]nc[iıuü]|nc[iıuü])$", "", raw, flags=re.IGNORECASE)
    raw = raw.strip(" .()")
    return raw if raw else None


def _clean_identifier_part(part: str) -> str:
    value = normalize_identifier(part)
    if not value or "/" in value or "-" in value:
        raise InvalidReference(
            "madde format is invalid. Use formats like 17/5-a, 17/5, or 17-a."
        )
    return value


def _reject_invalid_madde_format() -> None:
    raise InvalidReference(
        "madde format is invalid. Use formats like 17/5-a, 17/5, or 17-a."
    )


def parse_madde_token(token: Optional[str]) -> tuple[str, str, str]:
    cleaned = normalize_madde(token)
    if not cleaned:
        return "", "", ""

    slash_count = cleaned.count("/")
    dash_count = cleaned.count("-")
    if slash_count > 1 or dash_count > 1:
        _reject_invalid_madde_format()

    if slash_count == 0 and dash_count == 0:
        return cleaned, "", ""

    if "/" in cleaned:
        left, right = (part.strip() for part in cleaned.split("/", 1))
        if not left or not right or "-" in left:
            _reject_invalid_madde_format()

        if "-" in right:
            first, second = (part.strip() for part in right.split("-", 1))
            if not first or not second or not first.isdigit():
                _reject_invalid_madde_format()
            return left, first, _clean_identifier_part(second)

        if right.isdigit():
            return left, right, ""
        return left, "", _clean_identifier_part(right)

    left, right = (part.strip() for part in cleaned.split("-", 1))
    if not left or not right:
        _reject_invalid_madde_format()
    return left, "", _clean_identifier_part(right)


def normalize_reference(ref: dict) -> dict:
    source_text = _clean(ref.get("source_text"))
    if not source_text:
        raise InvalidReference("source_text is required")

    kanun_no = normalize_kanun_no(_clean(ref.get("kanun_no")))
    kanun_ad = normalize_kanun_adi(_clean(ref.get("kanun_ad")), kanun_no=kanun_no or "")

    madde_raw = _clean(ref.get("madde"))
    fikra_raw = _clean(ref.get("fikra"))
    bent_raw = _clean(ref.get("bent"))

    madde_val, fikra_val, bent_val = "", "", ""
    if madde_raw:
        madde_val, fikra_val, bent_val = parse_madde_token(madde_raw)

    out_madde = madde_val if madde_val else madde_raw
    out_fikra = fikra_val if fikra_val else fikra_raw
    out_bent = bent_val if bent_val else bent_raw

    return {
        "kanun_no": kanun_no if kanun_no else None,
        "kanun_ad": kanun_ad if kanun_ad else None,
        "madde": normalize_madde(out_madde) if out_madde else None,
        "fikra": normalize_identifier(out_fikra) if out_fikra else None,
        "bent": normalize_identifier(out_bent) if out_bent else None,
        "source_text": source_text,
    }


def canonical_key(ref: dict) -> tuple:
    return tuple(ref.get(f) for f in REFERENCE_FIELDS)


def law_family_key(ref: dict) -> str:
    k_no = ref.get("kanun_no")
    k_ad = ref.get("kanun_ad")
    if k_no:
        return f"no:{k_no}"
    if k_ad:
        canonical_name = normalize_kanun_adi(k_ad) or k_ad
        mapped_no = LAW_NUMBER_BY_NAME.get(canonical_name)
        if mapped_no:
            return f"no:{mapped_no}"
        val = _normalize_turkish_key(canonical_name)
        return f"name:{val}"
    return ""


def normalize_references(refs: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    normalized_list: list[dict] = []
    for r in refs:
        n = normalize_reference(r)
        key = canonical_key(n)
        if key in seen:
            raise DuplicateReference(
                f"duplicate reference: source_text={n['source_text']!r}"
            )
        seen.add(key)
        normalized_list.append(n)

    def is_specific(ref: dict) -> bool:
        return bool(ref.get("madde") or ref.get("fikra") or ref.get("bent"))

    groups: dict[str, list[dict]] = {}
    ungrouped: list[dict] = []
    for r in normalized_list:
        fkey = law_family_key(r)
        if fkey:
            groups.setdefault(fkey, []).append(r)
        else:
            ungrouped.append(r)

    final_list: list[dict] = []
    for fkey, group in groups.items():
        specifics = [r for r in group if is_specific(r)]
        generics = [r for r in group if not is_specific(r)]
        if specifics:
            final_list.extend(group if not generics else specifics)
        else:
            final_list.extend(group)

    final_list.extend(ungrouped)

    final_keys = {canonical_key(r) for r in final_list}
    return [r for r in normalized_list if canonical_key(r) in final_keys]


def references_diff(prev: list[dict], curr: list[dict]) -> dict:
    prev_map = {canonical_key(r): r for r in prev}
    curr_map = {canonical_key(r): r for r in curr}
    added_keys = curr_map.keys() - prev_map.keys()
    removed_keys = prev_map.keys() - curr_map.keys()
    return {
        "added": [curr_map[k] for k in added_keys],
        "removed": [prev_map[k] for k in removed_keys],
    }


def is_diff_zero(diff: dict) -> bool:
    return not diff["added"] and not diff["removed"]
