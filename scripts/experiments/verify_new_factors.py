import yfinance as yf
import pandas as pd

def check_stock(ticker):
    print(f"Checking {ticker}...")
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        debt = info.get('debtToEquity')
        rev_growth = info.get('revenueGrowth')
        gross_profits = info.get('grossProfits') # usually in 'financials'
        total_assets = info.get('totalAssets') # usually in 'balance_sheet'
        
        # Sometimes info doesn't have financial statement items directly, need to check income_stmt/balance_sheet
        if gross_profits is None:
            try:
                fin = stock.financials
                if 'Gross Profit' in fin.index:
                    gross_profits = fin.loc['Gross Profit'].iloc[0]
            except:
                pass
                
        if total_assets is None:
            try:
                bs = stock.balance_sheet
                if 'Total Assets' in bs.index:
                    total_assets = bs.loc['Total Assets'].iloc[0]
            except:
                pass

        print(f"  - Debt/Equity: {debt}")
        print(f"  - Rev Growth: {rev_growth}")
        print(f"  - Gross Profit: {gross_profits}")
        print(f"  - Total Assets: {total_assets}")
        
    except Exception as e:
        print(f"  Error: {e}")

check_stock("005930.KS") # Samsung
check_stock("035420.KS") # Naver
