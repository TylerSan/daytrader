"""IBKR ib_insync wrapper.

Generic market-data only: bars, snapshots, connection lifecycle.
Futures-specific helpers (OI, term structure, settlement) live in
`reports/futures_data/ib_extensions.py` and accept an IBClient instance.

See spec §4.1 for full design.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
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

    def is_healthy(self) -> bool:
        """Return True iff connected to IB Gateway."""
        return self._ib is not None and self._ib.isConnected()
