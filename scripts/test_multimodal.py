import sys
import os
import argparse

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analysis.multimodal import MultimodalAnalyst
from src.config import Config

def main():
    parser = argparse.ArgumentParser(description="Test Multimodal Analysis")
    parser.add_argument("ticker", nargs="?", default="AAPL", help="Stock Ticker (e.g. AAPL, 005930.KS)")
    args = parser.parse_args()
    
    ticker = args.ticker
    print(f"=== Multimodal Deep Analysis: {ticker} ===")
    
    if not Config.GOOGLE_API_KEY:
        print("Error: GOOGLE_API_KEY is missing.")
        return

    print("1. Initializing Analyst...")
    analyst = MultimodalAnalyst()
    
    print(f"2. Analyzing {ticker} (This may take 10-20 seconds)...")
    try:
        result = analyst.analyze_stock(ticker)
        
        print("\n=== Analysis Result ===")
        print(f"Signal:     {result.get('signal')}")
        print(f"Confidence: {result.get('confidence')}")
        print(f"Reason:     {result.get('reason')}")
        
        if "raw_text" in result:
            print("\n[Raw LLM Output]")
            print(result["raw_text"])
            
    except Exception as e:
        print(f"Analysis Failed: {e}")

if __name__ == "__main__":
    main()
