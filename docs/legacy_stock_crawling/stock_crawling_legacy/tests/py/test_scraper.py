import urllib.request
from bs4 import BeautifulSoup

def test_naver_news():
    ticker_str = "005930"
    url = f"https://finance.naver.com/item/main.naver?code={ticker_str}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    html = urllib.request.urlopen(req).read().decode('euc-kr')
    soup = BeautifulSoup(html, 'html.parser')
    
    articles = soup.select('.sub_section.news_section ul li a')
    if not articles:
        articles = soup.select('.news_section a')
        
    print(f"검색된 뉴스 개수: {len(articles)}")
    for a in articles[:3]:
        title = a.text.strip()
        link = a.get('href', '')
        if link.startswith('/'):
            link = "https://finance.naver.com" + link
        print(f"제목: {title}\n링크: {link}")

if __name__ == "__main__":
    test_naver_news()
