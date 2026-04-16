"""이슈 #1/#2 실데이터 검증 (cp949 콘솔 호환)"""
import sys
sys.path.insert(0, '.')
from src.analysis.growth_stock_finder import HybridGrowthStockFinder

PASS = "[OK]"
FAIL = "[FAIL]"

def main():
    finder = HybridGrowthStockFinder()
    print("KR 종목 스크리닝 시작 (yfinance 실호출)...")
    results = finder._screen_with_yfinance(finder.KR_CANDIDATE_SYMBOLS)

    print(f"\nKR 결과 수: {len(results)} (기준: 3개 이상)")
    for s in results:
        print(f"  {s.symbol} / {s.name} / {s.sector} / "
              f"rev={s.revenue_growth} / margin={s.profit_margin}")

    # AC-1: 섹터 Unknown 없고 한국어인지 (ASCII 아닌 문자 포함 여부로 판단)
    def is_korean_text(t):
        return any('\uac00' <= c <= '\ud7a3' for c in t)

    ac1_sector = results and all(
        s.sector != 'Unknown' and is_korean_text(s.sector)
        for s in results
    )
    # AC-2: 재무값 최소 하나 non-None
    ac2_financial = any(
        (s.revenue_growth is not None) or (s.profit_margin is not None)
        for s in results
    )
    # AC-3: 최소 3개 이상
    ac3_count = len(results) >= 3
    # AC (이슈 #2): 이름이 한국어
    ac_name = results and all(is_korean_text(s.name) for s in results)

    # US 회귀 확인
    print("\nUS 종목 스크리닝 시작...")
    us_results = finder._screen_with_yfinance(finder.US_CANDIDATE_SYMBOLS)
    print(f"US 결과 수: {len(us_results)}")
    for s in us_results:
        print(f"  {s.symbol} / {s.name} / {s.sector}")
    ac_us_ok = len(us_results) >= 1

    print("\n" + "=" * 60)
    print("[AC 판정]")
    print(f"  {PASS if ac1_sector else FAIL} AC-1: 섹터가 한국어 (Unknown 없음)")
    print(f"  {PASS if ac_name else FAIL} AC-2(#2): 이름이 한국어")
    print(f"  {PASS if ac2_financial else FAIL} AC-2(#1): 재무값 최소 1개 non-None")
    print(f"  {PASS if ac3_count else FAIL} AC-3: 최소 3개 이상 종목")
    print(f"  {PASS if ac_us_ok else FAIL} AC-6: 미국 종목 정상 반환 (회귀 없음)")

    all_pass = ac1_sector and ac_name and ac2_financial and ac3_count and ac_us_ok
    print(f"\n{'[OK] 전체 통과' if all_pass else '[FAIL] 일부 실패'}")
    return 0 if all_pass else 1

if __name__ == "__main__":
    sys.exit(main())
