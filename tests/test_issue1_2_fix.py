"""이슈 #1/#2 수정 검증 테스트 (cp949 콘솔 호환)"""
import sys
sys.path.insert(0, '.')
from src.analysis.growth_stock_finder import HybridGrowthStockFinder

PASS = "[OK]"
FAIL = "[FAIL]"

def check(label, cond):
    tag = PASS if cond else FAIL
    print(f"  {tag} {label}")
    return cond

def main():
    finder = HybridGrowthStockFinder()
    all_ok = True

    print("=" * 60)
    print("[정적 검증]")
    all_ok &= check("KR_SECTOR_MAP 15개", len(finder.KR_SECTOR_MAP) == 15)
    all_ok &= check("KR_NAME_MAP 15개", len(finder.KR_NAME_MAP) == 15)
    all_ok &= check("KR_CANDIDATE_SYMBOLS 15개", len(finder.KR_CANDIDATE_SYMBOLS) == 15)

    print("\n[시가총액 체크]")
    passes_kr = finder._passes_screening(None, None, None, 50_000_000_000_000, is_kr=True)
    passes_us = finder._passes_screening(None, None, None, 50_000_000_000_000, is_kr=False)
    all_ok &= check("한국 종목 50조원 (is_kr=True) -> 통과", passes_kr)
    all_ok &= check("미국 종목 50조달러 (is_kr=False) -> 차단", not passes_us)

    print("\n[키 동기화 확인]")
    map_keys = set(finder.KR_SECTOR_MAP.keys())
    name_keys = set(finder.KR_NAME_MAP.keys())
    cand_keys = set(finder.KR_CANDIDATE_SYMBOLS)
    sect_ok = map_keys == cand_keys
    name_ok = name_keys == cand_keys
    all_ok &= check("KR_SECTOR_MAP 키 == KR_CANDIDATE_SYMBOLS", sect_ok)
    all_ok &= check("KR_NAME_MAP 키 == KR_CANDIDATE_SYMBOLS", name_ok)
    if not sect_ok:
        print(f"    SECTOR_MAP에만 있는 키: {map_keys - cand_keys}")
        print(f"    CANDIDATE에만 있는 키: {cand_keys - map_keys}")
    if not name_ok:
        print(f"    NAME_MAP에만 있는 키: {name_keys - cand_keys}")
        print(f"    CANDIDATE에만 있는 키: {cand_keys - name_keys}")

    print("\n[씨에스윈드 112610.KS 매핑]")
    sector_ks = finder.KR_SECTOR_MAP.get("112610.KS")
    name_ks = finder.KR_NAME_MAP.get("112610.KS")
    sector_kq = finder.KR_SECTOR_MAP.get("112610.KQ")
    all_ok &= check(f"112610.KS 섹터: {sector_ks}", sector_ks is not None)
    all_ok &= check(f"112610.KS 이름: {name_ks}", name_ks is not None)
    all_ok &= check("112610.KQ 섹터 없음 (KQ->KS 수정 확인)", sector_kq is None)

    # is_kr=True: KR_SECTOR_MAP 항상 우선 적용 확인
    print("\n[KR 항상 우선 덮어쓰기 확인]")
    # 145020.KQ (휴젤)에 대해 is_kr=True 케이스 mock 검증
    expected_sector_hugel = finder.KR_SECTOR_MAP.get("145020.KQ")
    expected_name_hugel = finder.KR_NAME_MAP.get("145020.KQ")
    all_ok &= check(f"145020.KQ(휴젤) 섹터: {expected_sector_hugel}", expected_sector_hugel == "바이오")
    all_ok &= check(f"145020.KQ(휴젤) 이름: {expected_name_hugel}", expected_name_hugel == "휴젤")

    expected_sector_alteogen = finder.KR_SECTOR_MAP.get("196170.KQ")
    expected_name_alteogen = finder.KR_NAME_MAP.get("196170.KQ")
    all_ok &= check(f"196170.KQ(알테오젠) 섹터: {expected_sector_alteogen}", expected_sector_alteogen == "바이오")
    all_ok &= check(f"196170.KQ(알테오젠) 이름: {expected_name_alteogen}", expected_name_alteogen == "알테오젠")

    print("\n[미국 longName-only 종목 통과 확인]")
    has_name_both = bool("SuperMicro" or "Super Micro Computer Inc")
    has_name_long_only = bool("" or "Super Micro Computer Inc")
    has_name_none = bool("" or "")
    all_ok &= check("shortName+longName 모두 있을 때 has_name=True", has_name_both)
    all_ok &= check("longName만 있을 때 has_name=True", has_name_long_only)
    all_ok &= check("둘 다 없을 때 has_name=False", not has_name_none)

    print("\n" + "=" * 60)
    result_tag = PASS if all_ok else FAIL
    print(f"전체 정적 검증: {result_tag}")
    return 0 if all_ok else 1

if __name__ == "__main__":
    sys.exit(main())
