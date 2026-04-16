import re


def normalize_signal(signal: str) -> str:
    normalized = (signal or "").strip().upper()
    mapping = {
        "매수": "BUY",
        "매도": "SELL",
        "보유": "HOLD",
        "중립": "NEUTRAL",
        "BUY": "BUY",
        "SELL": "SELL",
        "HOLD": "HOLD",
        "NEUTRAL": "NEUTRAL",
    }
    return mapping.get(normalized, normalized)


def signal_to_korean(signal: str) -> str:
    normalized = normalize_signal(signal)
    mapping = {
        "BUY": "매수",
        "SELL": "매도",
        "HOLD": "보유",
        "NEUTRAL": "중립",
    }
    return mapping.get(normalized, normalized or "알 수 없음")


def localize_signal_terms(text: str) -> str:
    if not text:
        return text

    localized = text
    replacements = {
        r"\bBUY\b": "매수",
        r"\bSELL\b": "매도",
        r"\bHOLD\b": "보유",
        r"\bNEUTRAL\b": "중립",
    }
    for pattern, replacement in replacements.items():
        localized = re.sub(pattern, replacement, localized, flags=re.IGNORECASE)
    return localized
