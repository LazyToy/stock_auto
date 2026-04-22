"""이슈 #11: 외국인/기관 수급 파서 단위 테스트 (HTML fixture 사용)."""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# 네이버 frgn.naver 페이지 외국인/기관 순매매 테이블 HTML fixture
_HTML_FIXTURE = """
<html><body>
<table class="type2">
<thead>
<tr>
  <th>날짜</th>
  <th>외국인 순매매</th>
  <th>기관 순매매</th>
</tr>
</thead>
<tbody>
<tr>
  <td class="date">2026.04.17</td>
  <td class="num"><span class="tah">+15,234</span></td>
  <td class="num"><span class="tah">-8,450</span></td>
</tr>
<tr>
  <td class="date">2026.04.16</td>
  <td class="num"><span class="tah">-3,100</span></td>
  <td class="num"><span class="tah">-2,300</span></td>
</tr>
<tr>
  <td class="date">2026.04.15</td>
  <td class="num"><span class="tah">-5,200</span></td>
  <td class="num"><span class="tah">-1,000</span></td>
</tr>
<tr>
  <td class="date">2026.04.14</td>
  <td class="num"><span class="tah">-2,800</span></td>
  <td class="num"><span class="tah">+500</span></td>
</tr>
<tr>
  <td class="date">2026.04.11</td>
  <td class="num"><span class="tah">-1,500</span></td>
  <td class="num"><span class="tah">-3,200</span></td>
</tr>
<tr>
  <td class="date">2026.04.10</td>
  <td class="num"><span class="tah">-900</span></td>
  <td class="num"><span class="tah">-4,100</span></td>
</tr>
</tbody>
</table>
</body></html>
"""

_HTML_EMPTY = "<html><body><p>데이터 없음</p></body></html>"

_HTML_NAVER_LIVE_SHAPE = """
<html><body>
<table class="type2">
  <caption>거래원정보</caption>
  <tr><td class="title">미래에셋증권</td><td class="num">1,646,968</td></tr>
</table>
<table class="type2">
  <caption>외국인 기관 순매매 거래량</caption>
  <tr class="title1">
    <th rowspan="2">날짜</th><th rowspan="2">종가</th><th rowspan="2">전일비</th>
    <th rowspan="2">등락률</th><th rowspan="2">거래량</th>
    <th class="bg01">기관</th><th colspan="3" class="bg01 last">외국인</th>
  </tr>
  <tr>
    <td class="tc"><span class="tah p10 gray03">2026.04.17</span></td>
    <td class="num"><span class="tah p11">216,000</span></td>
    <td class="num"><span class="tah p11 nv01">1,500</span></td>
    <td class="num"><span class="tah p11 nv01">-0.69%</span></td>
    <td class="num"><span class="tah p11">15,537,867</span></td>
    <td class="num"><span class="tah p11 red01">+869,054</span></td>
    <td class="num"><span class="tah p11 nv01">-3,177,110</span></td>
    <td class="num"><span class="tah p11">2,876,898,857</span></td>
    <td class="num"><span class="tah p11">49.21%</span></td>
  </tr>
</table>
</body></html>
"""


def test_parse_returns_list_of_records():
    """파싱 결과가 리스트이고 각 항목에 date, foreign, institution 키가 있어야 한다."""
    from flow_fetcher import parse_foreign_institutional_flow
    records = parse_foreign_institutional_flow(_HTML_FIXTURE)
    assert isinstance(records, list)
    assert len(records) >= 1
    r = records[0]
    assert "date" in r
    assert "foreign" in r
    assert "institution" in r


def test_parse_first_record_values():
    """첫 번째 행의 날짜와 외국인/기관 순매매 값이 정확해야 한다."""
    from flow_fetcher import parse_foreign_institutional_flow
    records = parse_foreign_institutional_flow(_HTML_FIXTURE)
    first = records[0]
    assert first["date"] == "2026.04.17"
    assert first["foreign"] == 15234
    assert first["institution"] == -8450


def test_parse_empty_html_returns_empty():
    """데이터 없는 HTML → 빈 리스트 반환 (예외 없이)."""
    from flow_fetcher import parse_foreign_institutional_flow
    records = parse_foreign_institutional_flow(_HTML_EMPTY)
    assert records == []


def test_parse_none_html_returns_empty():
    """None HTML → 빈 리스트 반환."""
    from flow_fetcher import parse_foreign_institutional_flow
    records = parse_foreign_institutional_flow(None)
    assert records == []


def test_fetch_flow_uses_injectable():
    """http_get injectable 이 실제로 호출되는지 검증 (네트워크 없음)."""
    from flow_fetcher import fetch_flow
    called = []

    def fake_http_get(url: str) -> str:
        called.append(url)
        return _HTML_FIXTURE

    records = fetch_flow("005930", http_get=fake_http_get, sleep=lambda s: None)
    assert len(called) == 1
    assert "005930" in called[0]
    assert len(records) >= 1


def test_parse_second_record_negative_foreign():
    """두 번째 행 외국인 순매매가 음수로 정확히 파싱되어야 한다."""
    from flow_fetcher import parse_foreign_institutional_flow
    records = parse_foreign_institutional_flow(_HTML_FIXTURE)
    assert records[1]["foreign"] == -3100
    assert records[1]["institution"] == -2300


def test_parse_current_naver_table_shape():
    """현행 네이버 표 구조(td.tc 날짜, 기관 다음 외국인 순서)를 파싱한다."""
    from flow_fetcher import parse_foreign_institutional_flow
    records = parse_foreign_institutional_flow(_HTML_NAVER_LIVE_SHAPE)
    assert len(records) == 1
    assert records[0]["date"] == "2026.04.17"
    assert records[0]["institution"] == 869054
    assert records[0]["foreign"] == -3177110


if __name__ == "__main__":
    test_parse_returns_list_of_records()
    test_parse_first_record_values()
    test_parse_empty_html_returns_empty()
    test_parse_none_html_returns_empty()
    test_fetch_flow_uses_injectable()
    test_parse_second_record_negative_foreign()
    test_parse_current_naver_table_shape()
    print("[PASS] test_flow_fetcher 전체 통과")
