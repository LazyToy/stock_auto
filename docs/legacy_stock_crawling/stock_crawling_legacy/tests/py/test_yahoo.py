import requests

def test_yahoo_screener():
    url = "https://query2.finance.yahoo.com/v1/finance/screener/predefined/saved"
    params = {
        "formatted": "false",
        "lang": "en-US",
        "region": "US",
        "scrIds": "day_gainers",
        "count": 100
    }
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    res = requests.get(url, params=params, headers=headers)
    if res.status_code == 200:
        data = res.json()
        quotes = data['finance']['result'][0]['quotes']
        for q in quotes[:3]:
            print(q['symbol'], q.get('regularMarketChangePercent'), q.get('regularMarketVolume'))
    else:
        print("Failed:", res.status_code)

test_yahoo_screener()
