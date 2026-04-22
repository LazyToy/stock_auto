import yfinance as yf
import pandas as pd

def test_yf():
    tickers = ["AAPL", "MSFT", "TSLA"]
    data = yf.download(tickers, period="1d", group_by="ticker")
    for t in tickers:
        print(t)
        print(data[t])

test()
