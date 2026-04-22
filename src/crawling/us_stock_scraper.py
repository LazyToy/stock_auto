from __future__ import annotations

import concurrent.futures
import datetime
import re
import time
import urllib.request
import json
import xml.etree.ElementTree as ET
import importlib
from typing import Any, cast

gspread = importlib.import_module("gspread")
Credentials = importlib.import_module("google.oauth2.service_account").Credentials
import pandas as pd
fdr = importlib.import_module("FinanceDataReader")
from src.crawling.streak_indicators import compute_indicators

from src.crawling._env_overrides import read_env_float, read_env_int
from src.crawling.service_account_path import resolve_service_account_file

# ==========================================
# CONFIG 설정
# ==========================================
CONFIG = {
    "SERVICE_ACCOUNT_FILE": "config/google_service_account.json",
    "SPREADSHEET_PREFIX": "주식_쉐도잉_",
    "SURGE_THRESHOLD_LARGE": read_env_float("CRAWL_US_SURGE_THRESHOLD_LARGE", 8.0),  # 대형주 급등 기준 (%)
    "SURGE_THRESHOLD_SMALL": read_env_float("CRAWL_US_SURGE_THRESHOLD_SMALL", 15.0),  # 소형주/바이오 급등 기준 (%)
    "DROP_THRESHOLD_LARGE": read_env_float("CRAWL_US_DROP_THRESHOLD_LARGE", -8.0),  # 대형주 낙폭과대 기준 (%)
    "DROP_THRESHOLD_SMALL": read_env_float("CRAWL_US_DROP_THRESHOLD_SMALL", -15.0),  # 소형주 낙폭과대 기준 (%)
    "MARKET_CAP_THRESHOLD": read_env_int("CRAWL_US_MARKET_CAP_THRESHOLD", 2000000000), # 대형주/소형주 구분 기준 (20억 달러)
    "VOLUME_THRESHOLD": read_env_int("CRAWL_US_VOLUME_THRESHOLD", 100000000),     # 거래대금 기준 (1억 달러)
    "VOLATILITY_THRESHOLD": read_env_float("CRAWL_US_VOLATILITY_THRESHOLD", 5.0),       # 변동폭 기준 (%)
}

def make_sheet_month(now: datetime.datetime) -> str:
    """스프레드시트 파일명용 날짜 문자열 (YYYYMM, 월 단위)."""
    return now.strftime("%Y%m")


def make_row_date(now: datetime.datetime) -> str:
    """행 날짜·dedup key 용 날짜 문자열 (YYYY-MM-DD, 일 단위)."""
    return now.strftime("%Y-%m-%d")


def get_google_sheet(today_str):
    """
    오늘 날짜의 구글 스프레드시트를 가져오거나 생성합니다.
    """
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    
    try:
        credentials = Credentials.from_service_account_file(resolve_service_account_file(), scopes=scopes)
        gc = gspread.authorize(credentials)
        
        file_name = f"{CONFIG['SPREADSHEET_PREFIX']}{today_str}"

        print(f"file_name \n {file_name}")
        
        try:
            sh = gc.open(file_name)
            print(f"기존 시트 오픈: {file_name}")
        except gspread.SpreadsheetNotFound:
            sh = gc.create(file_name)
            # 공유 설정 (필요시)
            # sh.share('your-email@gmail.com', perm_type='user', role='writer')
            print(f"새 시트 생성: {file_name}")
            
        return sh
    except Exception as e:
        print(f"구글 시트 인증/생성 에러: {e}")
        return None

def ensure_worksheet(sh, title, headers):
    """
    워크시트가 없으면 생성하고 헤더를 설정합니다.
    """
    try:
        ws = sh.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows="100", cols=len(headers))
        ws.append_row(headers)
        # 헤더 스타일 설정
        ws.format("A1:Z1", {
            "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9},
            "textFormat": {"bold": True}
        })
    return ws

# ==========================================
# 이슈 #16: TradingView 포지셔널 디코딩 분리
# ==========================================

_TICKER_RE = re.compile(r'^[A-Z.]+$')
_SANITY_PROBE_N = 5  # 첫 N건 sanity 프로브 개수


def decode_tv_row(d: list, strict: bool = False) -> dict:
    """
    TradingView scanner 응답의 'd' 배열을 필드명 dict 로 디코딩.

    컬럼 순서 (payload columns 리스트와 1:1 대응):
        d[0]=ticker, d[1]=name, d[2]=close, d[3]=change,
        d[4]=volume_value, d[5]=high, d[6]=low,
        d[7]=market_cap, d[8]=sector

    Sanity 조건:
        - close > 0
        - volume_value >= 0
        - ticker 가 ^[A-Z.]+$ 패턴 매칭 (BRK.A, BRK.B 허용)

    Parameters
    ----------
    d      : TradingView 응답 item['d'] 배열
    strict : True 이면 sanity 실패 시 ValueError 발생.
             False (기본) 이면 _sanity_ok=False 를 dict 에 포함하여 반환.

    Returns
    -------
    dict with keys: ticker, name, close, change, volume_value,
                    high, low, market_cap, sector, _sanity_ok
    """
    ticker = str(d[0]) if d[0] is not None else ""
    name = str(d[1]) if d[1] is not None else ""
    close = float(d[2]) if d[2] is not None else 0.0
    change = float(d[3]) if d[3] is not None else 0.0
    volume_value = float(d[4]) if d[4] is not None else 0.0
    high = float(d[5]) if d[5] is not None else 0.0
    low = float(d[6]) if d[6] is not None else 0.0
    market_cap = float(d[7]) if d[7] is not None else 0.0
    sector = str(d[8]) if len(d) > 8 and d[8] is not None else ""
    volume = float(d[9]) if len(d) > 9 and d[9] is not None else 0.0

    sanity_ok = (
        close > 0
        and volume_value >= 0
        and bool(_TICKER_RE.match(ticker))
    )

    if not sanity_ok and strict:
        raise ValueError(
            f"TradingView sanity check 실패: ticker={ticker!r}, "
            f"close={close}, volume_value={volume_value}"
        )

    return {
        "ticker": ticker,
        "name": name,
        "close": close,
        "change": change,
        "volume_value": volume_value,
        "high": high,
        "low": low,
        "market_cap": market_cap,
        "sector": sector,
        "volume": volume,
        "_sanity_ok": sanity_ok,
    }


def get_tradingview_data():
    """
    TradingView Screener API를 사용하여 미국 주식 데이터를 가져옵니다.
    """
    url = "https://scanner.tradingview.com/america/scan"
    payload = {
        "filter": [
            {"left": "type", "operation": "in_range", "right": ["stock", "dr"]},
            {"left": "exchange", "operation": "in_range", "right": ["AMEX", "NASDAQ", "NYSE"]},
            {"left": "Value.Traded", "operation": "greater", "right": CONFIG["VOLUME_THRESHOLD"]}
        ],
        "options": {"lang": "en"},
        "markets": ["america"],
        "symbols": {"query": {"types": []}, "tickers": []},
        "columns": ["name", "description", "close", "change", "Value.Traded", "high", "low", "market_cap_basic", "sector"],
        "sort": {"sortBy": "change", "sortOrder": "desc"},
        "range": [0, 500]
    }
    
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req) as res:
            data = json.loads(res.read().decode('utf-8'))
            raw_items = data.get('data', [])
            rows = []
            fail_count = 0
            for item in raw_items:
                decoded = decode_tv_row(item['d'], strict=False)
                if not decoded["_sanity_ok"]:
                    fail_count += 1
                rows.append(decoded)
            total_count = len(rows)
            # 첫 N건 중 1건이라도 실패 시 경고 + 전체 응답 로깅 (키 없이)
            first_n_fails = sum(1 for r in rows[:_SANITY_PROBE_N] if not r["_sanity_ok"])
            if first_n_fails > 0:
                import sys as _sys
                print(
                    f"[경고] TradingView 첫 {_SANITY_PROBE_N}건 중 {first_n_fails}건 sanity 실패 "
                    f"— 전체 응답 로깅:",
                    file=_sys.stderr,
                )
                for _item in raw_items:
                    print(_item.get('d', []), file=_sys.stderr)
            # 전체 sanity 실패 비율 5% 초과 시 경고
            if total_count > 0 and fail_count / total_count > 0.05:
                import sys as _sys
                print(
                    f"[경고] TradingView sanity check 실패 비율 "
                    f"{fail_count}/{total_count} "
                    f"({fail_count / total_count * 100:.1f}%) > 5%",
                    file=_sys.stderr,
                )
            return pd.DataFrame(rows)
    except Exception as e:
        print(f"TradingView API 에러: {e}")
        return pd.DataFrame()

def get_yahoo_rss_news(ticker):
    """
    Yahoo Finance RSS 피드에서 뉴스 최대 3개를 가져온다.

    엔드포인트: https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US
    RSS <item>에서 <title>과 <link>를 추출. 소형주·바이오 등 Naver가 미커버하는 종목에 fallback으로 사용.
    """
    url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
    news_list = []
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as res:
            raw = res.read()
        root = ET.fromstring(raw)
        for item in root.iter('item'):
            title_el = item.find('title')
            link_el = item.find('link')
            title = title_el.text.strip() if title_el is not None and title_el.text else ''
            link = link_el.text.strip() if link_el is not None and link_el.text else ''
            if title and link:
                news_list.append((title, link))
            if len(news_list) >= 3:
                break
    except Exception as e:
        print(f"[{ticker}] Yahoo RSS 뉴스 에러: {e}")
    return news_list


def get_naver_us_news(ticker):
    """
    네이버 증권 미국 주식 뉴스 가져오기.

    TradingView 티커는 suffix 없음 (e.g. AAPL).
    네이버 API는 거래소 suffix가 있어야 뉴스를 반환함:
      NASDAQ → .O,  NYSE → .N,  AMEX → .A
    따라서 .O → .N → .A 순서로 시도하고 뉴스가 나오면 중단.

    응답 구조:
      data = [{"total": N, "items": [{...}]}, ...]  (그룹 리스트)
    각 그룹에서 items를 평탄화해 최대 3개 수집.
    URL은 item 내 mobileNewsUrl 필드를 직접 사용.
    """
    # 이미 suffix가 있으면 그대로, 없으면 거래소별 suffix 순서로 시도
    if '.' in ticker:
        ticker_variants = [ticker]
    else:
        ticker_variants = [
            ticker + '.O',  # NASDAQ
            ticker + '.N',  # NYSE
            ticker + '.A',  # AMEX
        ]

    news_list = []
    for variant in ticker_variants:
        try:
            url = f"https://api.stock.naver.com/news/stock/{variant}?pageSize=3&page=1"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as res:
                data = json.loads(res.read().decode('utf-8'))

            if not isinstance(data, list) or not data:
                continue

            # 모든 그룹의 items를 평탄화
            items = [item for group in data for item in group.get('items', [])]

            for item in items[:3]:
                title = item.get('title', '').strip()
                link = item.get('mobileNewsUrl', '').strip()
                if title and link:
                    news_list.append((title, link))

            if news_list:
                break  # 뉴스를 찾았으면 다음 suffix는 시도하지 않음

        except Exception as e:
            print(f"[{variant}] 뉴스 가져오기 에러: {e}")
            continue

    # Naver에서 못 찾으면 Yahoo Finance RSS fallback
    if not news_list:
        news_list = get_yahoo_rss_news(ticker)

    # 3개 미만이면 빈 값으로 채움
    while len(news_list) < 3:
        news_list.append(("", ""))
    return news_list[:3]

def get_chart_formulas(ticker):
    """
    Finviz 이미지 URL을 Google Sheets IMAGE 수식으로 반환.
    일봉/주봉/월봉 + 3개월/1년/5년 총 6개 반환.
    - p=d: 일봉 (~6개월), p=w: 주봉 (~3년), p=m: 월봉 (~10년+)
    - ty=c: 캔들차트, ty=l: 라인차트 / ta=1: 기술지표 포함, ta=0: 없음
    """
    url_d   = f"https://finviz.com/chart.ashx?t={ticker}&ty=c&ta=1&p=d"   # 일봉 캔들 (~6개월)
    url_w   = f"https://finviz.com/chart.ashx?t={ticker}&ty=c&ta=1&p=w"   # 주봉 캔들 (~3년)
    url_m   = f"https://finviz.com/chart.ashx?t={ticker}&ty=c&ta=1&p=m"   # 월봉 캔들 (~10년+)
    url_3m  = f"https://finviz.com/chart.ashx?t={ticker}&ty=l&ta=0&p=d"   # 3개월 라인 (~6개월)
    url_1y  = f"https://finviz.com/chart.ashx?t={ticker}&ty=l&ta=0&p=w"   # 1년 라인 (~3년)
    url_5y  = f"https://finviz.com/chart.ashx?t={ticker}&ty=l&ta=0&p=m"   # 5년 라인 (~10년+)

    return (
        f'=IMAGE("{url_d}")',  f'=IMAGE("{url_w}")',  f'=IMAGE("{url_m}")',
        f'=IMAGE("{url_3m}")', f'=IMAGE("{url_1y}")', f'=IMAGE("{url_5y}")'
    )

def resize_cells_for_images(worksheet, start_col_index, end_col_index, row_height=300, col_width=600):
    """
    셀 크기 조정 (너비 600, 높이 300)
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
                        "properties": {"pixelSize": col_width},
                        "fields": "pixelSize"
                    }
                },
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": worksheet.id,
                            "dimension": "ROWS",
                            "startIndex": 1,
                            "endIndex": 1000
                        },
                        "properties": {"pixelSize": row_height},
                        "fields": "pixelSize"
                    }
                }
            ]
        }
        worksheet.spreadsheet.batch_update(body)
    except Exception as e:
        print(f"셀 크기 조정 에러: {e}")

def get_existing_keys(worksheet):
    try:
        records = worksheet.get_all_values()
        keys = set()
        for row in records[1:]:
            if len(row) >= 3:
                keys.add((row[0], row[2]))
        return keys
    except:
        return set()

# ==========================================
# 지표 헬퍼 함수 (이슈 #1)
# ==========================================

def _build_indicator_columns(indicators: dict, prev_close: float, today_open: float) -> list:
    """compute_indicators 결과 + 전일종가/금일시가로 5개 컬럼 값 생성."""
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


def _enrich_us_with_indicators(ticker_str: str, start_date: str) -> list:
    """FDR DataReader로 280거래일 OHLCV 조회 후 미국 종목 지표 컬럼 5개 생성.
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
        return _build_indicator_columns(indicators, prev_close, today_open)
    except concurrent.futures.TimeoutError:
        print(f"[{ticker_str}] 지표 DataReader 타임아웃 - 지표 컬럼 빈값 처리")
        return _EMPTY
    except Exception as e:
        print(f"[{ticker_str}] 지표 계산 에러: {e}")
        return _EMPTY

def _run_dry_run_preflight(mock_mode: bool) -> None:
    source = "MOCK(no network)" if mock_mode else "live TradingView"
    print(f"[DRY RUN] Google Sheets skip - {source}")
    if mock_mode:
        print("[DRY RUN OK] US preflight completed")
        return

    df = get_tradingview_data()
    if df.empty:
        print("[DRY RUN] TradingView returned no rows")
        return

    print(f"[DRY RUN OK] TradingView rows={len(df)}")


def main():
    import os

    dry_run = os.environ.get("DRY_RUN", "0") == "1"
    mock_mode = os.environ.get("MOCK", "0") == "1"
    now = datetime.datetime.now()
    sheet_month_str = make_sheet_month(now)   # 스프레드시트 파일명: YYYYMM (월 단위)
    row_date_str    = make_row_date(now)       # 행 날짜·dedup key: YYYY-MM-DD (일 단위)
    print(f"거래일(행): {row_date_str}  /  시트월: {sheet_month_str}")
    print(f"--- 미국 주식 스크래핑 시작 ({row_date_str}) ---")

    if dry_run:
        _run_dry_run_preflight(mock_mode)
        return

    sh = get_google_sheet(sheet_month_str)
    if not sh: return
    
    df = get_tradingview_data()
    if df.empty:
        print("데이터를 가져오지 못했습니다.")
        return
    
    # 작업 1: 미국 급등주
    print("--- 작업 1: 미국 급등주 수집 ---")
    headers1 = [
        "날짜", "종목명", "티커", "등락률(%)", "거래대금($)", "시총($)",
        "뉴스1", "URL1", "뉴스2", "URL2", "뉴스3", "URL3",
        "일봉", "주봉", "월봉", "3개월", "1년", "3년", "키워드",
        "52주신고", "52주신저", "연속봉", "ATR14(%)", "갭(%)",
    ]
    ws1 = ensure_worksheet(sh, "미국_급등주_쉐도잉", headers1)
    existing1 = get_existing_keys(ws1)

    # 지표용 OHLCV 조회 시작일 (52주=252거래일 + 여유 28일)
    indicator_start = (datetime.datetime.today() - datetime.timedelta(days=400)).strftime("%Y%m%d")

    # 필터링: (대형주 & 8% 이상) OR (소형주 & 15% 이상)
    cond_large = (df['market_cap'] >= CONFIG["MARKET_CAP_THRESHOLD"]) & (df['change'] >= CONFIG["SURGE_THRESHOLD_LARGE"])
    cond_small = (df['market_cap'] < CONFIG["MARKET_CAP_THRESHOLD"]) & (df['change'] >= CONFIG["SURGE_THRESHOLD_SMALL"])
    surge_df = df[cond_large | cond_small]

    rows1 = []
    for _, row in surge_df.iterrows():
        ticker = str(row['ticker'])
        if (row_date_str, ticker) in existing1: continue

        row_name = str(row['name'])
        print(f"처리 중 (급등): {row_name} ({ticker})")
        news = get_naver_us_news(ticker)
        charts = get_chart_formulas(ticker)
        indicator_cols = _enrich_us_with_indicators(ticker, indicator_start)
        print(f"  [지표] 52주신고={indicator_cols[0]!r}, 52주신저={indicator_cols[1]!r}, 연속봉={indicator_cols[2]}, ATR14(%)={indicator_cols[3]}, 갭(%)={indicator_cols[4]}")

        rows1.append([
            row_date_str, row_name, ticker, round(float(row['change']), 2),
            round(float(row['volume_value']), 0), round(float(row['market_cap']), 0),
            news[0][0], news[0][1], news[1][0], news[1][1], news[2][0], news[2][1],
            charts[0], charts[1], charts[2], charts[3], charts[4], charts[5],
            str(row.get('sector') or ''),
            *indicator_cols,
        ])
        time.sleep(0.5)

    if rows1:
        ws1.append_rows(rows1, value_input_option='USER_ENTERED')
        resize_cells_for_images(ws1, 12, 18)
        print(f"급등주 {len(rows1)}건 완료")
        
    # 작업 2: 미국 거래대금/변동성
    print("--- 작업 2: 미국 거래대금 급증주 수집 ---")
    headers2 = [
        "날짜", "종목명", "티커", "등락률(%)", "변동폭(%)", "거래대금($)",
        "뉴스1", "URL1", "뉴스2", "URL2", "뉴스3", "URL3",
        "일봉", "주봉", "월봉", "3개월", "1년", "3년", "키워드",
        "52주신고", "52주신저", "연속봉", "ATR14(%)", "갭(%)",
    ]
    ws2 = ensure_worksheet(sh, "미국_거래대금_쉐도잉", headers2)
    existing2 = get_existing_keys(ws2)

    # 변동폭 계산 및 필터링
    df['volatility'] = (df['high'] - df['low']) / df['low'] * 100
    vol_df = df[df['volatility'] >= CONFIG["VOLATILITY_THRESHOLD"]]

    rows2 = []
    for _, row in vol_df.iterrows():
        ticker = str(row['ticker'])
        if (row_date_str, ticker) in existing2: continue

        row_name = str(row['name'])
        print(f"처리 중 (거래대금): {row_name} ({ticker})")
        news = get_naver_us_news(ticker)
        charts = get_chart_formulas(ticker)
        indicator_cols = _enrich_us_with_indicators(ticker, indicator_start)
        print(f"  [지표] 52주신고={indicator_cols[0]!r}, 52주신저={indicator_cols[1]!r}, 연속봉={indicator_cols[2]}, ATR14(%)={indicator_cols[3]}, 갭(%)={indicator_cols[4]}")

        rows2.append([
            row_date_str, row_name, ticker, round(float(row['change']), 2), round(float(row['volatility']), 2),
            round(float(row['volume_value']), 0),
            news[0][0], news[0][1], news[1][0], news[1][1], news[2][0], news[2][1],
            charts[0], charts[1], charts[2], charts[3], charts[4], charts[5],
            str(row.get('sector') or ''),
            *indicator_cols,
        ])
        time.sleep(0.5)

    if rows2:
        ws2.append_rows(rows2, value_input_option='USER_ENTERED')
        resize_cells_for_images(ws2, 12, 18)
        print(f"거래대금 급증주 {len(rows2)}건 완료")

    # 작업 3: 미국 낙폭과대
    task3_us_drop_stocks(row_date_str, df, sh)

def task3_us_drop_stocks(today_str: str, df: pd.DataFrame, sh) -> None:
    """
    작업 3: 미국 낙폭과대 종목 수집.
    기존 task1(급등) 과 대칭 구조 — 등락률 부호 반전.
    워크시트명: 미국_낙폭과대_쉐도잉
    """
    print("--- 작업 3: 미국 낙폭과대 종목 수집 ---")
    headers3 = [
        "날짜", "종목명", "티커", "등락률(%)", "거래대금($)", "시총($)",
        "뉴스1", "URL1", "뉴스2", "URL2", "뉴스3", "URL3",
        "일봉", "주봉", "월봉", "3개월", "1년", "3년", "키워드",
        "52주신고", "52주신저", "연속봉", "ATR14(%)", "갭(%)",
    ]
    ws3 = ensure_worksheet(sh, "미국_낙폭과대_쉐도잉", headers3)
    existing3 = get_existing_keys(ws3)

    indicator_start = (datetime.datetime.today() - datetime.timedelta(days=400)).strftime("%Y%m%d")

    cond_large = (
        (df['market_cap'] >= CONFIG["MARKET_CAP_THRESHOLD"])
        & (df['change'] <= CONFIG["DROP_THRESHOLD_LARGE"])
    )
    cond_small = (
        (df['market_cap'] < CONFIG["MARKET_CAP_THRESHOLD"])
        & (df['change'] <= CONFIG["DROP_THRESHOLD_SMALL"])
    )
    drop_df = df[cond_large | cond_small]

    rows3 = []
    for _, row in drop_df.iterrows():
        ticker = str(row['ticker'])
        if (today_str, ticker) in existing3:
            continue

        row_name = str(row['name'])
        print(f"처리 중 (낙폭과대): {row_name} ({ticker})")
        news = get_naver_us_news(ticker)
        charts = get_chart_formulas(ticker)
        indicator_cols = _enrich_us_with_indicators(ticker, indicator_start)

        rows3.append([
            today_str, row_name, ticker, round(float(row['change']), 2),
            round(float(row['volume_value']), 0), round(float(row['market_cap']), 0),
            news[0][0], news[0][1], news[1][0], news[1][1], news[2][0], news[2][1],
            charts[0], charts[1], charts[2], charts[3], charts[4], charts[5],
            str(row.get('sector') or ''),
            *indicator_cols,
        ])
        time.sleep(0.5)

    if rows3:
        ws3.append_rows(rows3, value_input_option='USER_ENTERED')
        resize_cells_for_images(ws3, 12, 18)
        print(f"낙폭과대 {len(rows3)}건 완료")
    else:
        print("조건에 맞는 미국 낙폭과대 종목이 없습니다.")


if __name__ == "__main__":
    main()
