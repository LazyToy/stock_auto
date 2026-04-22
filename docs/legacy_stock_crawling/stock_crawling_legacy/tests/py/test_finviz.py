import urllib.request
from bs4 import BeautifulSoup
import re

def scrape_finviz(filters):
    url = f"https://finviz.com/screener.ashx?v=111&f={filters}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    res = urllib.request.urlopen(req)
    html = res.read().decode('utf-8')
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find all rows in the screener table
    # The table has class 'screener_table' or similar. Let's just find links to quote.ashx
    tickers = []
    for a in soup.find_all('a', href=re.compile(r'^quote\.ashx\?t=')):
        ticker = a.text.strip()
        if ticker and ticker not in tickers:
            tickers.append(ticker)
    return tickers

print(scrape_finviz("sh_curvol_o1000,ta_perf_d5o"))
