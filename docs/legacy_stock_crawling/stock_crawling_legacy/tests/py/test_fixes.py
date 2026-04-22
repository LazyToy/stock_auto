import requests
from bs4 import BeautifulSoup

def test_encoding():
    url = "https://finance.naver.com/item/main.naver?code=005930"
    res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    # Try decoding with euc-kr directly from content
    html = res.content.decode('euc-kr', 'replace')
    soup = BeautifulSoup(html, 'html.parser')
    articles = soup.select('.sub_section.news_section ul li a')
    print("--- News Encoding Test ---")
    for a in articles[:3]:
        print(a.text.strip())

def test_charts():
    print("\n--- Chart URL Test ---")
    urls = [
        "https://ssl.pstatic.net/imgfinance/chart/item/candle/day/005930.png",
        "https://ssl.pstatic.net/imgfinance/chart/item/candle/week/005930.png",
        "https://ssl.pstatic.net/imgfinance/chart/item/candle/month/005930.png",
        "https://ssl.pstatic.net/imgfinance/chart/item/candle/day/005930_end.png"
    ]
    for u in urls:
        r = requests.get(u)
        print(f"URL: {u} -> Status: {r.status_code}")

if __name__ == "__main__":
    test_encoding()
    test_charts()
