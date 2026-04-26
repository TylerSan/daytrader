"""IBKR ib_insync wrapper.

Generic market-data only: bars, snapshots, connection lifecycle.
Futures-specific helpers (OI, term structure, settlement) live in
`reports/futures_data/ib_extensions.py` and accept an IBClient instance.

See spec §4.1 for full design.
"""

from __future__ import annotations

from ib_insync import IB


class IBClient:
    """Singleton ib_insync wrapper, reused across reports."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 4002,
        client_id: int = 1,
    ) -> None:
        self.host = host
        self.port = port
        self.client_id = client_id
        self._ib: IB | None = None

    def connect(self, timeout: int = 10) -> None:
        """Establish connection to IB Gateway. Idempotent."""
        if self._ib is not None and self._ib.isConnected():
            return
        if self._ib is None:
            self._ib = IB()
        self._ib.connect(
            host=self.host,
            port=self.port,
            clientId=self.client_id,
            timeout=timeout,
        )

    def disconnect(self) -> None:
        """Close connection. Idempotent."""
        if self._ib is not None and self._ib.isConnected():
            self._ib.disconnect()

    def reconnect(self) -> None:
        """Disconnect then reconnect. Idempotent."""
        self.disconnect()
        self.connect()

    def is_healthy(self) -> bool:
        """Return True iff connected to IB Gateway."""
        return self._ib is not None and self._ib.isConnected()
