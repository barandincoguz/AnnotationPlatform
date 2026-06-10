"""Pure-function reference normalization, deduping, and set-semantic diff."""
import re
import unicodedata
from typing import Optional

REFERENCE_FIELDS = (
    "kanun_no", "kanun_ad", "madde", "fikra", "bent", "source_text",
)

ORDINAL_MAP = {
    "birinci": "1",
    "ikinci": "2",
    "ucuncu": "3",
    "dorduncu": "4",
    "besinci": "5",
    "altinci": "6",
    "yedinci": "7",
    "sekizinci": "8",
    "dokuzuncu": "9",
    "onuncu": "10",
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
}

LAW_NAME_ALIASES = {
    "VERGIUSULKANUNU": "Vergi Usul Kanunu",
    "GELIRVERGISIKANUNU": "Gelir Vergisi Kanunu",
    "KURUMLARVERGISIKANUNU": "Kurumlar Vergisi Kanunu",
    "KATMADEGERVERGISIKANUNU": "Katma Değer Vergisi Kanunu",
    "KATMADEGERVERGISIKDVKANUNU": "Katma Değer Vergisi Kanunu",
    "KDVKANUNU": "Katma Değer Vergisi Kanunu",
    "OZELTUKETIMVERGISIKANUNU": "Özel Tüketim Vergisi Kanunu",
    "OTVKANUNU": "Özel Tüketim Vergisi Kanunu",
    "DAMGAVERGISIKANUNU": "Damga Vergisi Kanunu",
    "HARCLARKANUNU": "Harçlar Kanunu",
}

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
    value = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^A-Za-z0-9]+", "", value).upper()
    return value

def normalize_kanun_adi(text: Optional[str], kanun_no: str = "") -> Optional[str]:
    if not text:
        return None
    raw = collapse_ws(text)
    upper_key = _normalize_turkish_key(raw)
    if upper_key in LAW_ABBREVIATIONS:
        return LAW_ABBREVIATIONS[upper_key]
    if upper_key in LAW_NAME_ALIASES:
        return LAW_NAME_ALIASES[upper_key]
    return raw

def normalize_identifier(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    raw = collapse_ws(str(value)).strip("()[]{}., ")
    lowered = _normalize_turkish_key(raw).lower()
    return ORDINAL_MAP.get(lowered, raw)

def normalize_madde(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    raw = collapse_ws(str(value))
    raw = re.sub(r"^madd\w*\s+", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*madd\w*$", "", raw, flags=re.IGNORECASE)
    raw = raw.strip(" .()")
    return raw if raw else None

def parse_madde_token(token: Optional[str]) -> tuple[str, str, str]:
    cleaned = normalize_madde(token)
    if not cleaned:
        return "", "", ""
    head = cleaned
    fikra = ""
    bent = ""

    if "/" in cleaned:
        left, right = cleaned.split("/", 1)
        head = left.strip()
        right = right.strip()
        if "-" in right:
            first, second = right.split("-", 1)
            if first.isdigit():
                fikra = first
                bent = normalize_identifier(second)
            else:
                bent = normalize_identifier(right)
        elif right.isdigit():
            fikra = right
        else:
            bent = normalize_identifier(right)
    elif "-" in cleaned:
        left, right = cleaned.split("-", 1)
        head = left.strip()
        bent = normalize_identifier(right)

    return head, fikra, bent

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

    def law_family_key(ref: dict) -> str:
        k_no = ref.get("kanun_no")
        k_ad = ref.get("kanun_ad")
        if k_no:
            return f"no:{k_no}"
        if k_ad:
            val = _normalize_turkish_key(k_ad)
            return f"name:{val}"
        return ""

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
