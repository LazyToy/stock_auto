import json
import math
import os
from typing import Dict, Iterable, Mapping, Any


STRESS_RESULT_CURRENCY = "KRW"
STRESS_PORTFOLIO_STORE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "stress_portfolios.json")
)


def _normalize_kr_symbol(symbol: str) -> str:
    """숫자형 한국 종목 코드에 yfinance suffix를 붙인다."""
    cleaned = symbol.strip()
    if cleaned.isdigit():
        return f"{cleaned}.KS"
    return cleaned


def infer_symbol_currency(symbol: str) -> str:
    """종목의 거래소 기준 quote currency를 간단히 추정한다."""
    cleaned = str(symbol or "").strip().upper()
    if cleaned.isdigit() or cleaned.endswith((".KS", ".KQ")):
        return "KRW"
    return "USD"


def infer_portfolio_currency(portfolio_weights: Dict[str, float]) -> str:
    """포트폴리오 금액 차트에 표시할 기준 통화를 추정한다."""
    currencies = {
        infer_symbol_currency(symbol)
        for symbol in portfolio_weights
        if str(symbol).strip()
    }
    if not currencies:
        return "INPUT"
    if len(currencies) == 1:
        return currencies.pop()
    return "INPUT"


def format_stress_amount(value: float, currency: str) -> str:
    """Stress Test 금액을 표/차트 설명용 통화 형식으로 표시한다."""
    if currency == "KRW":
        return f"₩{value:,.0f}"
    if currency == "USD":
        return f"${value:,.2f}"
    return f"{value:,.2f} (입력 통화)"


def format_display_number(value: Any, digits: int = 2, na_text: str = "N/A") -> str:
    """Format dashboard table numbers with thousands separators."""
    if value is None:
        return na_text
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(numeric):
        return na_text
    if digits <= 0:
        return f"{numeric:,.0f}"
    return f"{numeric:,.{digits}f}"


def split_macro_path_rows(rows: Any) -> tuple[list[Mapping], list[Mapping]]:
    """Split USD/KRW rows from other macro rows so chart scales stay readable."""
    if hasattr(rows, "to_dict"):
        source_rows = rows.to_dict("records")
    else:
        source_rows = rows or []

    usdkrw_rows = []
    other_rows = []
    for row in source_rows:
        symbol = str(row.get("symbol", "")).upper()
        name = str(row.get("name", "")).upper()
        if symbol == "KRW=X" or name == "USD/KRW":
            usdkrw_rows.append(row)
        else:
            other_rows.append(row)
    return usdkrw_rows, other_rows


def hide_benchmark_traces_by_default(fig: Any) -> Any:
    """Keep benchmark traces available in the legend but hidden on initial render."""
    for trace in getattr(fig, "data", []):
        name = str(getattr(trace, "name", "") or "")
        if name.startswith("Benchmark:"):
            trace.visible = "legendonly"
    return fig


def _clean_portfolio_weights(portfolio_weights: Mapping[str, Any]) -> Dict[str, float]:
    cleaned: Dict[str, float] = {}
    for symbol, weight in (portfolio_weights or {}).items():
        clean_symbol = str(symbol or "").strip()
        if not clean_symbol:
            continue
        try:
            cleaned[clean_symbol] = float(weight)
        except (TypeError, ValueError):
            continue
    return cleaned


def load_stress_portfolios(store_path: str = STRESS_PORTFOLIO_STORE_PATH) -> Dict[str, Dict[str, float]]:
    """Load saved Stress Test portfolios from JSON."""
    if not os.path.exists(store_path):
        return {}

    try:
        with open(store_path, "r", encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}

    raw_portfolios = payload.get("portfolios", payload) if isinstance(payload, dict) else {}
    if not isinstance(raw_portfolios, dict):
        return {}

    portfolios: Dict[str, Dict[str, float]] = {}
    for name, weights in raw_portfolios.items():
        clean_name = str(name or "").strip()
        if not clean_name or not isinstance(weights, dict):
            continue
        clean_weights = _clean_portfolio_weights(weights)
        if clean_weights:
            portfolios[clean_name] = clean_weights
    return portfolios


def save_stress_portfolio(
    name: str,
    portfolio_weights: Mapping[str, Any],
    store_path: str = STRESS_PORTFOLIO_STORE_PATH,
) -> str:
    """Save or replace a named Stress Test portfolio."""
    clean_name = str(name or "").strip()
    if not clean_name:
        raise ValueError("저장할 포트폴리오 이름을 입력해주세요.")

    clean_weights = _clean_portfolio_weights(portfolio_weights)
    if not clean_weights:
        raise ValueError("저장할 포트폴리오 종목이 없습니다.")

    portfolios = load_stress_portfolios(store_path=store_path)
    portfolios[clean_name] = clean_weights

    directory = os.path.dirname(store_path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    with open(store_path, "w", encoding="utf-8") as file:
        json.dump(
            {"version": 1, "portfolios": portfolios},
            file,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    return clean_name


def format_krw_input_amount(value: float) -> str:
    """원화 금액 입력 기본값을 천 단위 쉼표가 있는 문자열로 만든다."""
    return f"{int(value):,}"


def parse_krw_input_amount(value: str) -> int:
    """천 단위 쉼표가 포함된 원화 금액 입력을 정수로 변환한다."""
    cleaned = str(value or "").strip().replace(",", "")
    if not cleaned.isdigit():
        raise ValueError("총 포트폴리오 가치는 숫자와 쉼표만 입력해주세요.")
    return int(cleaned)


def parse_portfolio_text(portfolio_text: str) -> Dict[str, float]:
    """수동 입력 텍스트를 종목-비중 딕셔너리로 변환한다."""
    portfolio_weights: Dict[str, float] = {}

    for line in portfolio_text.strip().split("\n"):
        if ":" not in line:
            continue

        symbol, weight_text = line.strip().split(":", 1)
        symbol = symbol.strip()
        weight = float(weight_text.strip())

        if not symbol:
            continue

        portfolio_weights[symbol] = weight

    return portfolio_weights


def _iter_portfolio_rows(rows: Any) -> Iterable[Mapping]:
    """DataFrame/list 입력을 공통 row iterator로 변환한다."""
    if hasattr(rows, "to_dict"):
        return rows.to_dict("records")
    return rows or []


def portfolio_rows_to_weights(rows: Any) -> Dict[str, float]:
    """UI 표 입력(Symbol, Weight %)을 스트레스 테스트용 비중 딕셔너리로 변환한다."""
    portfolio_weights: Dict[str, float] = {}

    for row in _iter_portfolio_rows(rows):
        symbol = str(row.get("Symbol", "")).strip()
        weight_value = row.get("Weight (%)")
        if not symbol:
            continue

        try:
            weight_pct = float(weight_value)
        except (TypeError, ValueError):
            raise ValueError(f"{symbol} 비중은 숫자로 입력해주세요.")

        if math.isnan(weight_pct):
            raise ValueError(f"{symbol} 비중은 숫자로 입력해주세요.")

        portfolio_weights[symbol] = weight_pct / 100.0

    return portfolio_weights


def portfolio_weights_to_rows(portfolio_weights: Dict[str, float]) -> list[Dict[str, float | str]]:
    """비중 딕셔너리를 data editor 기본 행으로 변환한다."""
    return [
        {
            "Symbol": symbol,
            "Weight (%)": weight * 100.0,
        }
        for symbol, weight in portfolio_weights.items()
    ]


def validate_portfolio_weights(
    portfolio_weights: Dict[str, float],
    tolerance: float = 0.01,
) -> Dict:
    """스트레스 테스트 입력 비중의 유효성을 점검한다."""
    warnings = []
    if not portfolio_weights:
        return {
            "is_valid": False,
            "can_normalize": False,
            "total_weight": 0.0,
            "warnings": ["포트폴리오 비중이 비어 있습니다."],
        }

    total_weight = sum(portfolio_weights.values())
    has_negative_weight = any(weight < 0 for weight in portfolio_weights.values())
    if total_weight <= 0:
        warnings.append("비중 합계는 0보다 커야 합니다.")
    if has_negative_weight:
        warnings.append("음수 비중은 현재 Stress Test에서 지원하지 않습니다.")
    if abs(total_weight - 1.0) > tolerance:
        warnings.append(f"비중 합계가 {total_weight:.2f}입니다. 1.00으로 정규화가 필요합니다.")

    return {
        "is_valid": not warnings,
        "can_normalize": total_weight > 0 and not has_negative_weight,
        "total_weight": total_weight,
        "warnings": warnings,
    }


def normalize_portfolio_weights(portfolio_weights: Dict[str, float]) -> Dict[str, float]:
    """상대 비중을 유지한 채 합계를 1로 맞춘다."""
    total_weight = sum(portfolio_weights.values())
    if total_weight <= 0:
        raise ValueError("Portfolio weights must sum to a positive value")
    return {
        symbol: weight / total_weight
        for symbol, weight in portfolio_weights.items()
    }


def _stock_market_value(stock: Dict) -> float:
    """대시보드 stock row에서 평가액을 계산한다."""
    for key in ("eval_amt", "market_value", "evaluation_amount"):
        value = stock.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                continue

    try:
        return float(stock.get("current_price", 0.0)) * float(stock.get("quantity", 0.0))
    except (TypeError, ValueError):
        return 0.0


def build_existing_portfolio_weights(state_data: Dict) -> Dict[str, float]:
    """기존 상태 데이터에서 스트레스 테스트용 포트폴리오 비중을 만든다."""
    stocks = state_data.get("stocks", [])
    stock_values: Dict[str, float] = {}
    for stock in stocks:
        symbol = stock.get("symbol") or stock.get("ticker")
        if not symbol:
            continue
        value = _stock_market_value(stock)
        if value <= 0:
            continue
        stock_values[_normalize_kr_symbol(symbol)] = value

    if stock_values:
        total_value = sum(stock_values.values())
        return {
            symbol: value / total_value
            for symbol, value in stock_values.items()
        }

    hwm = state_data.get("high_water_marks", {})
    if not hwm:
        return {}

    adjusted_symbols = []
    for symbol in hwm.keys():
        adjusted_symbols.append(_normalize_kr_symbol(symbol))

    weight = 1.0 / len(adjusted_symbols)
    return {symbol: weight for symbol in adjusted_symbols}
