from datetime import datetime

from src.data.models import Order, OrderSide, OrderType


def test_kis_broker_place_order_passes_exchange(monkeypatch):
    from src.broker.kis import KISBroker

    broker = KISBroker(is_mock=True, market="US")
    order = Order(
        symbol="IBM",
        order_type=OrderType.MARKET,
        side=OrderSide.BUY,
        quantity=2,
        price=111.0,
        created_at=datetime.now(),
    )

    calls = {}
    def _place_order(order_arg, exchange="NASD"):
        calls["value"] = (order_arg, exchange)
        return "ORD-1"

    monkeypatch.setattr(broker.client, "place_order", _place_order)

    result = broker.place_order(order, exchange="NYSE")

    assert result == "ORD-1"
    assert calls["value"][0] is order
    assert calls["value"][1] == "NYSE"


def test_kis_broker_cancel_order_delegates_all_args(monkeypatch):
    from src.broker.kis import KISBroker

    broker = KISBroker(is_mock=True, market="KR")
    calls = {}
    def _cancel_order(order_id, symbol, quantity):
        calls["value"] = (order_id, symbol, quantity)
        return {"rt_cd": "0"}

    monkeypatch.setattr(broker.client, "cancel_order", _cancel_order)

    result = broker.cancel_order("ORD-1", "005930", 3)

    assert result == {"rt_cd": "0"}
    assert calls["value"] == ("ORD-1", "005930", 3)
