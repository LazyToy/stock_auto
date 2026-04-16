from src.trader.self_healing import OrderContext, SelfHealingEngine


def test_self_healing_execute_order_cancels_pending_order_on_monitor_failure(monkeypatch):
    api_client = type("Api", (), {})()
    captured = {"cancel": None}

    def _place_order(order, exchange="NASD"):
        return "ORD-REC-1"

    def _cancel_order(order_id, symbol, quantity):
        captured["cancel"] = (order_id, symbol, quantity)
        return {"rt_cd": "0"}

    api_client.place_order = _place_order
    api_client.cancel_order = _cancel_order

    engine = SelfHealingEngine(api_client=api_client)
    monkeypatch.setattr(engine, "_monitor_order", lambda context: False)

    context = OrderContext(
        symbol="005930",
        quantity=2,
        side="BUY",
        price=50000,
    )

    assert engine.execute_order(context) is True
    assert captured["cancel"] == ("ORD-REC-1", "005930", 2)


def test_self_healing_execute_order_cancels_pending_order_via_broker(monkeypatch):
    broker = type("Broker", (), {})()
    captured = {"cancel": None}

    def _place_order(order, exchange="NASD"):
        return "ORD-BROKER-REC-1"

    def _cancel_order(order_id, symbol, quantity):
        captured["cancel"] = (order_id, symbol, quantity)
        return {"rt_cd": "0"}

    broker.place_order = _place_order
    broker.cancel_order = _cancel_order

    engine = SelfHealingEngine(api_client=None, broker=broker)
    monkeypatch.setattr(engine, "_monitor_order", lambda context: False)

    context = OrderContext(
        symbol="IBM",
        quantity=3,
        side="BUY",
        price=100.0,
        metadata={"exchange": "NYSE"},
    )

    assert engine.execute_order(context) is True
    assert captured["cancel"] == ("ORD-BROKER-REC-1", "IBM", 3)
