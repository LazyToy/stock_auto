# PR-10 대시보드 Smart Money 탭 코드 리뷰 결과

대상: `docs/SMART_MONEY_MTF_PR_PLAN.md`의 `PR-10. 대시보드 Smart Money 탭`  
검증 기준: `docs/SMART_MONEY_MTF_PR_PLAN.md:657-719`  
검증 환경: `.\stock_auto\Scripts\python.exe`

검증 명령 결과:

| 명령 | 결과 | 근거 |
|---|---:|---|
| `.\stock_auto\Scripts\python.exe -m compileall dashboard\components\smart_money_tab.py tests\dashboard\test_smart_money_tab.py` | 통과 | 정적 검증 요구: `docs/SMART_MONEY_MTF_PR_PLAN.md:696` |
| `.\stock_auto\Scripts\python.exe -m black --check dashboard\components\smart_money_tab.py tests\dashboard\test_smart_money_tab.py` | 미확정, 120초 timeout | 정적 검증 요구: `docs/SMART_MONEY_MTF_PR_PLAN.md:697` |
| `.\stock_auto\Scripts\python.exe -m isort --check-only dashboard\components\smart_money_tab.py tests\dashboard\test_smart_money_tab.py` | 통과 | 정적 검증 요구: `docs/SMART_MONEY_MTF_PR_PLAN.md:698` |
| `.\stock_auto\Scripts\python.exe -m mypy dashboard\components\smart_money_tab.py` | 통과 | 정적 검증 요구: `docs/SMART_MONEY_MTF_PR_PLAN.md:699` |
| `.\stock_auto\Scripts\python.exe -m pytest tests\dashboard\test_smart_money_tab.py -q` | 통과, 6 passed | 동적 검증 요구: `docs/SMART_MONEY_MTF_PR_PLAN.md:703-709` |
| `.\stock_auto\Scripts\python.exe -m streamlit run dashboard/app.py --server.headless true --server.port 8506 --server.address 127.0.0.1` | HTTP 200 확인 | 브라우저 검증 실행 요구: `docs/SMART_MONEY_MTF_PR_PLAN.md:713-714`; 앱 연결: `dashboard/app.py:640-641` |

---

## 1. 명세 준수 검증

| # | 요구사항 | 구현 위치 (파일:함수:라인) | 충족 여부 | 미충족 시 이유 |
|---:|---|---|---|---|
| 1 | Streamlit Smart Money 탭 추가 | `dashboard/components/smart_money_tab.py:205`, `dashboard/app.py:133-138`, `dashboard/app.py:640-641` | 충족 | 문제 없음 |
| 2 | 신규 파일 `dashboard/components/smart_money_tab.py` | `dashboard/components/smart_money_tab.py:1` | 충족 | 문제 없음 |
| 3 | 신규 테스트 `tests/dashboard/test_smart_money_tab.py` | `tests/dashboard/test_smart_money_tab.py:1` | 충족 | 문제 없음 |
| 4 | `dashboard/app.py`에 새 탭 연결 | `dashboard/app.py:102`, `dashboard/app.py:133-138`, `dashboard/app.py:640-641` | 충족 | 문제 없음 |
| 5 | 여러 종목 입력: comma-separated text area | `dashboard/components/smart_money_tab.py:211-217`, `dashboard/components/smart_money_tab.py:61-74` | 충족 | 문제 없음 |
| 6 | 시장 선택: KR/US | `dashboard/components/smart_money_tab.py:218-219` | 충족 | 문제 없음 |
| 7 | 거래소 선택: US일 때 NASD/NYSE/AMEX | `dashboard/components/smart_money_tab.py:220-229` | 부분 충족 | `US_EXCHANGES`는 `NASD/NYSE/AMEX`로 구현됐지만, KR 선택 시에도 거래소 selectbox가 노출되고 이후 `KRX`로 덮어쓴다. 요구 근거: `docs/SMART_MONEY_MTF_PR_PLAN.md:670-671` |
| 8 | 분석 실행 버튼 | `dashboard/components/smart_money_tab.py:231-242` | 충족 | 문제 없음 |
| 9 | 결과 표: `symbol` | `dashboard/components/smart_money_tab.py:160-178`, `dashboard/components/smart_money_tab.py:167` | 충족 | 문제 없음 |
| 10 | 결과 표: `signal` | `dashboard/components/smart_money_tab.py:160-178`, `dashboard/components/smart_money_tab.py:168` | 충족 | 문제 없음 |
| 11 | 결과 표: `confidence` | `dashboard/components/smart_money_tab.py:160-178`, `dashboard/components/smart_money_tab.py:169`, `dashboard/components/smart_money_tab.py:328-329` | 충족 | 문제 없음 |
| 12 | 결과 표: `daily structure` | `dashboard/components/smart_money_tab.py:170`, `dashboard/components/smart_money_tab.py:332-336` | 충족 | 문제 없음 |
| 13 | 결과 표: `1h setup` | `dashboard/components/smart_money_tab.py:171`, `dashboard/components/smart_money_tab.py:339-346` | 충족 | 문제 없음 |
| 14 | 결과 표: `5m trigger` | `dashboard/components/smart_money_tab.py:172`, `dashboard/components/smart_money_tab.py:349-359` | 충족 | 문제 없음 |
| 15 | 결과 표: `entry zone` | `dashboard/components/smart_money_tab.py:173`, `dashboard/components/smart_money_tab.py:362-366` | 충족 | 문제 없음 |
| 16 | 결과 표: `invalidation` | `dashboard/components/smart_money_tab.py:174`, `dashboard/components/smart_money_tab.py:369-372` | 충족 | 문제 없음 |
| 17 | 결과 표: `주요 reason` | `dashboard/components/smart_money_tab.py:175`, `dashboard/components/smart_money_tab.py:375-381` | 충족 | 문제 없음 |
| 18 | 선택 종목 상세: timeframe tabs 5m/1h/1d | `dashboard/components/smart_money_tab.py:22-27`, `dashboard/components/smart_money_tab.py:280-283` | 충족 | 문제 없음 |
| 19 | 선택 종목 상세: annotated chart | `dashboard/components/smart_money_tab.py:191-202`, `dashboard/components/smart_money_tab.py:293-295`, `src/analysis/smart_money/chart.py:45-61` | 충족 | 문제 없음 |
| 20 | 선택 종목 상세: pattern summary | `dashboard/components/smart_money_tab.py:296`, `dashboard/components/smart_money_tab.py:299-316` | 충족 | 문제 없음 |
| 21 | 선택 종목 상세: warnings | `dashboard/components/smart_money_tab.py:261-266`, `dashboard/components/smart_money_tab.py:315-316` | 충족 | 문제 없음 |
| 22 | 실패한 timeframe만 warning으로 표시 | `dashboard/components/smart_money_tab.py:181-188`, `dashboard/components/smart_money_tab.py:319-325`, `dashboard/components/smart_money_tab.py:261-266` | 충족 | 문제 없음 |
| 23 | 전체 종목 실패 시 error 표시 | `dashboard/components/smart_money_tab.py:252-255`, `dashboard/components/smart_money_tab.py:268-269` | 충족 | 문제 없음 |
| 24 | 일부 종목 성공 시 성공 결과 계속 표시 | `dashboard/components/smart_money_tab.py:252-259`, `dashboard/components/smart_money_tab.py:271-277` | 충족 | 문제 없음 |
| 25 | 자동주문 버튼 미구현 | `dashboard/components/smart_money_tab.py:205-249` | 충족 | 해당 렌더 함수에 주문 실행 버튼 또는 주문 API 호출 없음 |
| 26 | test double로 여러 종목 입력 파싱 검증 | `tests/dashboard/test_smart_money_tab.py:42-45` | 충족 | 문제 없음 |
| 27 | test double로 빈 종목 입력 시 API 호출 없음 검증 | `tests/dashboard/test_smart_money_tab.py:48-55` | 충족 | 문제 없음 |
| 28 | test double로 결과 표 컬럼 생성 검증 | `tests/dashboard/test_smart_money_tab.py:58-97` | 충족 | 문제 없음 |
| 29 | test double로 실패 warning 포함 검증 | `tests/dashboard/test_smart_money_tab.py:100-112` | 충족 | 문제 없음 |
| 30 | test double로 chart helper 인자 일치 검증 | `tests/dashboard/test_smart_money_tab.py:115-137` | 충족 | 문제 없음 |
| 31 | Playwright로 탭 표시, 결과 표, desktop/mobile 겹침, nonblank chart 검증 | `docs/SMART_MONEY_MTF_PR_PLAN.md:711-719`, `tests/dashboard/test_smart_money_tab.py:140-145` | 미충족 | 테스트는 app wiring 문자열만 확인한다. Playwright 자동 검증 또는 결과 표/viewport/chart nonblank 검증 코드가 없다. |

---

## 2. 논리 결함 분석

### 필수 체크리스트

| 검증 항목 | 판정 | 근거 |
|---|---|---|
| Null/None/빈 입력 | 부분 문제 | `parse_symbol_input`은 문자열이 아니면 `ValueError`를 발생시키고 빈 문자열은 빈 리스트를 반환한다: `dashboard/components/smart_money_tab.py:61-74`. `run_smart_money_batch`는 빈 리스트면 fetcher를 호출하지 않는다: `dashboard/components/smart_money_tab.py:86-90`. `build_result_rows(None)` 같은 시그니처 밖 입력은 별도 방어가 없다: `dashboard/components/smart_money_tab.py:160-178`. |
| 경계값 | 문제 없음 | 빈 종목 입력 경계는 `run_smart_money_batch`에서 `[]`로 종료한다: `dashboard/components/smart_money_tab.py:86-88`; 테스트 근거: `tests/dashboard/test_smart_money_tab.py:48-55`. |
| 타입 불일치 | 문제 없음 | fetcher protocol은 `fetch_symbol(symbol, market, exchange)`이고 호출부도 동일 인자를 사용한다: `dashboard/components/smart_money_tab.py:31-37`, `dashboard/components/smart_money_tab.py:115-117`. figure builder 계약은 `(DataFrame, TimeframePatternReport, SmartMoneySignal | None)`이고 호출부도 동일하다: `dashboard/components/smart_money_tab.py:41`, `dashboard/components/smart_money_tab.py:198-202`. |
| 예외 처리 누락 | 부분 문제 | 데이터 수집과 패턴 분석은 예외를 결과 객체로 격리한다: `dashboard/components/smart_money_tab.py:115-147`. 차트 생성은 `build_selected_chart`와 `_render_detail`에서 예외를 처리하지 않는다: `dashboard/components/smart_money_tab.py:191-202`, `dashboard/components/smart_money_tab.py:293-296`. |
| 상태 변이 | 문제 없음 | `MultiTimeframeDataset.successful_ohlcv`가 DataFrame copy를 반환한다: `src/analysis/timeframes.py:97-103`. PR-10 결과 생성은 새 row dict를 만든다: `dashboard/components/smart_money_tab.py:160-178`. |
| 동시성/순서 의존 | 문제 없음 | batch는 입력 순서대로 순차 실행하고 결과도 append 순서로 유지한다: `dashboard/components/smart_money_tab.py:90-103`. |
| 리소스 누수 | 문제 없음 | PR-10 컴포넌트는 파일/소켓을 직접 열지 않는다: `dashboard/components/smart_money_tab.py:1-391`. 외부 수집은 `MultiTimeframeFetcher`에 위임한다: `dashboard/components/smart_money_tab.py:90`, `src/analysis/timeframes.py:129-170`. |
| 하드코딩 | 부분 문제 | `US_EXCHANGES`, `TIMEFRAME_ORDER`, UI 기본값과 높이는 상수/리터럴로 존재한다: `dashboard/components/smart_money_tab.py:22-28`, `dashboard/components/smart_money_tab.py:211-225`. |

### 발견 결함

[Minor] `dashboard/components/smart_money_tab.py:220-229` — KR 시장 선택 시에도 US 거래소 selectbox가 표시된다.  
  현재 동작: `market` selectbox와 무관하게 `NASD/NYSE/AMEX` 거래소 selectbox를 렌더링한 뒤, KR이면 내부 값만 `KRX`로 덮어쓴다. 근거: `dashboard/components/smart_money_tab.py:218-229`.  
  예상 동작: 거래소 선택은 US일 때 `NASD/NYSE/AMEX`로 제공되어야 한다. 근거: `docs/SMART_MONEY_MTF_PR_PLAN.md:670-671`.  
  수정 방안: `market == "US"`일 때만 거래소 selectbox를 렌더링하고, KR일 때는 `"KRX"`를 표시 전용 또는 숨김 값으로 처리한다.

[Minor] `dashboard/components/smart_money_tab.py:293-296` — 차트 생성 실패가 UI 경고로 격리되지 않는다.  
  현재 동작: `build_selected_chart`가 `build_smart_money_figure` 예외를 그대로 전파하고 `_render_detail`에서 try-except가 없다. 근거: `dashboard/components/smart_money_tab.py:191-202`, `dashboard/components/smart_money_tab.py:293-296`; chart helper는 입력 오류 시 `ValueError`를 발생시킨다: `src/analysis/smart_money/chart.py:45-68`.  
  예상 동작: 대시보드 UX 요구는 실패를 warning/error로 표시하고 성공 결과를 계속 보여주는 흐름이다. 근거: `docs/SMART_MONEY_MTF_PR_PLAN.md:688-691`.  
  수정 방안: `_render_detail`에서 `build_selected_chart` 호출을 try-except로 감싸고, 해당 timeframe 차트 실패만 `st_api.warning`으로 표시한다.

---

## 3. 테스트 커버리지 갭 분석

### 3-1. 테스트 인벤토리

| 테스트 파일 | 테스트 메서드 | 검증 대상 함수 | 검증 내용 |
|---|---|---|---|
| `tests/dashboard/test_smart_money_tab.py` | `test_parse_symbol_input_splits_commas_and_removes_blank_values` | `parse_symbol_input` | 쉼표/줄바꿈/공백/중복 입력을 리스트로 정규화한다: `tests/dashboard/test_smart_money_tab.py:42-45`. |
| `tests/dashboard/test_smart_money_tab.py` | `test_run_smart_money_batch_skips_fetcher_for_empty_symbol_input` | `run_smart_money_batch` | 빈 입력이면 fetcher를 호출하지 않고 `[]`를 반환한다: `tests/dashboard/test_smart_money_tab.py:48-55`. |
| `tests/dashboard/test_smart_money_tab.py` | `test_build_result_rows_contains_required_dashboard_columns` | `build_result_rows` | 성공 결과 row의 필수 컬럼과 포맷을 검증한다: `tests/dashboard/test_smart_money_tab.py:58-97`. |
| `tests/dashboard/test_smart_money_tab.py` | `test_failed_timeframe_warning_is_preserved_in_analysis_result` | `collect_warnings` | timeframe 오류와 signal warning을 함께 반환한다: `tests/dashboard/test_smart_money_tab.py:100-112`. |
| `tests/dashboard/test_smart_money_tab.py` | `test_build_selected_chart_passes_matching_frame_report_and_signal` | `build_selected_chart` | 선택 timeframe의 frame/report/signal을 figure builder로 전달한다: `tests/dashboard/test_smart_money_tab.py:115-137`. |
| `tests/dashboard/test_smart_money_tab.py` | `test_dashboard_app_wires_smart_money_tab` | `dashboard/app.py` wiring | import, 탭명, 렌더 호출 문자열을 확인한다: `tests/dashboard/test_smart_money_tab.py:140-145`. |

### 3-2. 커버리지 갭

| 프로덕션 함수 | 정상 케이스 테스트 | 에러 케이스 테스트 | 경계값 테스트 | 누락된 테스트 시나리오 |
|---|---|---|---|---|
| `SmartMoneySymbolAnalysis.is_success` | 없음 | 없음 | 없음 | `signal 있음/error 없음`, `signal 있음/error 있음`, `signal 없음/error 없음` 조합 검증 누락: `dashboard/components/smart_money_tab.py:55-58`. |
| `parse_symbol_input` | 있음: `tests/dashboard/test_smart_money_tab.py:42-45` | 없음 | 부분: 빈 입력은 `run_smart_money_batch` 경유 검증 `tests/dashboard/test_smart_money_tab.py:48-55` | 비문자 입력 `ValueError`, 탭/소문자/중복 순서 유지 직접 테스트 누락: `dashboard/components/smart_money_tab.py:61-74`. |
| `run_smart_money_batch` | 없음 | 없음 | 있음: `tests/dashboard/test_smart_money_tab.py:48-55` | 여러 종목이 fetcher에 순차 전달되는지, 종목별 실패가 격리되는지 검증 누락: `dashboard/components/smart_money_tab.py:90-103`. |
| `analyze_smart_money_symbol` | 없음 | 없음 | 없음 | fetcher 실패, 모든 timeframe 실패, 패턴 분석 실패, 일부 timeframe 실패 후 signal 생성 검증 누락: `dashboard/components/smart_money_tab.py:106-157`. |
| `build_result_rows` | 있음: `tests/dashboard/test_smart_money_tab.py:58-97` | 없음 | 없음 | 실패 row(`signal is None`, `error 있음`), 일부 report 누락, entry/invalidation 없음 포맷 검증 누락: `dashboard/components/smart_money_tab.py:160-178`. |
| `collect_warnings` | 있음: `tests/dashboard/test_smart_money_tab.py:100-112` | 해당 없음 | 없음 | warning 중복 제거, warning 없음, result.error만 있는 경우 검증 누락: `dashboard/components/smart_money_tab.py:181-188`, `dashboard/components/smart_money_tab.py:384-391`. |
| `build_selected_chart` | 있음: `tests/dashboard/test_smart_money_tab.py:115-137` | 없음 | 없음 | frame 또는 report 누락 시 `None` 반환 검증 누락: `dashboard/components/smart_money_tab.py:198-202`. |
| `render_smart_money_tab` | 없음 | 없음 | 없음 | fake `st_api`로 빈 입력 warning, session_state 저장, KR/US 거래소 UI, 결과 렌더 호출 검증 누락: `dashboard/components/smart_money_tab.py:205-249`. |
| `_render_results` | 없음 | 없음 | 없음 | 전체 실패 error, 일부 성공 warning, 성공 상세 selectbox 호출 검증 누락: `dashboard/components/smart_money_tab.py:252-277`. |
| `_render_detail` | 없음 | 없음 | 없음 | 5m/1h/1d tab 생성, missing timeframe warning, chart 예외 처리 경로 검증 누락: `dashboard/components/smart_money_tab.py:280-296`. |

### 3-3. 테스트 품질

| 검증 항목 | 판정 | 근거 |
|---|---|---|
| 각 테스트가 하나의 동작만 검증하는가 | 부분 문제 | `test_build_result_rows_contains_required_dashboard_columns`는 컬럼 존재와 모든 포맷을 하나의 완전 dict equality로 검증한다: `tests/dashboard/test_smart_money_tab.py:83-97`. |
| 테스트 간 의존성이 없는가 | 문제 없음 | 모든 테스트가 로컬 fixture 함수 `_report`, `_frame` 또는 함수 내부 fake를 사용하고 공유 mutable 전역 상태가 없다: `tests/dashboard/test_smart_money_tab.py:11-39`, `tests/dashboard/test_smart_money_tab.py:51-55`, `tests/dashboard/test_smart_money_tab.py:118-125`. |
| Mock/Stub이 프로덕션 동작을 정확히 모사하는가 | 부분 문제 | FakeFetcher는 빈 입력에서 호출 금지만 검증하며 실제 `MultiTimeframeDataset` 반환 계약을 모사하지 않는다: `tests/dashboard/test_smart_money_tab.py:51-55`; 실제 protocol 근거: `dashboard/components/smart_money_tab.py:31-37`. |
| Assertion이 구체적인가 | 문제 없음 | 리스트/딕셔너리 완전 일치와 호출 인자 완전 일치를 사용한다: `tests/dashboard/test_smart_money_tab.py:45`, `tests/dashboard/test_smart_money_tab.py:85-97`, `tests/dashboard/test_smart_money_tab.py:136-137`. |
| 테스트 데이터가 deterministic한가 | 문제 없음 | `_frame`은 고정 값과 고정 날짜 범위를 사용한다: `tests/dashboard/test_smart_money_tab.py:29-39`. |

---

## 4. 데이터 흐름 정합성

### 4-1. 데이터 흐름도

```
[Streamlit text_area 입력]
  → parse_symbol_input(value)
  → list[str] symbols
  → run_smart_money_batch(symbol_text, market, exchange)
  → MultiTimeframeFetcher.fetch_symbol(symbol, market, exchange)
  → MultiTimeframeDataset
  → MultiTimeframeDataset.successful_ohlcv()
  → dict[str, pd.DataFrame]
  → analyze_multi_timeframe_patterns(frames)
  → dict[str, TimeframePatternReport]
  → combine_multi_timeframe_signals(reports, SignalConfig)
  → SmartMoneySignal
  → SmartMoneySymbolAnalysis
  → build_result_rows(results)
  → pd.DataFrame 결과 표
```

```
[선택 종목 + timeframe]
  → _render_detail(result)
  → build_selected_chart(result, timeframe)
  → build_smart_money_figure(frame, report, signal)
  → plotly.graph_objects.Figure
  → st.plotly_chart(...)
```

근거: 입력 UI `dashboard/components/smart_money_tab.py:211-242`, batch 흐름 `dashboard/components/smart_money_tab.py:77-103`, 단일 분석 흐름 `dashboard/components/smart_money_tab.py:106-157`, dataset copy 반환 `src/analysis/timeframes.py:97-103`, report 생성 `src/analysis/smart_money/report.py:157-167`, signal 생성 `src/analysis/smart_money/signal.py:101-115`, chart 생성 `dashboard/components/smart_money_tab.py:191-202`, `src/analysis/smart_money/chart.py:45-61`.

### 4-2. 정합성 검증

| 체크포인트 | 판정 | 근거 |
|---|---|---|
| 각 함수의 출력 타입이 다음 함수의 입력 타입과 일치하는가 | 문제 없음 | `successful_ohlcv()`는 `dict[str, pd.DataFrame]`를 반환하고 `analyze_multi_timeframe_patterns`는 `Mapping[str, pd.DataFrame]`를 받는다: `src/analysis/timeframes.py:97-103`, `src/analysis/smart_money/report.py:157-167`. `combine_multi_timeframe_signals`는 report mapping과 config를 받아 `SmartMoneySignal`을 반환한다: `src/analysis/smart_money/signal.py:101-115`, `src/analysis/smart_money/models.py:257-270`. |
| 데이터 변환 과정에서 정보 손실이 있는가 | 문제 없음 | `SmartMoneySymbolAnalysis`는 `frames`, `reports`, `signal`, `timeframe_errors`, `error`를 보관한다: `dashboard/components/smart_money_tab.py:44-53`, `dashboard/components/smart_money_tab.py:149-157`. |
| 필수 필드가 중간에 누락될 수 있는가 | 부분 문제 | 실패 row는 `signal`이 없으면 `"ERROR"`와 `0.0%`로 표시한다: `dashboard/components/smart_money_tab.py:164-175`. 오류 원문은 `주요 reason`에 들어가지만 confidence 0.0%가 실제 신뢰도처럼 보일 수 있다: `dashboard/components/smart_money_tab.py:169`, `dashboard/components/smart_money_tab.py:375-381`. |
| 에러 발생 시 호출자에게 적절한 정보가 전달되는가 | 부분 문제 | 수집/분석 예외는 `SmartMoneySymbolAnalysis.error`로 전달된다: `dashboard/components/smart_money_tab.py:115-147`. 차트 helper 예외는 `_render_detail`에서 사용자 warning으로 변환되지 않는다: `dashboard/components/smart_money_tab.py:293-296`. |

---

## 5. 테스트-프로덕션 괴리 분석

| 검증 항목 | 판정 | 근거 |
|---|---|---|
| 테스트가 프로덕션 함수를 직접 호출하는가, 별도 구현을 만들었는가 | 부분 문제 | `parse_symbol_input`, `run_smart_money_batch`, `build_result_rows`, `collect_warnings`, `build_selected_chart`는 직접 호출한다: `tests/dashboard/test_smart_money_tab.py:42-137`. Streamlit 렌더는 직접 호출하지 않고 app.py 문자열만 확인한다: `tests/dashboard/test_smart_money_tab.py:140-145`. |
| Mock이 실제 의존성의 인터페이스와 일치하는가 | 부분 문제 | FakeFetcher의 `fetch_symbol` 시그니처는 protocol과 일치한다: `tests/dashboard/test_smart_money_tab.py:51-52`, `dashboard/components/smart_money_tab.py:31-37`. 다만 실제 반환 타입 `MultiTimeframeDataset`를 반환하는 성공 경로 mock은 없다: `dashboard/components/smart_money_tab.py:115-126`. |
| 테스트 픽스처가 실제 데이터 형식과 일치하는가 | 문제 없음 | `_frame`은 `open/high/low/close/volume`과 `DatetimeIndex`를 가진다: `tests/dashboard/test_smart_money_tab.py:29-39`. chart helper 계약도 OHLC와 datetime index를 요구한다: `src/analysis/smart_money/chart.py:50-61`. |
| 테스트에서만 통과하고 실제 환경에서 실패할 수 있는 경로가 있는가 | 부분 문제 | 렌더 테스트는 문자열 기반 wiring만 확인하므로 실제 Streamlit `st_api.session_state`, selectbox, button, plotly 렌더 동작을 검증하지 않는다: `dashboard/components/smart_money_tab.py:205-249`, `tests/dashboard/test_smart_money_tab.py:140-145`. |

별도 구현 존재 여부: 프로덕션 로직을 재구현한 별도 구현은 발견되지 않았다. 테스트 helper `_report`, `_frame`은 데이터 fixture이며 프로덕션 알고리즘 대체 구현이 아니다: `tests/dashboard/test_smart_money_tab.py:11-39`.

---

## 6. 확장성 및 유지보수 리스크

| 검증 항목 | 판정 | 근거 |
|---|---|---|
| 단일 책임 원칙: 하나의 함수/클래스가 여러 역할을 하는가 | 부분 문제 | `render_smart_money_tab`은 입력 UI, session_state 업데이트, batch 실행, 결과 렌더 진입을 함께 수행한다: `dashboard/components/smart_money_tab.py:205-249`. 결과/상세 렌더는 별도 함수로 분리되어 있다: `dashboard/components/smart_money_tab.py:252-316`. |
| 결합도: 모듈 간 불필요한 직접 의존이 있는가 | 문제 없음 | PR-10 컴포넌트는 Smart Money public API와 timeframe fetcher를 직접 사용한다: `dashboard/components/smart_money_tab.py:12-20`. 작업 목표가 패턴 엔진 결과를 UI에 연결하는 것이므로 직접 의존은 요구 범위 안이다: `docs/SMART_MONEY_MTF_PR_PLAN.md:659-660`. |
| 설정값: 매직 넘버가 상수나 설정으로 분리되었는가 | 부분 문제 | timeframe order와 US exchange는 상수다: `dashboard/components/smart_money_tab.py:22-28`. text area 기본값/높이와 column 비율은 함수 내부 리터럴이다: `dashboard/components/smart_money_tab.py:209-215`. |
| 에러 메시지: 디버깅에 충분한 정보를 제공하는가 | 부분 문제 | 수집/분석 실패 메시지는 예외 문자열을 포함한다: `dashboard/components/smart_money_tab.py:117-147`. 차트 생성 실패는 사용자 메시지로 변환되지 않는다: `dashboard/components/smart_money_tab.py:293-296`. |
| 문서화: public API에 docstring이 있는가, 있다면 정확한가 | 문제 없음 | protocol, dataclass property, public 함수에 docstring이 있다: `dashboard/components/smart_money_tab.py:31-38`, `dashboard/components/smart_money_tab.py:55-62`, `dashboard/components/smart_money_tab.py:77-85`, `dashboard/components/smart_money_tab.py:106-114`, `dashboard/components/smart_money_tab.py:160-197`, `dashboard/components/smart_money_tab.py:205-206`. |
| 후속 작업과의 호환: 현재 인터페이스가 확장 시 breaking change를 유발하는가 | 부분 문제 | `render_smart_money_tab`은 fetcher/config/figure_builder를 주입받지 않아 fixture 기반 브라우저 검증이나 후속 테스트 확장이 어렵다: `dashboard/components/smart_money_tab.py:205`, `dashboard/components/smart_money_tab.py:237-242`; 브라우저 검증 요구 근거: `docs/SMART_MONEY_MTF_PR_PLAN.md:711-719`. |

---

## 7. 최종 판정

### 7-1. 영역별 등급

| 영역 | 등급 | 핵심 근거 |
|---|---:|---|
| 명세 준수 | B | 주요 UI/데이터 흐름은 구현됐지만 KR 선택 시 US 거래소 selectbox 노출이 명세와 다르다: `dashboard/components/smart_money_tab.py:220-229`, `docs/SMART_MONEY_MTF_PR_PLAN.md:670-671`. |
| 논리 건전성 | B | 수집/분석 실패 격리는 구현됐지만 차트 생성 실패는 UI warning으로 격리되지 않는다: `dashboard/components/smart_money_tab.py:115-147`, `dashboard/components/smart_money_tab.py:293-296`. |
| 테스트 커버리지 | C | 명세의 test double 항목은 일부 충족하지만 `analyze_smart_money_symbol`, `render_smart_money_tab`, 실패/경계 경로 테스트가 없다: `dashboard/components/smart_money_tab.py:106-157`, `dashboard/components/smart_money_tab.py:205-249`, `tests/dashboard/test_smart_money_tab.py:42-145`. |
| 데이터 정합성 | B | 핵심 타입 연결은 맞지만 차트 예외와 실패 row confidence 표현에 오해 가능성이 있다: `dashboard/components/smart_money_tab.py:169`, `dashboard/components/smart_money_tab.py:293-296`. |
| 테스트-프로덕션 일치 | C | 순수 함수는 직접 검증하지만 실제 Streamlit 렌더 경로는 문자열 wiring만 확인한다: `tests/dashboard/test_smart_money_tab.py:140-145`, `dashboard/components/smart_money_tab.py:205-249`. |
| 확장성/유지보수 | B | 구성 분리는 되어 있으나 render 함수에 fetcher/config 주입점이 없어 fixture/Playwright 검증 확장이 어렵다: `dashboard/components/smart_money_tab.py:205`, `dashboard/components/smart_money_tab.py:237-242`. |
| **종합** | **C** | 기능은 동작 가능한 수준이나 UI 명세 차이와 렌더/실분석/브라우저 검증 공백이 남아 있다: `docs/SMART_MONEY_MTF_PR_PLAN.md:670-719`, `tests/dashboard/test_smart_money_tab.py:140-145`. |

### 7-2. 즉시 수정 필요 항목 TOP 5

| 순위 | 심각도 | 위치 (파일:라인) | 문제 요약 | 수정 방안 |
|---:|---|---|---|---|
| 1 | Minor | `dashboard/components/smart_money_tab.py:220-229` | KR 시장에서도 US 거래소 selectbox가 표시된다. | `market == "US"`일 때만 거래소 selectbox를 렌더링하고 KR은 `"KRX"` 고정값으로 처리한다. |
| 2 | Minor | `dashboard/components/smart_money_tab.py:293-296` | 차트 helper 예외가 Streamlit warning으로 격리되지 않는다. | `_render_detail`에서 chart 생성 예외를 잡아 해당 timeframe warning으로 표시한다. |
| 3 | Info | `dashboard/components/smart_money_tab.py:205-242` | `render_smart_money_tab`에 fetcher/config 주입점이 없어 mock/fixture 브라우저 검증이 어렵다. | 선택 인자로 fetcher/config 또는 batch runner를 주입할 수 있게 확장한다. |
| 4 | Info | `tests/dashboard/test_smart_money_tab.py:140-145` | 실제 Streamlit 렌더 경로와 viewport/chart nonblank 검증이 없다. | fake `st_api` 단위 테스트와 Playwright screenshot/nonblank 검증을 추가한다. |
| 5 | Info | `docs/SMART_MONEY_MTF_PR_PLAN.md:697` | `black --check` 검증이 120초 timeout으로 확정되지 않았다. | black 실행 지연 원인을 확인하고 동일 명령을 재검증한다. |

### 7-3. 권장 후속 조치

1. `render_smart_money_tab`의 KR/US 거래소 UI 분기를 수정하고, fake `st_api` 테스트로 KR 선택 시 `NASD/NYSE/AMEX`가 노출되지 않는지 검증한다.
2. `analyze_smart_money_symbol`의 fetcher 실패, 전체 timeframe 실패, 일부 timeframe 실패, 패턴 분석 실패 테스트를 추가한다.
3. fixture 주입 가능한 렌더 경로를 만든 뒤 Playwright로 Smart Money 탭, 결과 표, desktop/mobile 텍스트 겹침, chart nonblank를 검증한다.
