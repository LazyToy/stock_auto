import requests
from bs4 import BeautifulSoup

url = 'https://finance.naver.com/item/news_news.naver?code=005930'
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
res = requests.get(url, headers=headers)
res.encoding = 'euc-kr'
soup = BeautifulSoup(res.text, 'html.parser')
articles = soup.select('.title a')
for a in articles[:3]:
    print(a.text.strip(), a.get('href'))
