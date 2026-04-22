import requests

def get_us_stocks():
    url = "https://scanner.tradingview.com/america/scan"
    payload = {
        "filter": [
            {"left": "type", "operation": "in_range", "right": ["stock", "dr"]},
            {"left": "exchange", "operation": "in_range", "right": ["AMEX", "NASDAQ", "NYSE"]},
            {"left": "Value.Traded", "operation": "greater", "right": 100000000},
            {"left": "change", "operation": "greater", "right": 5}
        ],
        "options": {"lang": "en"},
        "markets": ["america"],
        "symbols": {"query": {"types": []}, "tickers": []},
        "columns": ["name", "description", "close", "change", "Value.Traded", "high", "low", "market_cap_basic", "sector"],
        "sort": {"sortBy": "change", "sortOrder": "desc"},
        "range": [0, 200]
    }
    
    res = requests.post(url, json=payload)
    if res.status_code == 200:
        data = res.json()
        for d in data.get('data', [])[:5]:
            print(d['d'])
    else:
        print("Error:", res.status_code)

get_us_stocks()
