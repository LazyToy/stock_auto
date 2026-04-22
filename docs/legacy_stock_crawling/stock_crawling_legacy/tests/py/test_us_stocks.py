import FinanceDataReader as fdr
import requests
from bs4 import BeautifulSoup

def test_fdr_us():
    print("--- Test 1: FDR US Stocks ---")
    try:
        df_ndx = fdr.StockListing('NASDAQ')
        print("NASDAQ columns:", df_ndx.columns)
        aapl = df_ndx[df_ndx['Symbol'] == 'AAPL'].iloc[0]
        print("AAPL data:\n", aapl)
    except Exception as e:
        print("FDR US Error:", e)

def test_naver_us_news():
    print("\n--- Test 2: Naver US News ---")
    # Naver mobile API for US stocks:
    # https://api.stock.naver.com/stock/AAPL.O/news/list?pageSize=3&page=1
    url = "https://api.stock.naver.com/stock/AAPL.O/news/list?pageSize=3&page=1"
    res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    if res.status_code == 200:
        data = res.json()
        for item in data[:3]:
            print(f"Title: {item.get('title')}")
            print(f"Link: https://m.stock.naver.com/worldstock/stock/AAPL.O/news/{item.get('articleId')}/{item.get('officeId')}")
    else:
        print("Failed to fetch news API:", res.status_code)

def test_naver_us_charts():
    print("\n--- Test 3: Naver US Charts ---")
    # Let's guess the chart URL for US stocks
    urls = [
        "https://ssl.pstatic.net/imgfinance/chart/world/area/month3/AAPL.O.png",
        "https://ssl.pstatic.net/imgfinance/chart/world/candle/day/AAPL.O.png",
        "https://ssl.pstatic.net/imgfinance/chart/world/area/month3/AAPL.png"
    ]
    for u in urls:
        r = requests.get(u)
        print(f"URL: {u} -> Status: {r.status_code}")

if __name__ == "__main__":
    test_fdr_us()
    test_naver_us_news()
    test_naver_us_charts()
