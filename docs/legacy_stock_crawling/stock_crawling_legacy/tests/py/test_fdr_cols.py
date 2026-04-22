import FinanceDataReader as fdr

def test():
    df = fdr.StockListing('NASDAQ')
    print(df.columns)
    print(df.head(2))

test()
