"""Runtime helpers for constructing KIS API clients consistently."""

from collections.abc import Callable

from src.broker.factory import BrokerFactory
from src.broker.kis import KISBroker
from src.data.api_client import KISAPIClient


def build_kis_client(
    *,
    is_mock: bool,
    market: str | None = None,
    app_key: str | None = None,
    app_secret: str | None = None,
    account_number: str | None = None,
    client_cls: Callable[..., KISAPIClient] = KISAPIClient,
):
    """Build a KIS client with only the fields required by the caller."""
    kwargs = {"is_mock": is_mock}

    if market is not None:
        kwargs["market"] = market

    if app_key is not None or app_secret is not None or account_number is not None:
        kwargs["app_key"] = app_key
        kwargs["app_secret"] = app_secret
        kwargs["account_number"] = account_number

    return client_cls(**kwargs)


def build_kis_broker(
    *,
    is_mock: bool,
    market: str | None = None,
    app_key: str | None = None,
    app_secret: str | None = None,
    account_number: str | None = None,
    broker_factory_cls: Callable[..., BrokerFactory] = BrokerFactory,
    broker_cls: Callable[..., KISBroker] = KISBroker,
):
    """Build a KIS broker adapter with only the fields required by the caller."""
    kwargs = {"is_mock": is_mock}

    if market is not None:
        kwargs["market"] = market

    if app_key is not None or app_secret is not None or account_number is not None:
        kwargs["app_key"] = app_key
        kwargs["app_secret"] = app_secret
        kwargs["account_number"] = account_number

    create_broker = getattr(broker_factory_cls, "create_broker", None)
    if callable(create_broker):
        return create_broker("kis", **kwargs)

    return broker_cls(**kwargs)
