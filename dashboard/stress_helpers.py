from typing import Dict


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


def build_existing_portfolio_weights(state_data: Dict) -> Dict[str, float]:
    """기존 상태 데이터에서 스트레스 테스트용 포트폴리오 비중을 만든다."""
    hwm = state_data.get("high_water_marks", {})
    if not hwm:
        return {}

    adjusted_symbols = []
    for symbol in hwm.keys():
        if symbol.isdigit():
            adjusted_symbols.append(f"{symbol}.KS")
        else:
            adjusted_symbols.append(symbol)

    weight = 1.0 / len(adjusted_symbols)
    return {symbol: weight for symbol in adjusted_symbols}
