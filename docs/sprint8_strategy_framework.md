# Sprint 8 Strategy Framework

Sprint 8 adds a production strategy SDK on top of the existing RenkoLabAI trading stack without replacing Sprint T1/T2 backtesting or Sprint 7 analytics.

Implemented components:

- Strategy interface, context, configuration, result and signal protocol.
- Registry, factory and package auto-loader.
- Signal support for BUY, SELL, EXIT_LONG, EXIT_SHORT and HOLD. EXIT_LONG and EXIT_SHORT are backwards-compatible aliases of the existing EXIT signal.
- Position sizing policies: fixed quantity, fixed risk percentage, ATR-based sizing and Kelly extension.
- Risk-management rules: stop loss, take profit, trailing stop, max daily loss and max open positions.
- Strategy lifecycle hooks: initialize, on_market_data, on_brick, on_tick, on_order_fill, on_position_close and shutdown.
- Built-in executable strategies: PDH/PDL breakout, EMA trend and Renko trend.
- Backtesting compatibility through the existing StrategyEngine and BacktestEngine.
- Paper-trading integration through PaperStrategyBridge.

The framework remains registry-driven and uses existing trading execution, portfolio, paper trading, Renko brick and market-data models.
