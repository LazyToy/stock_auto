import yfinance as yf

def check_exchange(ticker):
    print(f"Checking {ticker}...")
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        print(f"Exchange: {info.get('exchange')}")
        print(f"QuoteType: {info.get('quoteType')}")
    except Exception as e:
        print(f"Error: {e}")

check_exchange("AAPL")
check_exchange("KO") # Coca Cola (NYSE)
check_exchange("SPY") # ETF
