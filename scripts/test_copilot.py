from src.copilot.agent import CopilotAgent
import os

def test_manual():
    print("=== AI Copilot Manual Test ===")
    
    if not os.getenv("GOOGLE_API_KEY"):
        print("Warning: GOOGLE_API_KEY is not set.")
    
    try:
        agent = CopilotAgent()
        print("Agent initialized successfully.")
        
        queries = [
            "내 포트폴리오 요약해줘",
            "최근 거래 내역 3건만 알려줘",
            "삼성전자 매매 이유 설명해줘"
        ]
        
        for q in queries:
            print(f"\nQ: {q}")
            response = agent.process_query(q)
            print(f"A: {response}")
            
    except Exception as e:
        print(f"Test failed: {e}")

if __name__ == "__main__":
    test_manual()
