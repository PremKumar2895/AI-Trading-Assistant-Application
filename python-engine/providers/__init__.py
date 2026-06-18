"""Real-market data providers (clean OHLCV) with a router that falls back to vision."""
from .router import DataRouter

__all__ = ["DataRouter"]
