import urllib.request
from bs4 import BeautifulSoup

def test_news_encoding():
    print("\n--- Test 2: News Encoding ---")
    ticker = "005930"
    url = f"https://finance.naver.com/item/main.naver?code={ticker}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    res = urllib.request.urlopen(req)
    html = res.read().decode('euc-kr', 'replace')
    
    soup = BeautifulSoup(html, 'html.parser')
    a = soup.select_one('.sub_section.news_section ul li a')
    print(f"Title: {a.text.strip() if a else 'None'}")

if __name__ == "__main__":
    test_news_encoding()
