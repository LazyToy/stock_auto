
import sys
import pytest

# 테스트 실행 결과를 파일로 저장
with open("test_result_utf8.txt", "w", encoding="utf-8") as f:
    # stdout과 stderr를 파일로 리다이렉트
    sys.stdout = f
    sys.stderr = f
    
    # pytest 실행
    exit_code = pytest.main(["tests/test_ml_strategy.py", "tests/test_rl_strategy.py", "-v", "--tb=short"])

print(f"Test finished with exit code: {exit_code}")
