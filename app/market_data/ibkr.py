import asyncio
import os
import threading
from contextlib import contextmanager
from typing import Iterator

from ib_insync import IB


IB_HOST = os.getenv("IBKR_HOST", "127.0.0.1")
IB_PORT = int(os.getenv("IBKR_PORT", "7497"))
IB_CLIENT_ID = int(os.getenv("IBKR_CLIENT_ID", "17"))
IB_READONLY = os.getenv("IBKR_READONLY", "true").lower() in ("1", "true", "yes")
IB_MARKET_DATA_TYPE = int(os.getenv("IBKR_MARKET_DATA_TYPE", "1"))
_IBKR_LOCK = threading.Lock()


def _ensure_event_loop() -> None:
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())


def connect_ib() -> IB:
    _ensure_event_loop()

    ib = IB()

    # Common IBKR ports:
    # - 7497: TWS Paper
    # - 7496: TWS Live
    # - 4002: IB Gateway Paper
    # - 4001: IB Gateway Live
    #
    # IB_READONLY=true is recommended while this app only fetches market data.
    # IB_MARKET_DATA_TYPE:
    # - 1: live
    # - 2: frozen
    # - 3: delayed
    # - 4: delayed frozen
    ib.connect(
        IB_HOST,
        IB_PORT,
        clientId=IB_CLIENT_ID,
        readonly=IB_READONLY,
    )
    ib.reqMarketDataType(IB_MARKET_DATA_TYPE)
    return ib


@contextmanager
def ibkr_session() -> Iterator[IB]:
    ib = None

    with _IBKR_LOCK:
        try:
            ib = connect_ib()
            yield ib
        finally:
            if ib is not None and ib.isConnected():
                ib.disconnect()
