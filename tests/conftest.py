import sys
import os

# 프로젝트 루트 디렉토리를 sys.path에 추가하여 src 모듈을 import 할 수 있게 함
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
