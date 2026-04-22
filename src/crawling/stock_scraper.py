from __future__ import annotations

import datetime
import time
import urllib.request
import concurrent.futures
import importlib
from typing import Any, cast
from bs4 import BeautifulSoup
import pandas as pd

gspread = importlib.import_module("gspread")
Credentials = importlib.import_module("google.oauth2.service_account").Credentials
fdr = importlib.import_module("FinanceDataReader")
from src.crawling.sector_map_kr import SectorMapKR
from src.crawling.streak_indicators import compute_indicators

from src.crawling._env_overrides import read_env_float, read_env_int
from src.crawling.service_account_path import resolve_service_account_file

# ==========================================
# CONFIG 설정
# ==========================================
CONFIG = {
    "SERVICE_ACCOUNT_FILE": "config/google_service_account.json", # 서비스 계정 JSON 키파일 경로
    "SPREADSHEET_PREFIX": "주식_쉐도잉_",            # 구글 시트 파일명 접두사
    "SURGE_THRESHOLD": read_env_float("CRAWL_KR_SURGE_THRESHOLD", 15.0),  # 급등 기준 (%)
    "DROP_THRESHOLD": read_env_float("CRAWL_KR_DROP_THRESHOLD", -15.0),  # 낙폭과대 절대 기준 (%)
    "DROP_SECONDARY_THRESHOLD": read_env_float("CRAWL_KR_DROP_SECONDARY_THRESHOLD", -6.0),  # 낙폭과대 복합 기준 — 등락률 (%)
    "VOLUME_THRESHOLD": read_env_int("CRAWL_KR_VOLUME_THRESHOLD", 500),  # 거래대금 기준 (억 원)
    "FLUCTUATION_THRESHOLD": read_env_float("CRAWL_KR_FLUCTUATION_THRESHOLD", 6.0),  # 변동폭 기준 (%)
    # 제외 종목 리스트 (시가총액 상위 10종목 등)
    "EXCLUDE_STOCKS": [
        "005930", # 삼성전자
        "000660", # SK하이닉스
        "373220", # LG에너지솔루션
        "207940", # 삼성바이오로직스
        "005380", # 현대차
        "000270", # 기아
        "068270", # 셀트리온
        "005490", # POSCO홀딩스
        "105560", # KB금융
        "028260", # 삼성물산
    ]
}

# ==========================================
# 헬퍼 함수
# ==========================================

def get_naver_news(ticker_str, keyword=""):
    """
    네이버 증권 종목 뉴스에서 상위 3개의 제목과 URL을 가져옵니다.
    """
    news_list = []
    try:
        url = f"https://finance.naver.com/item/main.naver?code={ticker_str}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        res = urllib.request.urlopen(req, timeout=10)
        # 네이버 금융 메인 페이지는 현재 utf-8 인코딩을 사용합니다.
        html_text = res.read().decode('utf-8', 'replace')
        
        soup = BeautifulSoup(html_text, 'html.parser')
        
        # 네이버 금융 메인 페이지 뉴스 영역 셀렉터
        articles = soup.select('.sub_section.news_section ul li a')
        if not articles:
            articles = soup.select('.news_section a')
        
        for article in articles[:3]:
            title = article.text.strip()
            link = str(article.get('href') or '')
            if link.startswith('/'):
                link = "https://finance.naver.com" + link
            if title and link:
                news_list.append((title, link))
            
    except Exception as e:
        print(f"[{ticker_str}] 뉴스 검색 중 에러 발생: {e}")
        
    # 뉴스가 3개가 안 될 경우 빈 값으로 채움
    while len(news_list) < 3:
        news_list.append(("", ""))
        
    return news_list

def get_chart_formulas(ticker):
    """
    네이버 증권 차트 이미지 URL을 Google Sheets IMAGE 수식으로 반환합니다.
    """
    # 종목코드가 숫자형으로 변환되어 앞의 0이 사라지는 것을 방지
    ticker_str = str(ticker).zfill(6)
    
    # 3개월, 1년, 3년 차트 이미지 주소 (area 차트)
    url_3m = f"https://ssl.pstatic.net/imgfinance/chart/item/area/month3/{ticker_str}.png"
    url_1y = f"https://ssl.pstatic.net/imgfinance/chart/item/area/year/{ticker_str}.png"
    url_3y = f"https://ssl.pstatic.net/imgfinance/chart/item/area/year3/{ticker_str}.png"
    
    return (
        f'=IMAGE("{url_3m}")',
        f'=IMAGE("{url_1y}")',
        f'=IMAGE("{url_3y}")'
    )

def get_gspread_client():
    """
    Google Sheets API 클라이언트를 인증하고 반환합니다.
    """
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    credentials = Credentials.from_service_account_file(
        resolve_service_account_file(), scopes=scopes
    )
    client = gspread.authorize(credentials)
    return client

def ensure_worksheet(sh, sheet_name, headers):
    """
    워크시트가 존재하는지 확인하고, 없으면 생성 후 헤더를 추가합니다.
    """
    try:
        worksheet = sh.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = sh.add_worksheet(title=sheet_name, rows="1000", cols="20")
        worksheet.append_row(headers, value_input_option='USER_ENTERED')
    return worksheet

def get_existing_keys(worksheet):
    """
    시트에 이미 존재하는 (날짜, 종목코드) 쌍을 Set으로 반환하여 중복을 방지합니다.
    """
    try:
        records = worksheet.get_all_values()
        existing_keys = set()
        for row in records[1:]: # 헤더 제외
            # 빈 행이거나 날짜/종목코드가 없는 경우 무시
            if not any(row):
                continue
            if len(row) >= 3:
                date_val = str(row[0]).strip()
                ticker_val = str(row[2]).replace("'", "").strip() # 작은따옴표 제거
                if date_val and ticker_val: # 빈 값 무시
                    existing_keys.add((date_val, ticker_val))
        return existing_keys
    except Exception:
        return set()

def resize_cells_for_images(worksheet, start_col_index, end_col_index, row_height=300, col_width=600):
    """
    차트 이미지가 잘 보이도록 셀의 높이와 너비를 조정합니다. (기존 대비 2배 확대)
    """
    try:
        body = {
            "requests": [
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": worksheet.id,
                            "dimension": "COLUMNS",
                            "startIndex": start_col_index,
                            "endIndex": end_col_index
                        },
                        "properties": {
                            "pixelSize": col_width
                        },
                        "fields": "pixelSize"
                    }
                },
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": worksheet.id,
                            "dimension": "ROWS",
                            "startIndex": 1, # 헤더 제외
                            "endIndex": 1000 # 넉넉하게 1000행까지
                        },
                        "properties": {
                            "pixelSize": row_height
                        },
                        "fields": "pixelSize"
                    }
                }
            ]
        }
        worksheet.spreadsheet.batch_update(body)
        print("셀 크기(너비/높이) 자동 조정 완료.")
    except Exception as e:
        print(f"셀 크기 조정 중 에러 발생: {e}")

# ==========================================
# 신규 헬퍼 함수 (이슈 #1, #2, #15)
# ==========================================

def infer_volume_unit(df: pd.DataFrame, *, _log_fn=None) -> int:
    """
    FDR Amount 컬럼의 단위를 추론하여 배율을 반환한다.
    삼성전자(005930)를 sanity anchor로 사용.

    Parameters
    ----------
    df      : Code, Amount 컬럼을 포함하는 DataFrame
    _log_fn : 로그 출력 함수 (기본 None=무음). main()에서 print 주입.

    Returns
    -------
    1         — 이미 원(KRW) 단위
    1_000_000 — 백만원 단위 (×1,000,000 필요)
    """
    SAMSUNG = "005930"
    # 삼성전자 최소 합리 거래대금: 100억 원 (장중 최소 거래량 기준)
    SAMSUNG_MIN_WON = 1e10

    anchor_rows = cast(pd.DataFrame, df[df["Code"] == SAMSUNG].copy()) if "Code" in df.columns else pd.DataFrame()
    if not anchor_rows.empty:
        anchor_amount = float(anchor_rows["Amount"].iloc[0])
        if anchor_amount > 0:
            if anchor_amount >= SAMSUNG_MIN_WON:
                return 1
            else:
                return 1_000_000
        # anchor_amount == 0 (거래정지 등) → fallback 경로 — 반드시 로그
        if _log_fn:
            _log_fn("[단위감지 FALLBACK] 삼성전자(005930) 거래대금=0 (거래정지 추정) "
                    "— 전체 max 기반 추정 사용 (오판 가능성 주의)")
    else:
        if _log_fn:
            _log_fn("[단위감지 FALLBACK] 삼성전자(005930) 데이터 없음 "
                    "— 전체 max 기반 추정 사용 (오판 가능성 주의)")

    # 삼성전자가 없거나 거래정지 → 전체 max 기반 fallback
    max_amount = float(df["Amount"].max()) if "Amount" in df.columns and not df["Amount"].empty else 0.0
    if max_amount > 0 and max_amount < SAMSUNG_MIN_WON:
        return 1_000_000
    return 1


def resolve_trading_date(df: pd.DataFrame, now: datetime.datetime) -> str:
    """
    FDR 데이터에서 실제 거래일을 YYYYMMDD 로 반환한다.
    Date 컬럼이 없거나 전부 NaN이면 now 기준 날짜로 fallback한다.

    Parameters
    ----------
    df  : fdr.StockListing('KRX') 결과 DataFrame
    now : 실행 시점 datetime (테스트 주입용)
    """
    if "Date" in df.columns:
        date_col = cast(pd.Series, df["Date"])
        dates = pd.Series(dtype="datetime64[ns]")
        if not bool(date_col.isna().all()):
            dates = pd.Series(pd.to_datetime(date_col, errors="coerce").dropna())
        if len(dates) > 0:
            most_common = dates.mode().iloc[0]
            return most_common.strftime("%Y%m%d")
    return now.strftime("%Y%m%d")


def build_indicator_columns(
    indicators: dict,
    prev_close: float,
    today_open: float,
) -> list:
    """
    compute_indicators 결과 + 전일종가/금일시가로 5개 컬럼 값 생성.

    Returns
    -------
    [52주신고(str), 52주신저(str), 연속봉(int), ATR14(%)(float), 갭(%)(float)]
    """
    gap = 0.0
    if prev_close and prev_close > 0:
        gap = round((today_open - prev_close) / prev_close * 100, 2)
    return [
        "신고" if indicators["is_52w_high"] else "",
        "신저" if indicators["is_52w_low"] else "",
        int(indicators["streak_days"]),
        round(float(indicators["atr14_pct"]), 2),
        gap,
    ]


def ensure_header_columns(worksheet, expected_headers: list) -> None:
    """
    기존 워크시트 헤더 행에 누락된 컬럼을 오른쪽 끝에 추가한다 (마이그레이션).

    - 헤더 행이 없으면 아무것도 하지 않는다 (빈 시트는 ensure_worksheet 가 처리).
    - 이미 모든 컬럼이 있으면 아무것도 하지 않는다 (멱등).
    - 중간 삽입 금지: 끝에 append 만 한다 (chart 컬럼 인덱스 불변 유지).
    """
    try:
        all_values = worksheet.get_all_values()
        if not all_values:
            return
        existing_headers = all_values[0]
        missing = [h for h in expected_headers if h not in existing_headers]
        if not missing:
            return
        new_row = existing_headers + missing
        worksheet.update("1:1", [new_row], value_input_option='USER_ENTERED')
        print(f"[헤더 마이그레이션] 신규 컬럼 추가: {missing}")
    except Exception as e:
        print(f"[헤더 마이그레이션] 실패 (계속 진행): {e}")


def dry_run_indicator_check(
    df_today: pd.DataFrame,
    sector_map,
    *,
    mock_indicators: bool = False,
) -> None:
    """
    DRY_RUN=1 모드 전용 - Google Sheets 쓰기 없이 급등주 1종목의
    row_data(지표 5개 포함)를 stdout으로 출력하여 AC-8 검증 경로 제공.

    Parameters
    ----------
    mock_indicators : True 이면 FDR 없이 합성 지표값 사용 (MOCK=1 env).

    헤더 순서: 날짜, 종목명, 종목코드, 등락률(%), 거래대금(억),
               뉴스1_제목 ~ 뉴스3_URL, 3개월차트 ~ 3년차트, 키워드,
               52주신고, 52주신저, 연속봉, ATR14(%), 갭(%)
    """
    import os
    today_str = datetime.datetime.today().strftime("%Y%m%d")
    surge_df = df_today[df_today['등락률'] >= CONFIG["SURGE_THRESHOLD"]]
    if surge_df.empty:
        # 급등주 없으면 등락률 상위 1종목으로 대체 (dry-run 전용)
        surge_df = df_today.nlargest(1, '등락률')
    indicator_start = (
        datetime.datetime.today() - datetime.timedelta(days=400)
    ).strftime("%Y%m%d")

    print("\n" + "-" * 60)
    print("[DRY RUN] 지표 컬럼 검증 - 첫 번째 종목 처리 중...")
    if mock_indicators:
        print("[DRY RUN] MOCK 모드: 네트워크 없이 합성 지표값 사용")
    print("-" * 60)

    for ticker, row in surge_df.head(1).iterrows():
        ticker_str = str(ticker).zfill(6)
        stock_name = str(row['종목명'])
        fluctuation = round(float(row['등락률']), 2)
        volume_100m = round(float(row['거래대금']) / 100_000_000, 2)
        keyword = sector_map.lookup(ticker_str)
        if mock_indicators:
            # 합성 지표값 - FDR 네트워크 불필요 (Windows cp949 포함)
            indicator_cols = ["신고", "", 3, 1.23, 2.5]
        else:
            indicator_cols = enrich_with_indicators(ticker_str, indicator_start)

        row_data = [
            today_str, stock_name, f"'{ticker_str}", fluctuation, volume_100m,
            "(dry-run)", "", "(dry-run)", "", "(dry-run)", "",  # 뉴스 3개
            "(dry-run)", "(dry-run)", "(dry-run)",              # 차트 3개
            keyword,
            *indicator_cols,
        ]
        headers = [
            "날짜", "종목명", "종목코드", "등락률(%)", "거래대금(억)",
            "뉴스1_제목", "뉴스1_URL", "뉴스2_제목", "뉴스2_URL", "뉴스3_제목", "뉴스3_URL",
            "3개월차트", "1년차트", "3년차트", "키워드",
            "52주신고", "52주신저", "연속봉", "ATR14(%)", "갭(%)",
        ]
        print(f"\n{'─' * 60}")
        for h, v in zip(headers, row_data):
            print(f"  {h:20s}: {v!r}")
        print(f"{'─' * 60}")
        length_ok = len(row_data) == len(headers)
        print(f"[DRY RUN OK] len={len(row_data)} header={len(headers)} match={'YES' if length_ok else 'NO'}")
        # 지표 컬럼 타입 검증
        w52h, w52l, streak, atr14, gap = indicator_cols
        print('[TYPE CHECK]')
        print(f"  52주신고 type={type(w52h).__name__!r} (기대: str) {'OK' if isinstance(w52h, str) else 'NG'}")
        print(f"  52주신저 type={type(w52l).__name__!r} (기대: str) {'OK' if isinstance(w52l, str) else 'NG'}")
        print(f"  연속봉   type={type(streak).__name__!r} (기대: int) {'OK' if isinstance(streak, int) else 'NG'}")
        print(f"  ATR14(%) type={type(atr14).__name__!r} (기대: float) {'OK' if isinstance(atr14, float) else 'NG'}")
        print(f"  갭(%)    type={type(gap).__name__!r} (기대: float) {'OK' if isinstance(gap, float) else 'NG'}")



def enrich_with_indicators(ticker_str: str, start_date: str) -> list:
    """
    FDR DataReader로 280거래일 OHLCV 조회 후 지표 컬럼 5개 생성.
    타임아웃 15초, 실패 시 빈 값 반환.

    Returns
    -------
    [52주신고, 52주신저, 연속봉, ATR14(%), 갭(%)] 또는 ["", "", 0, 0.0, 0.0]
    """
    _EMPTY = ["", "", 0, 0.0, 0.0]
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            df_detail = ex.submit(fdr.DataReader, ticker_str, start_date).result(timeout=15)
        if df_detail is None or df_detail.empty or len(df_detail) < 2:
            return _EMPTY
        indicators = compute_indicators(df_detail)
        prev_close = float(df_detail["Close"].iloc[-2])
        today_open = float(df_detail["Open"].iloc[-1]) if "Open" in df_detail.columns else 0.0
        return build_indicator_columns(indicators, prev_close, today_open)
    except concurrent.futures.TimeoutError:
        print(f"[{ticker_str}] 지표 DataReader 타임아웃 — 지표 컬럼 빈값 처리")
        return _EMPTY
    except Exception as e:
        print(f"[{ticker_str}] 지표 계산 에러: {e}")
        return _EMPTY


# ==========================================
# 메인 작업 함수
# ==========================================

def task1_surge_stocks(today_str, df_today, sh, sector_map):
    """
    작업 1: 당일 급등주 수집 (15% 이상 상승 종목)
    """
    print("--- 작업 1: 당일 급등주 수집 시작 ---")

    headers = [
        "날짜", "종목명", "종목코드", "등락률(%)", "거래대금(억)",
        "뉴스1_제목", "뉴스1_URL", "뉴스2_제목", "뉴스2_URL", "뉴스3_제목", "뉴스3_URL",
        "3개월차트", "1년차트", "3년차트", "키워드",
        "52주신고", "52주신저", "연속봉", "ATR14(%)", "갭(%)",
    ]
    worksheet = ensure_worksheet(sh, "급등주_쉐도잉", headers)
    # 기존 시트에 지표 5개 컬럼이 없으면 헤더 마이그레이션
    ensure_header_columns(worksheet, headers)
    existing_keys = get_existing_keys(worksheet)
    
    # 15% 이상 상승 종목 필터링
    surge_df = df_today[df_today['등락률'] >= CONFIG["SURGE_THRESHOLD"]]

    # 지표용 OHLCV 조회 시작일 (52주=252거래일 + 여유 28일)
    indicator_start = (datetime.datetime.today() - datetime.timedelta(days=400)).strftime("%Y%m%d")

    rows_to_append = []
    for ticker, row in surge_df.iterrows():
        try:
            ticker_str = str(ticker).zfill(6)

            # 중복 체크 (같은 날짜에 이미 저장된 종목코드는 건너뜀)
            if (today_str, ticker_str) in existing_keys:
                print(f"이미 존재하는 데이터 건너뜀 (급등주): {row['종목명']} ({ticker_str})")
                continue

            stock_name = row['종목명']
            fluctuation = round(row['등락률'], 2)
            volume_100m = round(row['거래대금'] / 100000000, 2)  # 억 원 단위

            print(f"처리 중 (급등주): {stock_name} ({ticker_str}) - {fluctuation}%")

            news = get_naver_news(ticker_str, stock_name)
            charts = get_chart_formulas(ticker_str)
            keyword = sector_map.lookup(ticker_str)
            indicator_cols = enrich_with_indicators(ticker_str, indicator_start)
            print(f"  [지표] 52주신고={indicator_cols[0]!r}, 52주신저={indicator_cols[1]!r}, 연속봉={indicator_cols[2]}, ATR14(%)={indicator_cols[3]}, 갭(%)={indicator_cols[4]}")

            row_data = [
                today_str, stock_name, f"'{ticker_str}", fluctuation, volume_100m,
                news[0][0], news[0][1], news[1][0], news[1][1], news[2][0], news[2][1],
                charts[0], charts[1], charts[2], keyword,
                *indicator_cols,
            ]
            rows_to_append.append(row_data)
            time.sleep(0.5)  # 네이버 요청 제한 방지

        except Exception as e:
            print(f"[{ticker}] 급등주 처리 중 에러: {e}")
            continue
            
    if rows_to_append:
        worksheet.append_rows(rows_to_append, value_input_option='USER_ENTERED')
        print(f"급등주 {len(rows_to_append)}건 업로드 완료.")
        # 차트 이미지가 잘 보이도록 셀 크기 조정 (차트 컬럼: 11, 12, 13 -> startIndex 11, endIndex 14)
        resize_cells_for_images(worksheet, 11, 14)
    else:
        print("조건에 맞는 급등주가 없습니다.")

def task2_high_volume_stocks(today_str, df_today, sh, sector_map):
    """
    작업 2: 거래대금 급증 종목 수집 (500억 이상 + 변동폭 6% 이상)
    """
    print("--- 작업 2: 거래대금 급증 종목 수집 시작 ---")
    
    headers = [
        "날짜", "종목명", "종목코드", "등락률(%)", "변동폭(%)", "거래대금(억)",
        "뉴스1_제목", "뉴스1_URL", "뉴스2_제목", "뉴스2_URL", "뉴스3_제목", "뉴스3_URL",
        "3개월차트", "1년차트", "3년차트", "키워드",
        "52주신고", "52주신저", "연속봉", "ATR14(%)", "갭(%)",
    ]
    worksheet = ensure_worksheet(sh, "거래대금_쉐도잉", headers)
    # 기존 시트에 지표 5개 컬럼이 없으면 헤더 마이그레이션
    ensure_header_columns(worksheet, headers)
    existing_keys = get_existing_keys(worksheet)
    
    # 고가, 저가 정보가 정확하지 않을 수 있으므로, 먼저 거래대금으로 1차 필터링
    cond_volume = df_today['거래대금'] >= (CONFIG["VOLUME_THRESHOLD"] * 100000000)
    cond_exclude = ~df_today.index.isin(CONFIG["EXCLUDE_STOCKS"])
    
    target_df = df_today[cond_volume & cond_exclude].copy()
    
    # 지표용 OHLCV 조회 시작일 (52주=252거래일 + 여유 28일)
    indicator_start = (datetime.datetime.today() - datetime.timedelta(days=400)).strftime("%Y%m%d")

    rows_to_append = []
    for ticker, row in target_df.iterrows():
        try:
            ticker_str = str(ticker).zfill(6)

            # 중복 체크
            if (today_str, ticker_str) in existing_keys:
                print(f"이미 존재하는 데이터 건너뜀 (거래대금): {row['종목명']} ({ticker_str})")
                continue

            # fdr.DataReader로 280거래일 OHLCV 조회 (고가/저가 + 지표 계산에 함께 사용)
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    df_detail = ex.submit(fdr.DataReader, ticker_str, indicator_start).result(timeout=15)
            except concurrent.futures.TimeoutError:
                print(f"[{ticker_str}] DataReader 타임아웃 — 건너뜀")
                continue

            if df_detail is None or df_detail.empty:
                continue

            high = float(df_detail['High'].iloc[-1])
            low = float(df_detail['Low'].iloc[-1])

            if low > 0:
                volatility = (high - low) / low * 100
            else:
                volatility = 0.0

            # 2차 필터링: 변동폭 6% 이상
            if volatility < CONFIG["FLUCTUATION_THRESHOLD"]:
                continue

            stock_name = row['종목명']
            fluctuation = round(row['등락률'], 2)
            volatility = round(volatility, 2)
            volume_100m = round(row['거래대금'] / 100000000, 2)

            print(f"처리 중 (거래대금): {stock_name} ({ticker_str}) - 거래대금 {volume_100m}억, 변동폭 {volatility}%")

            news = get_naver_news(ticker_str, stock_name)
            charts = get_chart_formulas(ticker_str)
            keyword = sector_map.lookup(ticker_str)

            # 지표 컬럼: df_detail 재사용 (이미 280일치 조회 완료)
            try:
                indicators = compute_indicators(df_detail)
                prev_close = float(df_detail["Close"].iloc[-2]) if len(df_detail) >= 2 else 0.0
                today_open = float(df_detail["Open"].iloc[-1]) if "Open" in df_detail.columns else 0.0
                indicator_cols = build_indicator_columns(indicators, prev_close, today_open)
            except Exception as e:
                print(f"[{ticker_str}] 지표 계산 에러: {e}")
                indicator_cols = ["", "", 0, 0.0, 0.0]
            print(f"  [지표] 52주신고={indicator_cols[0]!r}, 52주신저={indicator_cols[1]!r}, 연속봉={indicator_cols[2]}, ATR14(%)={indicator_cols[3]}, 갭(%)={indicator_cols[4]}")

            row_data = [
                today_str, stock_name, f"'{ticker_str}", fluctuation, volatility, volume_100m,
                news[0][0], news[0][1], news[1][0], news[1][1], news[2][0], news[2][1],
                charts[0], charts[1], charts[2], keyword,
                *indicator_cols,
            ]
            rows_to_append.append(row_data)
            time.sleep(0.5)
            
        except Exception as e:
            print(f"[{ticker}] 거래대금 급증주 처리 중 에러: {e}")
            continue
            
    if rows_to_append:
        worksheet.append_rows(rows_to_append, value_input_option='USER_ENTERED')
        print(f"거래대금 급증주 {len(rows_to_append)}건 업로드 완료.")
        # 차트 이미지가 잘 보이도록 셀 크기 조정 (차트 컬럼: 12, 13, 14 -> startIndex 12, endIndex 15)
        resize_cells_for_images(worksheet, 12, 15)
    else:
        print("조건에 맞는 거래대금 급증주가 없습니다.")

# ==========================================
# 이슈 #6: 낙폭과대 필터 함수
# ==========================================

def filter_drop_stocks(df: pd.DataFrame, threshold: float = -15.0) -> pd.DataFrame:
    """
    낙폭과대 1차 필터: 등락률이 threshold 이하인 종목 반환 (순수 함수).

    Parameters
    ----------
    df        : 등락률 컬럼을 포함하는 DataFrame (index = 종목코드)
    threshold : 등락률 상한 (부호 포함, 기본값 -15.0)

    Returns
    -------
    조건을 만족하는 종목만 포함된 DataFrame
    """
    return cast(pd.DataFrame, df[df['등락률'] <= threshold].copy())


def filter_drop_stocks_combined(df: pd.DataFrame) -> pd.DataFrame:
    """
    낙폭과대 복합 필터 (순수 함수).
    조건 A: 등락률 <= DROP_THRESHOLD (-15%)
    조건 B: 거래대금 >= VOLUME_THRESHOLD(500억) AND 등락률 <= DROP_SECONDARY_THRESHOLD (-6%)
    A OR B 를 만족하는 종목 반환.
    """
    vol_won = CONFIG["VOLUME_THRESHOLD"] * 100_000_000  # 억 → 원
    cond_a = df['등락률'] <= CONFIG["DROP_THRESHOLD"]
    cond_b = (df['거래대금'] >= vol_won) & (df['등락률'] <= CONFIG["DROP_SECONDARY_THRESHOLD"])
    return cast(pd.DataFrame, df[cond_a | cond_b].copy())


def task3_drop_stocks(today_str: str, df_today: pd.DataFrame, sh, sector_map) -> None:
    """
    작업 3: 낙폭과대 종목 수집.
    기존 task1_surge_stocks 와 대칭 구조 (등락률 부호 반전).
    워크시트명: 낙폭과대_쉐도잉
    """
    print("--- 작업 3: 낙폭과대 종목 수집 시작 ---")

    headers = [
        "날짜", "종목명", "종목코드", "등락률(%)", "거래대금(억)",
        "뉴스1_제목", "뉴스1_URL", "뉴스2_제목", "뉴스2_URL", "뉴스3_제목", "뉴스3_URL",
        "3개월차트", "1년차트", "3년차트", "키워드",
        "52주신고", "52주신저", "연속봉", "ATR14(%)", "갭(%)",
    ]
    worksheet = ensure_worksheet(sh, "낙폭과대_쉐도잉", headers)
    # 기존 시트에 지표 5개 컬럼이 없으면 헤더 마이그레이션
    ensure_header_columns(worksheet, headers)
    existing_keys = get_existing_keys(worksheet)

    drop_df = filter_drop_stocks_combined(df_today)
    indicator_start = (datetime.datetime.today() - datetime.timedelta(days=400)).strftime("%Y%m%d")

    rows_to_append = []
    for ticker, row in drop_df.iterrows():
        try:
            ticker_str = str(ticker).zfill(6)
            if (today_str, ticker_str) in existing_keys:
                print(f"이미 존재하는 데이터 건너뜀 (낙폭과대): {row['종목명']} ({ticker_str})")
                continue

            stock_name = str(row['종목명'])
            fluctuation = round(float(row['등락률']), 2)
            volume_100m = round(float(row['거래대금']) / 100_000_000, 2)

            print(f"처리 중 (낙폭과대): {stock_name} ({ticker_str}) - {fluctuation}%")

            news = get_naver_news(ticker_str, stock_name)
            charts = get_chart_formulas(ticker_str)
            keyword = sector_map.lookup(ticker_str)
            indicator_cols = enrich_with_indicators(ticker_str, indicator_start)

            row_data = [
                today_str, stock_name, f"'{ticker_str}", fluctuation, volume_100m,
                news[0][0], news[0][1], news[1][0], news[1][1], news[2][0], news[2][1],
                charts[0], charts[1], charts[2], keyword,
                *indicator_cols,
            ]
            rows_to_append.append(row_data)
            time.sleep(0.5)

        except Exception as e:
            print(f"[{ticker}] 낙폭과대 처리 중 에러: {e}")
            continue

    if rows_to_append:
        worksheet.append_rows(rows_to_append, value_input_option='USER_ENTERED')
        print(f"낙폭과대 {len(rows_to_append)}건 업로드 완료.")
        resize_cells_for_images(worksheet, 11, 14)
    else:
        print("조건에 맞는 낙폭과대 종목이 없습니다.")


# ==========================================
# 실행 블록
# ==========================================
def main():
    import os
    dry_run = os.environ.get("DRY_RUN", "0") == "1"
    today = datetime.datetime.today()

    # DRY_RUN=1 이면 Google Sheets 연결 없이 지표 컬럼 stdout 검증만 수행
    # MOCK=1 추가 시 FDR 네트워크 없이 합성 데이터로 검증 (오프라인 환경 포함)
    if dry_run:
        mock_mode = os.environ.get("MOCK", "0") == "1"
        print(f"[DRY RUN] Google Sheets skip - {'MOCK(no network)' if mock_mode else 'live FDR'}")
        try:
            if mock_mode:
                # 합성 DataFrame - 네트워크 불필요, Windows cp949 환경에서도 동작
                df_today = pd.DataFrame({
                    '종목명': ['테스트종목A'],
                    '등락률': [18.0],
                    '거래대금': [80_000_000_000],
                }, index=["005930"])
                sector_map = SectorMapKR("sector_map_kr.json")
                sector_map.load(known_tickers=["005930"])
                dry_run_indicator_check(df_today, sector_map, mock_indicators=True)
            else:
                df_krx = fdr.StockListing('KRX')
                df_today_raw = df_krx[df_krx['Market'].str.contains('KOSPI|KOSDAQ', na=False)].copy()
                today_str = resolve_trading_date(df_krx, today)
                df_today = df_today_raw.set_index('Code')
                df_today['종목명'] = df_today['Name']
                df_today['등락률'] = cast(pd.Series, pd.to_numeric(df_today['ChagesRatio'], errors='coerce')).fillna(0)
                df_today['거래대금'] = cast(pd.Series, pd.to_numeric(df_today['Amount'], errors='coerce')).fillna(0)
                anchor_df = df_today_raw.reset_index() if 'Code' not in df_today_raw.columns else df_today_raw
                unit_multiplier = infer_volume_unit(anchor_df, _log_fn=print)
                if unit_multiplier != 1:
                    df_today['거래대금'] = df_today['거래대금'] * unit_multiplier
                sector_map = SectorMapKR("sector_map_kr.json")
                sector_map.load(known_tickers=df_today.index.tolist())
                dry_run_indicator_check(df_today, sector_map)
            print("[DRY RUN OK] KR preflight completed")
        except Exception as e:
            print(f"[DRY RUN error] {e}")
        return

    # 2. 당일 주식 데이터 가져오기 (KOSPI, KOSDAQ) — 날짜 확정을 위해 먼저 실행
    print("당일 주식 데이터(OHLCV) 수집 중...")

    try:
        df_krx = fdr.StockListing('KRX')

        # KOSPI, KOSDAQ 종목만 필터링
        df_today_raw = df_krx[df_krx['Market'].str.contains('KOSPI|KOSDAQ', na=False)].copy()

        if df_today_raw.empty:
            print("주식 데이터를 불러오지 못했습니다.")
            return

        # ── 이슈 #2: FDR 실제 거래일로 today_str 확정 ──
        today_str = resolve_trading_date(df_krx, today)
        month_str = datetime.datetime.strptime(today_str, "%Y%m%d").strftime("%Y%m")
        print(f"거래일: {today_str}")

        # pykrx와 동일한 컬럼명으로 매핑
        df_today = df_today_raw.set_index('Code')
        df_today['종목명'] = df_today['Name']
        df_today['등락률'] = cast(pd.Series, pd.to_numeric(df_today['ChagesRatio'], errors='coerce')).fillna(0)
        df_today['거래대금'] = cast(pd.Series, pd.to_numeric(df_today['Amount'], errors='coerce')).fillna(0)

        # ── 이슈 #15: 삼성전자 anchor 기반 거래대금 단위 보정 ──
        fdr_version = getattr(fdr, '__version__', 'unknown')
        print(f"[FDR 버전] {fdr_version}")
        anchor_df = df_today_raw.reset_index() if 'Code' not in df_today_raw.columns else df_today_raw
        unit_multiplier = infer_volume_unit(anchor_df, _log_fn=print)
        print(f"[단위감지] FDR Amount 단위: {'원' if unit_multiplier == 1 else '백만원'} (배율 {unit_multiplier})")
        if unit_multiplier != 1:
            df_today['거래대금'] = df_today['거래대금'] * unit_multiplier

        print(f"[{today_str}] 주식 데이터 수집 완료.")

    except Exception as e:
        print(f"데이터 수집 실패: {e}")
        return

    # 1. Google Sheets 연동
    try:
        gc = get_gspread_client()
        spreadsheet_name = f"{CONFIG['SPREADSHEET_PREFIX']}{month_str}"

        try:
            sh = gc.open(spreadsheet_name)
            print(f"스프레드시트 '{spreadsheet_name}' 열기 성공: {sh.url}")
        except gspread.exceptions.SpreadsheetNotFound:
            print(f"스프레드시트 '{spreadsheet_name}'가 존재하지 않아 새로 생성합니다.")
            sh = gc.create(spreadsheet_name)
            print(f"새 스프레드시트 생성됨: {sh.url}")
            # 주의: 서비스 계정으로 생성한 시트는 서비스 계정 소유이므로,
            # 본인 계정으로 보려면 아래 주석을 해제하고 이메일을 입력하세요.
            # sh.share('your_email@gmail.com', perm_type='user', role='writer')

    except Exception as e:
        print(f"Google Sheets 인증 또는 열기 실패: {e}")
        return

    # 3. 섹터 맵 초기화 (네이버 WICS 캐시, 30일 자동 갱신)
    sector_map = SectorMapKR("sector_map_kr.json")
    sector_map.load(known_tickers=df_today.index.tolist())

    # 4. 작업 실행
    task1_surge_stocks(today_str, df_today, sh, sector_map)
    task2_high_volume_stocks(today_str, df_today, sh, sector_map)
    task3_drop_stocks(today_str, df_today, sh, sector_map)

    print("모든 작업이 완료되었습니다.")

if __name__ == "__main__":
    main()
