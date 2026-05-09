from app.market_data.models import MarketContext, MarketIndicators


def get_market_context(normalized: dict, classification: dict) -> MarketContext:
    strategy = classification.get("strategy") if isinstance(classification, dict) else None

    # Future behavior will depend on strategy:
    # - ultra_short: option bid/ask/spread/liquidity/current underlying price.
    # - short/swing/leap: candles, RSI, ATR, support/resistance, IV/HV, trend context.
    _ = strategy

    return MarketContext(indicators=MarketIndicators())
