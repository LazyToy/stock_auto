"""main()의 DRY_RUN 블록에 MOCK=1 지원 추가 + em-dash ASCII 교체."""

with open("stock_scraper.py", "r", encoding="utf-8") as f:
    content = f.read()

OLD = '''    # DRY_RUN=1 이면 Google Sheets 연결 없이 지표 컬럼 stdout 검증만 수행
    if dry_run:
        print("[DRY RUN 모드] Google Sheets 쓰기 생략 \u2014 지표 컬럼 stdout 검증")
        try:
            df_krx = fdr.StockListing('KRX')
            df_today_raw = df_krx[df_krx['Market'].str.contains('KOSPI|KOSDAQ', na=False)].copy()
            today_str = resolve_trading_date(df_krx, today)
            df_today = df_today_raw.set_index('Code')
            df_today['\uc885\ubaa9\uba85'] = df_today['Name']
            df_today['\ub4f1\ub77d\ub960'] = pd.to_numeric(df_today['ChagesRatio'], errors='coerce').fillna(0)
            df_today['\uac70\ub798\ub300\uae08'] = pd.to_numeric(df_today['Amount'], errors='coerce').fillna(0)
            anchor_df = df_today_raw.reset_index() if 'Code' not in df_today_raw.columns else df_today_raw
            unit_multiplier = infer_volume_unit(anchor_df, _log_fn=print)
            if unit_multiplier != 1:
                df_today['\uac70\ub798\ub300\uae08'] = df_today['\uac70\ub798\ub300\uae08'] * unit_multiplier
            sector_map = SectorMapKR("sector_map_kr.json")
            sector_map.load(known_tickers=df_today.index.tolist())
            dry_run_indicator_check(df_today, sector_map)
        except Exception as e:
            print(f"[DRY RUN \uc624\ub958] {e}")'''

NEW = '''    # DRY_RUN=1 이면 Google Sheets 연결 없이 지표 컬럼 stdout 검증만 수행
    # MOCK=1 추가 시 FDR 네트워크 없이 합성 데이터로 검증 (오프라인 환경 포함)
    if dry_run:
        mock_mode = os.environ.get("MOCK", "0") == "1"
        print(f"[DRY RUN] Google Sheets skip - {'MOCK(no network)' if mock_mode else 'live FDR'}")
        try:
            if mock_mode:
                # 합성 DataFrame - 네트워크 불필요, Windows cp949 환경에서도 동작
                df_today = pd.DataFrame({
                    '\uc885\ubaa9\uba85': ['\ud14c\uc2a4\ud2b8\uc885\ubaa9A'],
                    '\ub4f1\ub77d\ub960': [18.0],
                    '\uac70\ub798\ub300\uae08': [80_000_000_000],
                }, index=["005930"])
                sector_map = SectorMapKR("sector_map_kr.json")
                sector_map.load(known_tickers=["005930"])
                dry_run_indicator_check(df_today, sector_map, mock_indicators=True)
            else:
                df_krx = fdr.StockListing('KRX')
                df_today_raw = df_krx[df_krx['Market'].str.contains('KOSPI|KOSDAQ', na=False)].copy()
                today_str = resolve_trading_date(df_krx, today)
                df_today = df_today_raw.set_index('Code')
                df_today['\uc885\ubaa9\uba85'] = df_today['Name']
                df_today['\ub4f1\ub77d\ub960'] = pd.to_numeric(df_today['ChagesRatio'], errors='coerce').fillna(0)
                df_today['\uac70\ub798\ub300\uae08'] = pd.to_numeric(df_today['Amount'], errors='coerce').fillna(0)
                anchor_df = df_today_raw.reset_index() if 'Code' not in df_today_raw.columns else df_today_raw
                unit_multiplier = infer_volume_unit(anchor_df, _log_fn=print)
                if unit_multiplier != 1:
                    df_today['\uac70\ub798\ub300\uae08'] = df_today['\uac70\ub798\ub300\uae08'] * unit_multiplier
                sector_map = SectorMapKR("sector_map_kr.json")
                sector_map.load(known_tickers=df_today.index.tolist())
                dry_run_indicator_check(df_today, sector_map)
        except Exception as e:
            print(f"[DRY RUN error] {e}")'''

if OLD in content:
    content = content.replace(OLD, NEW)
    with open("stock_scraper.py", "w", encoding="utf-8") as f:
        f.write(content)
    print("patch2 done - MOCK mode added")
else:
    print("ERROR: target block not found")
    # 디버그: 키워드로 위치 찾기
    idx = content.find("DRY RUN")
    print(f"  'DRY RUN' found at index: {idx}")
    print(f"  context: {content[idx:idx+100]!r}")
