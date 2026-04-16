import json
import os
from datetime import datetime


def load_state(market: str = "KR"):
    """거래 상태 JSON 파일을 로드하고 high_water_marks를 병합한다."""
    dashboard_state_file = f"data/dashboard_{market.lower()}.json"
    trading_state_file = "trading_state.json"

    state_data = None

    if os.path.exists(dashboard_state_file):
        try:
            with open(dashboard_state_file, "r", encoding="utf-8") as f:
                state_data = json.load(f)
        except Exception:
            pass

    if os.path.exists(trading_state_file):
        try:
            with open(trading_state_file, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
                hwm = raw_data.get("high_water_marks", {})

                if not state_data:
                    state_data = {
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "total_asset": None,
                        "deposit": None,
                        "stocks": [],
                        "style": "VALUE",
                        "high_water_marks": hwm,
                        "market": market,
                    }
                elif "high_water_marks" not in state_data or not state_data["high_water_marks"]:
                    state_data["high_water_marks"] = hwm
        except Exception:
            pass

    if not state_data:
        return {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_asset": None,
            "deposit": None,
            "stocks": [],
            "style": "VALUE",
            "high_water_marks": {},
            "market": market,
        }

    state_data.setdefault("deposit", None)
    state_data.setdefault("stocks", [])
    state_data.setdefault("style", "VALUE")
    state_data.setdefault("total_asset", None)

    return state_data
