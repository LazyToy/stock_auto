import os
import streamlit as st
import yfinance as yf
import pandas as pd
import streamlit.components.v1 as components
import datetime
import traceback
import logging

logger = logging.getLogger("macro_tab")

# .env 로드 — 이 파일 기준으로 프로젝트 루트의 .env를 탐색
try:
    from dotenv import load_dotenv
    import pathlib
    _env_path = pathlib.Path(__file__).resolve().parents[2] / ".env"
    loaded = load_dotenv(dotenv_path=_env_path, override=False)
    if not loaded:
        print(f"[macro_tab] WARNING: .env 파일을 찾지 못했습니다 (탐색 경로: {_env_path})")
except ImportError:
    print("[macro_tab] WARNING: python-dotenv 미설치. pip install python-dotenv")

@st.cache_data(ttl=30)
def fetch_macro_data():
    from typing import Any
    data: dict[str, Any] = {}
    
    # ======== 1. yfinance Markets ========
    tickers = {
        'DXY': 'DX-Y.NYB',
        'US10Y': '^TNX',
        'VIX': '^VIX',
        'KRW': 'KRW=X',
        'KOSPI': '^KS11',
        'WTI': 'CL=F',
        'GOLD': 'GC=F',
        'SILVER': 'SI=F'
    }
    
    try:
        symbols = list(tickers.values())
        # period 5d to capture previous day reliably
        df_yf = yf.download(symbols, period='5d')['Close']
        df_yf = df_yf.ffill().bfill()
        
        for key, symbol in tickers.items():
            try:
                series = df_yf[symbol].dropna()
                if len(series) >= 2:
                    current_val = float(series.iloc[-1])
                    prev_val = float(series.iloc[-2])
                    change_pct = ((current_val / prev_val) - 1) * 100
                else:
                    current_val = float(series.iloc[-1]) if not series.empty else 0.0
                    change_pct = 0.0
                    
                data[key] = {
                    'val': current_val,
                    'change': change_pct,
                    'direction': 'up' if change_pct > 0 else 'dn' if change_pct < 0 else 'neu',
                    'sign': '▲' if change_pct > 0 else '▼' if change_pct < 0 else '—',
                    'change_str': f"{change_pct:+.2f}%"
                }
            except Exception:
                data[key] = {'val': None, 'change': None, 'direction': 'neu', 'sign': '—', 'change_str': "N/A"}

        # Calculate Gold/Silver Ratio
        try:
            gold_v = data.get('GOLD', {}).get('val')
            silver_v = data.get('SILVER', {}).get('val')
            gs_val = gold_v / silver_v if (gold_v is not None and silver_v and silver_v > 0) else None
            gs_change = None
            if gs_val is not None and 'GC=F' in df_yf.columns and 'SI=F' in df_yf.columns:
                gs_series = df_yf['GC=F'] / df_yf['SI=F']
                gs_series = gs_series.dropna()
                if len(gs_series) >= 2:
                    gs_prev = float(gs_series.iloc[-2])
                    gs_change = ((gs_val / gs_prev) - 1) * 100 if gs_prev else None

            data['GS_RATIO'] = {
                'val': gs_val,
                'change': gs_change,
                'direction': ('up' if gs_change is not None and gs_change > 0
                              else 'dn' if gs_change is not None and gs_change < 0 else 'neu'),
                'sign': ('▲' if gs_change is not None and gs_change > 0
                         else '▼' if gs_change is not None and gs_change < 0 else '—'),
                'change_str': f"{gs_change:+.2f}%" if gs_change is not None else "N/A"
            }
        except Exception:
            data['GS_RATIO'] = {'val': None, 'change': None, 'direction': 'neu', 'sign': '—', 'change_str': "N/A"}
    except Exception as e:
        print(f"yfinance error: {e}")
        for key in list(tickers.keys()) + ['GS_RATIO']:
            data[key] = {'val': None, 'change': None, 'direction': 'neu', 'sign': '—', 'change_str': "N/A"}

    # ======== 2. FRED API (fredapi 패키지 우선, fallback: pandas_datareader) ========
    fred_api_key = os.environ.get('FRED_API_KEY', '').strip()
    if not fred_api_key:
        print("[macro_tab] WARNING: FRED_API_KEY 미설정 — US 금리·CPI·한국 금리·PMI 표시 불가. "
              ".env 파일에 FRED_API_KEY=<키> 를 추가하세요.")
    else:
        print(f"[macro_tab] INFO: FRED_API_KEY 확인됨 (앞 4자리: {fred_api_key[:4]}****)")

    end_dt = datetime.datetime.now()
    start_dt = end_dt - datetime.timedelta(days=400)

    def _fetch_fred_series(series_id, api_key):
        """fredapi 우선, 없으면 pandas_datareader로 fallback. 실패 시 None + 콘솔 경고"""
        # 1차: fredapi
        try:
            from fredapi import Fred
            fred_client = Fred(api_key=api_key)
            s = fred_client.get_series(series_id, observation_start=start_dt)
            return s.dropna()
        except ImportError:
            print(f"[macro_tab] WARNING: fredapi 미설치. pip install fredapi")
        except Exception as e:
            print(f"[macro_tab] WARNING: fredapi로 {series_id} 조회 실패 → {type(e).__name__}: {e}")

        # 2차: pandas_datareader
        try:
            import pandas_datareader.data as web
            df = web.DataReader([series_id], 'fred', start_dt, end_dt)
            return df[series_id].dropna()
        except ImportError:
            print(f"[macro_tab] WARNING: pandas_datareader 미설치. pip install pandas-datareader")
        except Exception as e:
            print(f"[macro_tab] WARNING: pandas_datareader로 {series_id} 조회 실패 → {type(e).__name__}: {e}")

        return None

    # 미국 기준금리 (FEDFUNDS)
    try:
        s = _fetch_fred_series('FEDFUNDS', fred_api_key)
        data['US_RATE'] = {'val': float(s.iloc[-1]) if s is not None and len(s) > 0 else None}
    except Exception:
        data['US_RATE'] = {'val': None, 'is_stale': True}

    # 실업률 (UNRATE)
    try:
        s = _fetch_fred_series('UNRATE', fred_api_key)
        data['UNRATE'] = {'val': float(s.iloc[-1]) if s is not None and len(s) > 0 else None}
    except Exception:
        data['UNRATE'] = {'val': None, 'is_stale': True}

    # 하이일드 스프레드 (BAMLH0A0HYM2)
    try:
        s = _fetch_fred_series('BAMLH0A0HYM2', fred_api_key)
        data['SPREAD'] = {'val': float(s.iloc[-1]) if s is not None and len(s) > 0 else None}
    except Exception:
        data['SPREAD'] = {'val': None, 'is_stale': True}

    # 한국 외환보유고 (TRESEGKRM052N) — 단위: Millions of USD → /1000 = Billions USD
    try:
        s = _fetch_fred_series('TRESEGKRM052N', fred_api_key)
        data['RESERVE'] = {'val': float(s.iloc[-1]) / 1000 if s is not None and len(s) > 0 else None}
    except Exception:
        data['RESERVE'] = {'val': None, 'is_stale': True}

    # 미국 CPI YoY (CPIAUCSL)
    try:
        s = _fetch_fred_series('CPIAUCSL', fred_api_key)
        if s is not None and len(s) >= 13:
            cpi_yoy = ((float(s.iloc[-1]) / float(s.iloc[-13])) - 1) * 100
        else:
            cpi_yoy = None
        data['US_CPI'] = {'val': cpi_yoy}
    except Exception:
        data['US_CPI'] = {'val': None, 'is_stale': True}

    # 한국 기준금리 — FRED에 BOK 공식 기준금리 시리즈 없음
    # IRSTCI01KRM156N = 콜금리(익일물), 기준금리와 수bp 오차 허용 대용치
    # 정확한 BOK 기준금리는 ecos.bok.or.kr Open API 필요 (BOK_API_KEY)
    try:
        s = _fetch_fred_series('IRSTCI01KRM156N', fred_api_key)
        if s is None or len(s) == 0:
            s = _fetch_fred_series('INTDSRKRM193N', fred_api_key)
        kr_val = float(s.iloc[-1]) if s is not None and len(s) > 0 else None
        data['KR_RATE'] = {'val': kr_val, 'is_approx': True}  # 콜금리 대용치
        if kr_val is not None:
            print(f"[macro_tab] INFO: 한국 금리 {kr_val:.2f}% (콜금리 대용 — BOK 공식 기준금리와 수bp 차이 가능)")
    except Exception:
        data['KR_RATE'] = {'val': None, 'is_stale': True}

    # 한미 금리차 계산
    kr_r = data['KR_RATE']['val']
    us_r = data['US_RATE']['val']
    rate_diff = (kr_r - us_r) if (kr_r is not None and us_r is not None) else None
    data['RATE_DIFF'] = {'val': rate_diff}

    # 시카고연준 전국경기지수 CFNAI — FRED 무료 제공
    # CFNAI: 0=평균성장, 양수=평균 초과, 음수=평균 미달, -0.7 이하=경기침체 신호
    try:
        s = _fetch_fred_series('CFNAI', fred_api_key)
        cfnai_val = float(s.iloc[-1]) if s is not None and len(s) > 0 else None
        data['CFNAI'] = {'val': cfnai_val}
        if cfnai_val is not None:
            print(f"[macro_tab] INFO: CFNAI(경기종합지수) {cfnai_val:.2f}")
    except Exception:
        data['CFNAI'] = {'val': None}

    # ======== OECD CLI (Composite Leading Indicator) — 키 불필요, 완전 무료 ========
    # CLI: 100=장기 추세, 100 이상=확장, 100 미만=수축, 하락 추세면 경기 둔화 선행
    try:
        import requests as _req
        _oecd_url = ('https://stats.oecd.org/SDMX-JSON/data/MEI_CLI/'
                     'LOLITOAA.USA.M/all?startTime=2024-01')
        _oecd_resp = _req.get(_oecd_url, timeout=10)
        if _oecd_resp.status_code == 200:
            import json as _json
            _oecd_d = _json.loads(_oecd_resp.text)
            _ds = _oecd_d['data']['dataSets'][0]
            _series_key = list(_ds['series'].keys())[0]
            _obs = _ds['series'][_series_key]['observations']
            _sorted_keys = sorted(_obs.keys(), key=int)
            if len(_sorted_keys) >= 2:
                _cli_latest = float(_obs[_sorted_keys[-1]][0])
                _cli_prev = float(_obs[_sorted_keys[-2]][0])
                _cli_change = _cli_latest - _cli_prev
                data['OECD_CLI'] = {
                    'val': _cli_latest,
                    'change': _cli_change,
                    'direction': 'up' if _cli_change > 0 else 'dn' if _cli_change < 0 else 'neu',
                    'sign': '▲' if _cli_change > 0 else '▼' if _cli_change < 0 else '—',
                    'change_str': f"{_cli_change:+.2f}pt"
                }
                print(f"[macro_tab] INFO: OECD CLI {_cli_latest:.2f} ({_cli_change:+.2f}pt)")
            else:
                data['OECD_CLI'] = {'val': None, 'change': None, 'direction': 'neu', 'sign': '—', 'change_str': 'N/A'}
        else:
            print(f"[macro_tab] WARNING: OECD API 응답 {_oecd_resp.status_code}")
            data['OECD_CLI'] = {'val': None, 'change': None, 'direction': 'neu', 'sign': '—', 'change_str': 'N/A'}
    except Exception as e:
        print(f"[macro_tab] WARNING: OECD CLI 조회 실패 → {type(e).__name__}: {e}")
        data['OECD_CLI'] = {'val': None, 'change': None, 'direction': 'neu', 'sign': '—', 'change_str': 'N/A'}

    # ======== 3. Naver Finance for KOSPI Investment Trends (당월 누적) ========
    # pykrx의 KRX 거래대금 파싱 오류를 대신하여 네이버 금융 KOSPI 일별 투자자 동향을 스크래핑
    foreign_buy = retail_buy = pension_buy = 0.0
    try:
        import requests
        from io import StringIO
        today = datetime.datetime.today()
        target_month_str = today.strftime("%y.%m")
        
        headers = {'User-Agent': 'Mozilla/5.0'}
        for page in range(1, 4):
            d = today.strftime("%Y%m%d")
            url = f'https://finance.naver.com/sise/investorDealTrendDay.naver?bizdate={d}&sosok=01&page={page}'
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code != 200:
                break
            
            tables = pd.read_html(StringIO(resp.text))
            if not tables: break
            
            df = tables[0].dropna(thresh=5)
            # 네이버 금융 테이블은 기관계가 MultiIndex로 들어옴. 마지막 depth만 사용.
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [c[-1] for c in df.columns]
                
            # 당월 데이터만 필터링 (예: '24.03')
            df_month = df[df['날짜'].astype(str).str.startswith(target_month_str)]
            
            if df_month.empty and not df.empty:
                # 더 넘어가면 이전 달 데이터만 있으므로 루프를 미리 탈출
                break
                
            for _, row in df_month.iterrows():
                try:
                    retail_buy += float(str(row.get('개인', 0)).replace(',', ''))
                except ValueError: pass
                try:
                    foreign_buy += float(str(row.get('외국인', 0)).replace(',', ''))
                except ValueError: pass
                try:
                    pension_buy += float(str(row.get('연기금등', 0)).replace(',', ''))
                except ValueError: pass

        # 네이버 금융 단위는 '억원'. 원본 단위(원) 없이 여기서 바로 '조원'으로 환산 (/10000)
        foreign_buy = foreign_buy / 10000.0
        retail_buy = retail_buy / 10000.0
        pension_buy = pension_buy / 10000.0
        
    except Exception as e:
        print(f"[macro_tab] WARNING: 네이버 수급 스크래핑 오류 → {type(e).__name__}: {e}")
        foreign_buy = retail_buy = pension_buy = None

    data['FOREIGN_BUY'] = {'val': foreign_buy}
    data['RETAIL_BUY']  = {'val': retail_buy}
    data['PENSION_BUY'] = {'val': pension_buy}

    return data

def format_val(val, fmt="{:.2f}"):
    try:
        if val is None:
            return "N/A"
        if pd.isna(val):
            return "N/A"
        return fmt.format(val)
    except Exception:
        return str(val) if val is not None else "N/A"

def to_krw_string(usd_val, krw_rate):
    """Converts a USD value to KRW string like '(약 120,500원)' """
    try:
        if usd_val is None or krw_rate is None or krw_rate <= 0 or usd_val <= 0: return ""
        krw_val = usd_val * krw_rate
        if krw_val >= 1_000_000_000_000: # 1조 이상
             return f"<span style='font-size:12px;color:#888'> (~{krw_val/1_000_000_000_000:,.1f}조원)</span>"
        elif krw_val >= 100_000_000: # 1억 이상
             return f"<span style='font-size:12px;color:#888'> (~{krw_val/100_000_000:,.1f}억원)</span>"
        elif krw_val >= 10_000: # 1만 이상
             return f"<span style='font-size:12px;color:#888'> (~{krw_val/10_000:,.0f}만원)</span>"
        else:
             return f"<span style='font-size:12px;color:#888'> (~{krw_val:,.0f}원)</span>"
    except:
        return ""

def krw_to_usd_html(krw_trillion_val, krw_rate):
    """Converts a KRW Trillion value to USD Billions string with KRW in parenthesis."""
    try:
        if krw_trillion_val is None or krw_rate is None or krw_rate <= 0:
            return "N/A"
        usd_val = (krw_trillion_val * 1_000_000_000_000) / krw_rate
        usd_billions = usd_val / 1_000_000_000
        sign = "+" if usd_billions > 0 else "-" if usd_billions < 0 else ""
        usd_str = f"{sign}${abs(usd_billions):,.2f}B"
        krw_str = f"<span style='font-size:12px;color:#888;'> (~{krw_trillion_val:+.1f}조원)</span>"
        return f"{usd_str} {krw_str}"
    except Exception:
        return "N/A"

def render_macro_tab():
    with st.spinner("Fetching real-time macro data (Updates every 30s)..."):
        data = fetch_macro_data()

    # Get the KRW conversion rate
    krw_rate = data.get('KRW', {}).get('val', 0.0)

    # Convert USD values to KRW suffix (None-safe)
    wti_krw = to_krw_string(data['WTI']['val'], krw_rate)
    gold_krw = to_krw_string(data['GOLD']['val'], krw_rate)
    silver_krw = to_krw_string(data['SILVER']['val'], krw_rate)
    _reserve_val = data['RESERVE']['val']
    reserve_krw = to_krw_string(_reserve_val * 1e9 if _reserve_val is not None else None, krw_rate)
    
    # ======== 이슈 2-8: 임계값 상수 딕셔너리 ========
    MACRO_THRESHOLDS = {'DXY': 103, 'US10Y': 4.5, 'VIX': 30, 'KRW': 1400}

    # ======== None-safe 조건 변수 사전 계산 ========
    def _v(key):
        return data.get(key, {}).get('val')

    dxy_v      = _v('DXY')
    us10y_v    = _v('US10Y')
    vix_v      = _v('VIX')
    krw_v      = _v('KRW')
    rate_diff_v = _v('RATE_DIFF')
    kospi_ch   = data.get('KOSPI', {}).get('change')
    foreign_v  = _v('FOREIGN_BUY')
    retail_v   = _v('RETAIL_BUY')

    # DXY badge
    dxy_badge  = ('b-red' if dxy_v is not None and dxy_v > MACRO_THRESHOLDS['DXY'] else 'b-amb')
    dxy_label  = ('위험 — 신흥국 압박' if dxy_v is not None and dxy_v > MACRO_THRESHOLDS['DXY'] else '주의 — 모니터링')
    # US10Y badge
    us10y_badge = ('b-red' if us10y_v is not None and us10y_v > MACRO_THRESHOLDS['US10Y'] else 'b-grn')
    us10y_label = ('위험 — 주식 밸류 압박' if us10y_v is not None and us10y_v > MACRO_THRESHOLDS['US10Y'] else '안정 구간')
    # VIX badge
    vix_badge  = ('b-red' if vix_v is not None and vix_v > MACRO_THRESHOLDS['VIX']
                  else 'b-amb' if vix_v is not None and vix_v > 20 else 'b-grn')
    vix_label  = ('위험 — 극단공포' if vix_v is not None and vix_v > MACRO_THRESHOLDS['VIX']
                  else '주의 — 변동성확대' if vix_v is not None and vix_v > 20 else '안정적')
    # KRW badge
    krw_badge  = ('b-red' if krw_v is not None and krw_v > MACRO_THRESHOLDS['KRW'] else 'b-amb')
    krw_label  = ('위험 — 1,400원 이상' if krw_v is not None and krw_v > MACRO_THRESHOLDS['KRW'] else '주의 구간')
    # 한미금리차
    rate_diff_sub   = ('미국이 높음' if rate_diff_v is not None and rate_diff_v < 0 else '한국이 높음' if rate_diff_v is not None else 'N/A')
    rate_diff_cls   = ('up' if rate_diff_v is not None and rate_diff_v < 0 else 'neu')
    rate_diff_badge = ('b-red' if rate_diff_v is not None and rate_diff_v < -1.0 else 'b-amb')
    # KOSPI badge
    kospi_badge = ('b-red' if kospi_ch is not None and kospi_ch < -2
                   else 'b-grn' if kospi_ch is not None and kospi_ch > 1 else 'b-amb')
    # 이슈 2-5: 외국인 순매수 방향 반전 수정 ('up' = 매수 유입 = 긍정)
    foreign_sub_cls  = ('up' if foreign_v is not None and foreign_v > 0 else 'dn')
    foreign_badge    = ('b-grn' if foreign_v is not None and foreign_v > 0
                        else 'b-red' if foreign_v is not None else 'b-neu')
    foreign_badge_lbl= ('매수 유입' if foreign_v is not None and foreign_v > 0
                        else '매도 우위' if foreign_v is not None else 'N/A')
    # 개인 순매수 badge
    retail_badge = ('b-red' if retail_v is not None and foreign_v is not None and retail_v > 0 and foreign_v < 0 else 'b-amb')

    # KRW -> USD HTML conversions for investors
    foreign_val_html = krw_to_usd_html(foreign_v, krw_rate)
    retail_val_html = krw_to_usd_html(retail_v, krw_rate)
    pension_val_html = krw_to_usd_html(_v('PENSION_BUY'), krw_rate)

    # OECD CLI 사전 계산 (f-string 내 dict 직접 참조 금지)
    _oecd = data.get('OECD_CLI', {})
    oecd_val = _oecd.get('val')
    oecd_dir = _oecd.get('direction', 'neu')
    oecd_sign = _oecd.get('sign', '—')
    oecd_change_str = _oecd.get('change_str', 'N/A')
    oecd_badge = ('b-red' if oecd_val is not None and oecd_val < 99
                  else 'b-grn' if oecd_val is not None and oecd_val >= 100 else 'b-amb')
    oecd_badge_lbl = ('수축 국면' if oecd_val is not None and oecd_val < 99
                      else '확장 국면' if oecd_val is not None and oecd_val >= 100 else '주의')

    # CFNAI 사전 계산
    _cfnai = data.get('CFNAI', {})
    cfnai_val = _cfnai.get('val')
    cfnai_badge = ('b-red' if cfnai_val is not None and cfnai_val < -0.7
                   else 'b-grn' if cfnai_val is not None and cfnai_val > 0 else 'b-amb')
    cfnai_badge_lbl = ('침체 신호' if cfnai_val is not None and cfnai_val < -0.7
                       else '확장 국면' if cfnai_val is not None and cfnai_val > 0 else '보합')

    # HTML Template
    html_template = f"""
    <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:var(--font-sans,'Anthropic Sans',sans-serif); margin:0; padding:10px;}}
    .db{{padding:1rem 0;display:flex;flex-direction:column;gap:1rem}}
    .section-title{{font-size:11px;font-weight:500;color:var(--color-text-tertiary, #aaa);letter-spacing:.08em;text-transform:uppercase;margin-bottom:.5rem;padding-left:2px}}
    .grid2{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}}
    .grid3{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}}
    .grid4{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}}
    .card{{background:var(--color-background-primary, #fff);border:0.5px solid var(--color-border-tertiary, #e0e0e0);border-radius:8px;padding:.75rem 1rem;cursor:pointer;transition:border-color .15s;box-shadow: 0 1px 2px rgba(0,0,0,0.05);}}
    .card:hover{{border-color:#ccc}}
    @media (prefers-color-scheme: dark) {{
      .card{{background:#1e1e1e;border-color:#333;box-shadow: none;}}
      .card-label{{color:#aaa!important;}}
      .card-value{{color:#fff!important;}}
      .section-title{{color:#bbb!important;}}
      .detail-panel{{background:#222!important;color:#ccc!important;}}
      .master-card{{background:#1e1e1e!important; border-color:#333!important;}}
      .tab{{color:#aaa!important;border-color:#444!important;}}
      .tab.on{{background:#333!important;color:#fff!important;border-color:#555!important;}}
    }}
    .card-label{{font-size:11px;color:#666;margin-bottom:4px;font-weight:400}}
    .card-value{{font-size:20px;font-weight:500;color:#222;line-height:1}}
    .card-sub{{font-size:11px;margin-top:4px;font-weight:400}}
    .up{{color:#e24b4a}}
    .dn{{color:#185fa5}}
    .neu{{color:#777}}
    .badge{{display:inline-block;font-size:10px;font-weight:500;padding:2px 7px;border-radius:4px;margin-top:5px}}
    .b-red{{background:#fcebeb;color:#a32d2d}}
    .b-grn{{background:#e6f9ed;color:#1e7e44}}
    .b-amb{{background:#faeeda;color:#854f0b}}
    .b-blu{{background:#e6f1fb;color:#185fa5}}
    .b-neu{{background:#eee;color:#555}}
    .signal-bar{{display:flex;gap:4px;align-items:center;margin-bottom:.5rem}}
    .dot{{width:10px;height:10px;border-radius:50%;flex-shrink:0}}
    .dot-red{{background:#E24B4A}}
    .dot-amb{{background:#EF9F27}}
    .dot-grn{{background:#639922}}
    .signal-text{{font-size:12px;color:#666}}
    @media (prefers-color-scheme: dark) {{ .signal-text{{color:#aaa;}} }}
    .master-card{{background:#fff;border:0.5px solid #e0e0e0;border-radius:8px;padding:1rem 1.25rem}}
    .detail-panel{{background:#f9f9f9;border-radius:6px;padding:.75rem 1rem;margin-top:.5rem;font-size:12px;color:#555;line-height:1.6;display:none}}
    .detail-panel.show{{display:block}}
    .tab-row{{display:flex;gap:4px;margin-bottom:.75rem;flex-wrap:wrap}}
    .tab{{font-size:11px;padding:4px 10px;border-radius:6px;border:0.5px solid #ddd;cursor:pointer;color:#555;background:transparent;transition:all .15s}}
    .tab:hover{{background:#f0f0f0}}
    .tab.on{{background:#fff;color:#222;border-color:#999;font-weight:500}}
    .divider{{border:none;border-top:0.5px solid #e0e0e0;margin:.25rem 0}}
    .priority-tag{{font-size:10px;font-weight:500;padding:1px 5px;border-radius:3px;margin-left:4px;vertical-align:middle}}
    .p1{{background:#FCEBEB;color:#A32D2D}}
    .p2{{background:#FAEEDA;color:#854F0B}}
    .p3{{background:#E6F1FB;color:#185FA5}}
    </style>

    <div class="db">

    <div class="tab-row" id="tabs">
      <button class="tab on" onclick="switchTab('all')">전체 보기</button>
      <button class="tab" onclick="switchTab('macro')">글로벌 매크로</button>
      <button class="tab" onclick="switchTab('korea')">한국 시장</button>
      <button class="tab" onclick="switchTab('commodity')">에너지·원자재</button>
      <button class="tab" onclick="switchTab('signal')">종합 신호등</button>
    </div>

    <!-- SECTION: 글로벌 핵심 경보 -->
    <div class="sect" data-cat="macro">
      <div class="section-title">글로벌 핵심 경보 <span class="priority-tag p1">최우선 감시</span></div>
      <div class="grid4">
        <div class="card" onclick="toggle('d1')">
          <div class="card-label">달러 인덱스 DXY</div>
          <div class="card-value">{format_val(data['DXY']['val'])}</div>
          <div class="card-sub {data['DXY']['direction']}">{data['DXY']['sign']} {data['DXY']['change_str']} 전일비</div>
          <div class="badge {dxy_badge}">{dxy_label}</div>
          <div class="detail-panel" id="d1">30년차: DXY 103 돌파 시 신흥국 자금이탈 시작. 106↑이면 한국 외국인 매도 가속. 이 숫자 하나로 한국시장 방향이 결정된다.</div>
        </div>
        <div class="card" onclick="toggle('d2')">
          <div class="card-label">미국 기준금리</div>
          <div class="card-value">{format_val(data['US_RATE']['val'])}%</div>
          <div class="card-sub neu">최근 FED 실제 실효금리</div>
          <div class="badge b-amb">주의 — 인하 지연 여부</div>
          <div class="detail-panel" id="d2">30년차: Fed Funds Rate은 금값, 성장주, 신흥국 전체의 원점. 인하 기대가 살아야 리스크온. CME FedWatch 확률도 같이 봐야 한다.</div>
        </div>
        <div class="card" onclick="toggle('d3')">
          <div class="card-label">미국 10년물 국채</div>
          <div class="card-value">{format_val(data['US10Y']['val'], "{:.3f}")}%</div>
          <div class="card-sub {data['US10Y']['direction']}">{data['US10Y']['sign']} {data['US10Y']['change_str']} 전일비</div>
          <div class="badge {us10y_badge}">{us10y_label}</div>
          <div class="detail-panel" id="d3">30년차: 4.5% 이상이면 PER 압박 시작. 5% 돌파 시 2022년처럼 주식 전반 재편. 성장주 특히 직격. 연준 의도보다 시장금리가 먼저 움직인다.</div>
        </div>
        <div class="card" onclick="toggle('d4')">
          <div class="card-label">VIX 공포지수</div>
          <div class="card-value">{format_val(data['VIX']['val'])}</div>
          <div class="card-sub {data['VIX']['direction']}">{data['VIX']['sign']} {data['VIX']['change_str']} 전일비</div>
          <div class="badge {vix_badge}">{vix_label}</div>
          <div class="detail-panel" id="d4">30년차: 20↑ 시장 긴장, 30↑ 공포, 40↑ 극단공포(역발상 매수 신호). VIX spike 뒤 30일 이내 반등 확률 73%. 분할매수 타이밍.</div>
        </div>
      </div>
    </div>

    <!-- SECTION: 통화·금리 -->
    <div class="sect" data-cat="macro">
      <div class="section-title">통화·금리 환경 <span class="priority-tag p1">매일 확인</span></div>
      <div class="grid3">
        <div class="card" onclick="toggle('d5')">
          <div class="card-label">원달러 환율</div>
          <div class="card-value">{format_val(data['KRW']['val'], "{:,.0f}")} 원</div>
          <div class="card-sub {data['KRW']['direction']}">{data['KRW']['sign']} {data['KRW']['change_str']} 환율압력</div>
          <div class="badge {krw_badge}">{krw_label}</div>
          <div class="detail-panel" id="d5">30년차: 환율은 수입물가·기업원가·외국인 수급 3개를 동시에 움직인다. 미국주식 투자자는 환차손도 계산해야.</div>
        </div>
        <div class="card" onclick="toggle('d6')">
          <div class="card-label">한미 금리차</div>
          <div class="card-value">{format_val(data['RATE_DIFF']['val'], "{:+.2f}")}%p</div>
          <div class="card-sub {rate_diff_cls}">{rate_diff_sub}</div>
          <div class="badge {rate_diff_badge}">자본이탈 압력</div>
          <div class="detail-panel" id="d6">30년차: 금리차가 역전 상태이면 달러로 돈이 빨려간다. 1% 이상 차이면 외국인 수급에 지속 압력.</div>
        </div>
        <div class="card" onclick="toggle('d7')">
          <div class="card-label">한국 기준금리</div>
          <div class="card-value">{format_val(data['KR_RATE']['val'])}%</div>
          <div class="card-sub neu">한국은행 금리</div>
          <div class="badge b-amb">주의 — 진퇴양난</div>
          <div class="detail-panel" id="d7">30년차: 내리면 환율 폭등, 올리면 가계부채 폭발. 한은 발언에서 '완화' 단어가 늘어나면 선매수 신호.</div>
        </div>
      </div>
    </div>

    <!-- SECTION: 한국 시장 수급 -->
    <div class="sect" data-cat="korea">
      <div class="section-title">한국 시장 수급 <span class="priority-tag p1">금일 기준 누적</span></div>
      <div class="grid3">
        <div class="card" onclick="toggle('d8')">
          <div class="card-label">코스피 지수</div>
          <div class="card-value">{format_val(data['KOSPI']['val'], "{:,.2f}")}</div>
          <div class="card-sub {data['KOSPI']['direction']}">{data['KOSPI']['sign']} {data['KOSPI']['change_str']} (전일대비)</div>
          <div class="badge {kospi_badge}">방향성 탐색 중</div>
          <div class="detail-panel" id="d8">30년차: 코스피 숫자보다 '누가 사고 있는가'가 중요. 지수가 올라도 외국인이 파는 구조면 허상.</div>
        </div>
        <div class="card" onclick="toggle('d9')">
          <div class="card-label">당월 외국인 순매수 (KOSPI)</div>
          <div class="card-value">{foreign_val_html}</div>
          <div class="card-sub {foreign_sub_cls}">스마트머니 동향</div>
          <div class="badge {foreign_badge}">{foreign_badge_lbl}</div>
          <div class="detail-panel" id="d9">30년차: 외국인 수급이 가장 중요한 단일 지표. 반대로 외국인이 돌아오기 시작하면 진짜 반등 신호.</div>
        </div>
        <div class="card" onclick="toggle('d10')">
          <div class="card-label">한국 외환 보유고</div>
          <div class="card-value">${format_val(data['RESERVE']['val'], "{:,.0f}")}억 {reserve_krw}</div>
          <div class="card-sub neu">가장 최근 발표 수치</div>
          <div class="badge b-amb">주의 — 방어 자금력</div>
          <div class="detail-panel" id="d10">30년차: 외환보유고 안정성은 정부가 환율 방어에 쓸 수 있는 비상금의 규모.</div>
        </div>
      </div>
    </div>
    
    <div class="sect" data-cat="korea">
      <div class="grid2">
        <div class="card" onclick="toggle('dx1')">
          <div class="card-label">당월 개인 순매수 (KOSPI)</div>
          <div class="card-value">{retail_val_html}</div>
          <div class="card-sub neu">위험 — 역할 배분 변화</div>
          <div class="badge {retail_badge}">개인 물량 받이 여부</div>
          <div class="detail-panel" id="dx1">30년차: 개인이 외국인 매도 물량을 받아내면 위험. '스마트머니가 팔고 개미가 사는' 구조는 역사적으로 하락 선행 신호다.</div>
        </div>
        <div class="card" onclick="toggle('dx2')">
          <div class="card-label">당월 연기금 순매수 (KOSPI)</div>
          <div class="card-value">{pension_val_html}</div>
          <div class="card-sub neu">정책 매수력</div>
          <div class="badge b-amb">시장 받침 여부</div>
          <div class="detail-panel" id="dx2">30년차: 연기금은 '정책 매수'다. 펀더멘털 한계가 오면 지키지 못한다.</div>
        </div>
      </div>
    </div>

    <!-- SECTION: 에너지·원자재 -->
    <div class="sect" data-cat="commodity">
      <div class="section-title">에너지·원자재 (Source: Yahoo Finance) <span class="priority-tag p2">주 2회 확인</span></div>
      <div class="grid4">
        <div class="card" onclick="toggle('d14')">
          <div class="card-label">WTI 유가 (NYMEX)</div>
          <div class="card-value">${format_val(data['WTI']['val'])}<span style="font-size:12px;color:#888;">/배럴</span> {wti_krw}</div>
          <div class="card-sub {data['WTI']['direction']}">{data['WTI']['sign']} {data['WTI']['change_str']}</div>
          <div class="badge {'b-red' if data['WTI']['val'] is not None and data['WTI']['val'] > 85 else 'b-grn'}">{'위험 — 인플레 압박' if data['WTI']['val'] is not None and data['WTI']['val'] > 85 else '안정 국면'}</div>
          <div class="detail-panel" id="d14">30년차: 유가는 모든 물가의 어머니. $90↑ 유지되면 Fed 인하 불가. $80↓ 안정되면 기대 부활. (yfinance CL=F)</div>
        </div>
        <div class="card" onclick="toggle('d15')">
          <div class="card-label">금 (Gold, COMEX)</div>
          <div class="card-value">${format_val(data['GOLD']['val'], "{:,.1f}")}<span style="font-size:12px;color:#888;">/온스</span> {gold_krw}</div>
          <div class="card-sub {data['GOLD']['direction']}">{data['GOLD']['sign']} {data['GOLD']['change_str']}</div>
          <div class="badge {'b-grn' if data['GOLD']['change'] is not None and data['GOLD']['change'] > 0 else 'b-amb'}">안전자산 선호</div>
          <div class="detail-panel" id="d15">30년차: 금값 하락은 공포가 아니라 매수 기회일 수 있다. 중앙은행이 뒷받침한다. (yfinance GC=F)</div>
        </div>
        <div class="card" onclick="toggle('d16')">
          <div class="card-label">은 (Silver, COMEX)</div>
          <div class="card-value">${format_val(data['SILVER']['val'], "{:.2f}")}<span style="font-size:12px;color:#888;">/온스</span> {silver_krw}</div>
          <div class="card-sub {data['SILVER']['direction']}">{data['SILVER']['sign']} {data['SILVER']['change_str']}</div>
          <div class="badge b-grn">산업+안전자산</div>
          <div class="detail-panel" id="d16">30년차: 은은 금보다 변동성이 2배. 산업 수요 회복 시 탄력이 크다. (yfinance SI=F)</div>
        </div>
        <div class="card" onclick="toggle('d17')">
          <div class="card-label">금/은 비율</div>
          <div class="card-value">{format_val(data['GS_RATIO']['val'])}배</div>
          <div class="card-sub {data['GS_RATIO']['direction']}">{data['GS_RATIO']['sign']} {data['GS_RATIO']['change_str']}</div>
          <div class="badge {'b-grn' if data['GS_RATIO']['val'] is not None and data['GS_RATIO']['val'] > 80 else 'b-neu'}">은 상대적 가치</div>
          <div class="detail-panel" id="d17">30년차: 금/은 비율 80 이상 = 은 극단 저평가. 지금 비율이면 은이 적절 구간에 진입.</div>
        </div>
      </div>
    </div>

    <!-- SECTION: 경기 선행 -->
    <div class="sect" data-cat="macro">
      <div class="section-title">경기 선행지표 <span class="priority-tag p3">월 1회 확인</span></div>
      <div class="grid3">
        <div class="card" onclick="toggle('d18')">
          <div class="card-label">미국 CPI (YoY)</div>
          <div class="card-value">{format_val(data['US_CPI']['val'], "{:.2f}")}%</div>
          <div class="card-sub neu">최근 전년대비 성장</div>
          <div class="badge {'b-red' if data['US_CPI']['val'] is not None and data['US_CPI']['val'] > 3.0 else 'b-grn'}">인플레이션 모니터</div>
          <div class="detail-panel" id="d18">Core PCE가 핵심. 3% 이하여야 인하 논의 본격화.</div>
        </div>
        <div class="card" onclick="toggle('d20')">
          <div class="card-label">미국 실업률</div>
          <div class="card-value">{format_val(data['UNRATE']['val'], "{:.1f}")}%</div>
          <div class="card-sub neu">최근 공식 실업률</div>
          <div class="badge {'b-red' if data['UNRATE']['val'] is not None and data['UNRATE']['val'] > 4.5 else 'b-grn'}">경기 버팀목</div>
          <div class="detail-panel" id="d20">4.5%↑ 돌파 시 인하 압박. 현재는 긍정적.</div>
        </div>
        <div class="card" onclick="toggle('d21')">
          <div class="card-label">미국 신용 스프레드</div>
          <div class="card-value">{format_val(data['SPREAD']['val'], "{:.2f}")}%p</div>
          <div class="card-sub neu">하이일드 옵션조정</div>
          <div class="badge {'b-red' if data['SPREAD']['val'] is not None and data['SPREAD']['val'] > 4.0 else 'b-grn'}">금융위험 여부</div>
          <div class="detail-panel" id="d21">4%↑ 넘어가면 금융불안. 지금은 안정권.</div>
        </div>
      </div>
      <div class="grid2" style="margin-top:8px">
        <div class="card" onclick="toggle('d_oecd')">
          <div class="card-label">OECD 경기선행지수 (CLI) 🆕</div>
          <div class="card-value">{format_val(oecd_val, "{:.2f}")}</div>
          <div class="card-sub {oecd_dir}">{oecd_sign} {oecd_change_str} 전월비</div>
          <div class="badge {oecd_badge}">{oecd_badge_lbl}</div>
          <div class="detail-panel" id="d_oecd">OECD CLI: 100=장기 추세 기준. 100↑ 확장, 100↓ 수축. 하락 추세가 3개월 이상 지속되면 경기 둔화 선행 신호. ISM PMI 대체 지표로 키 없이 무료 조회.</div>
        </div>
        <div class="card" onclick="toggle('d_cfnai')">
          <div class="card-label">시카고연준 CFNAI (FRED)</div>
          <div class="card-value">{format_val(cfnai_val, "{:+.2f}")}</div>
          <div class="card-sub neu">0=평균 성장 기준</div>
          <div class="badge {cfnai_badge}">{cfnai_badge_lbl}</div>
          <div class="detail-panel" id="d_cfnai">CFNAI: 85개 경제 지표 종합. 양수=평균 이상 성장, 음수=평균 미달. -0.7 이하면 경기침체 진입 신호. 3개월 이동평균(CFNAI-MA3)이 더 안정적인 판단 기준.</div>
        </div>
      </div>
    </div>

    <!-- SECTION: 종합 신호등 -->
    <div class="sect" data-cat="signal">
      <div class="section-title">종합 신호등 — 지금 시장 어디 있나</div>
      <div class="master-card">
        <div class="grid2" style="gap:12px">
          <div>
            <div style="font-size:13px;font-weight:500;color:#222;margin-bottom:10px">현재 주요 위험 알림</div>
            <div class="signal-bar"><div class="dot dot-red"></div><div class="signal-text">환율 {format_val(data['KRW']['val'], "{:,.0f}")}원 수준 (모니터링 대상)</div></div>
            <div class="signal-bar"><div class="dot dot-red"></div><div class="signal-text">미 10년물 {format_val(data['US10Y']['val'], "{:.2f}")}% (압박 여부)</div></div>
            <div class="signal-bar"><div class="dot dot-red"></div><div class="signal-text">외국인 KOSPI 당월 {format_val(data['FOREIGN_BUY']['val'], "{:+.1f}")}조원 매매</div></div>
            <div class="signal-bar"><div class="dot dot-amb"></div><div class="signal-text">DXY {format_val(data['DXY']['val'], "{:.1f}")} 수준 글로벌 달러 지수</div></div>
          </div>
          <div>
            <div style="font-size:13px;font-weight:500;color:#222;margin-bottom:10px">현재 주요 버팀목</div>
            <div class="signal-bar"><div class="dot dot-grn"></div><div class="signal-text">실업률 {format_val(data['UNRATE']['val'], "{:.1f}")}% (비교적 안정)</div></div>
            <div class="signal-bar"><div class="dot dot-grn"></div><div class="signal-text">VIX 변동성 {format_val(data['VIX']['val'], "{:.1f}")} (안정권/경계구간)</div></div>
            <div class="signal-bar"><div class="dot dot-grn"></div><div class="signal-text">금값 ${format_val(data['GOLD']['val'], "{:,.0f}")} 방어력 확보</div></div>
            <div style="margin-top:12px;padding:10px;background:#f5f5f5;border-radius:6px">
              <div style="font-size:11px;font-weight:500;color:#666;margin-bottom:6px">30년차 결론</div>
              <div style="font-size:12px;color:#222;line-height:1.7">지금은 실시간 데이터 기반으로 판단. 외국인 복귀 확인이 핵심 과제. 리스크 대응력 강화.</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    </div>

    <script>
    function toggle(id){{
      const p=document.getElementById(id);
      if(!p) return;
      const isShow=p.classList.contains('show');
      document.querySelectorAll('.detail-panel').forEach(e=>e.classList.remove('show'));
      if(!isShow)p.classList.add('show');
    }}
    function switchTab(cat){{
      const event = window.event;
      if(event){{
        document.querySelectorAll('.tab').forEach(t=>t.classList.remove('on'));
        event.target.classList.add('on');
      }}
      document.querySelectorAll('.sect').forEach(s=>{{
        if(cat==='all'){{s.style.display='block';return}}
        const c=s.getAttribute('data-cat');
        s.style.display=(c===cat||cat==='signal'&&c==='signal')?'block':'none';
      }});
      if(cat==='signal'){{
        document.querySelectorAll('.sect').forEach(s=>s.style.display=s.getAttribute('data-cat')==='signal'?'block':'none');
      }}
    }}
    </script>
    """

    components.html(html_template, height=1350, scrolling=True)
