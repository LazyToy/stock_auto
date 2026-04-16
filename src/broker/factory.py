from enum import Enum
from typing import Optional
from src.broker.base import BaseBroker
from src.broker.kis import KISBroker
import logging

class BrokerType(Enum):
    KIS = "kis"
    KIWOOM = "kiwoom"
    SHINHAN = "shinhan"

class BrokerFactory:
    """브로커 생성을 담당하는 팩토리 클래스"""

    @staticmethod
    def create_broker(broker_type: str, **kwargs) -> Optional[BaseBroker]:
        logger = logging.getLogger(__name__)

        try:
            b_type = BrokerType(broker_type.lower())
        except ValueError:
            logger.error(f"Unsupported broker type: {broker_type}")
            return None

        if b_type == BrokerType.KIS:
            return KISBroker(**kwargs)
        elif b_type == BrokerType.KIWOOM:
            raise NotImplementedError(
                "KiwoomBroker는 현재 미구현 상태입니다. KIS 브로커를 사용하세요."
            )
        elif b_type == BrokerType.SHINHAN:
            raise NotImplementedError(
                "ShinhanBroker는 현재 미구현 상태입니다. KIS 브로커를 사용하세요."
            )
        else:
            return None
