from functools import lru_cache
from typing import Optional


KNOWN_SYMBOL_NAMES = {
    "005930": "삼성전자",
    "000660": "SK하이닉스",
    "035420": "NAVER",
    "035720": "카카오",
    "051910": "LG화학",
    "AAPL": "Apple",
    "TSLA": "Tesla",
    "NVDA": "NVIDIA",
    "MSFT": "Microsoft",
    "AMZN": "Amazon",
}


def _looks_like_mojibake(text: str) -> bool:
    if not text:
        return False
    if "�" in text:
        return True
    if any("" <= ch <= "" for ch in text):
        return True
    suspicious_latin1 = sum(1 for ch in text if "À" <= ch <= "ÿ")
    has_hangul = any("가" <= ch <= "힣" for ch in text)
    return suspicious_latin1 >= 3 and not has_hangul

def normalize_symbol_code(symbol: str) -> str:
    cleaned = (symbol or "").strip().upper()
    for suffix in (".KS", ".KQ"):
        if cleaned.endswith(suffix):
            return cleaned[: -len(suffix)]
    return cleaned


def build_symbol_candidates(symbol: str) -> list[str]:
    normalized = normalize_symbol_code(symbol)
    if not normalized:
        return []
    if normalized.isdigit():
        return [f"{normalized}.KS", f"{normalized}.KQ"]
    return [normalized]


def format_symbol_label(symbol: str, company_name: Optional[str]) -> str:
    normalized = normalize_symbol_code(symbol)
    if company_name:
        return f"{normalized} ({company_name})"
    return normalized


@lru_cache(maxsize=256)
def _looks_like_valid_company_name(name: Optional[str], candidate: str) -> bool:
    if not name:
        return False
    stripped = str(name).strip()
    if not stripped:
        return False
    upper_candidate = candidate.upper()
    upper_name = stripped.upper()
    if upper_name == upper_candidate:
        return False
    if upper_name.startswith(upper_candidate + ","):
        return False
    if stripped.count(",") >= 2:
        return False
    if _looks_like_mojibake(stripped):
        return False
    return True


def resolve_company_name(symbol: str) -> Optional[str]:
    normalized = normalize_symbol_code(symbol)
    if not normalized:
        return None

    if normalized in KNOWN_SYMBOL_NAMES:
        return KNOWN_SYMBOL_NAMES[normalized]

    try:
        import yfinance as yf
    except Exception:
        return None

    fallback_name: Optional[str] = None
    for candidate in build_symbol_candidates(symbol):
        try:
            info = yf.Ticker(candidate).info or {}
        except Exception:
            continue

        quote_type = str(info.get("quoteType") or "").upper()
        for key in ("longName", "shortName", "displayName", "name"):
            value = info.get(key)
            if not _looks_like_valid_company_name(value, candidate):
                continue
            if quote_type == "EQUITY":
                return str(value)
            fallback_name = fallback_name or str(value)

    return fallback_name


def build_symbol_label(symbol: str) -> str:
    normalized = normalize_symbol_code(symbol)
    if not normalized:
        return ""
    return format_symbol_label(normalized, resolve_company_name(normalized))


def build_chart_title(symbol: str, company_name: Optional[str]) -> str:
    return f"{format_symbol_label(symbol, company_name)} 분석"
