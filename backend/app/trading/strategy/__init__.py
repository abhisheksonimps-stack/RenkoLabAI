"""Trading strategy framework."""

from backend.app.trading.strategy.ema_crossover import EMACrossoverStrategy
from backend.app.trading.strategy.ema_trend import EMATrendStrategy
from backend.app.trading.strategy.engine import StrategyEngine
from backend.app.trading.strategy.factory import StrategyFactory
from backend.app.trading.strategy.interfaces import (
    SignalInterface,
    Strategy,
    StrategyConfiguration,
    StrategyContext,
    StrategyMetadataValue,
    StrategyParameterValue,
    StrategyResult,
)
from backend.app.trading.strategy.loader import StrategyLoader
from backend.app.trading.strategy.pdh_pdl_breakout import PDHPDLBreakoutStrategy
from backend.app.trading.strategy.renko_trend import RenkoTrendStrategy
from backend.app.trading.strategy.registry import StrategyRegistry, default_strategy_registry
from backend.app.trading.strategy.risk import (
    MaxDailyLossRule,
    MaxOpenPositionsRule,
    RiskManager,
    RiskRule,
    StopLossRule,
    TakeProfitRule,
    TrailingStopRule,
)
from backend.app.trading.strategy.sizing import (
    ATRPositionSizer,
    FixedQuantitySizer,
    FixedRiskPercentSizer,
    KellySizer,
    PositionSizer,
    PositionSizerFactory,
    PositionSizingContext,
    PositionSizingMethod,
)

__all__ = [
    "ATRPositionSizer",
    "EMACrossoverStrategy",
    "EMATrendStrategy",
    "FixedQuantitySizer",
    "FixedRiskPercentSizer",
    "KellySizer",
    "MaxDailyLossRule",
    "MaxOpenPositionsRule",
    "PDHPDLBreakoutStrategy",
    "PositionSizer",
    "PositionSizerFactory",
    "PositionSizingContext",
    "PositionSizingMethod",
    "RenkoTrendStrategy",
    "RiskManager",
    "RiskRule",
    "SignalInterface",
    "StopLossRule",
    "Strategy",
    "StrategyConfiguration",
    "StrategyContext",
    "StrategyEngine",
    "StrategyFactory",
    "StrategyLoader",
    "StrategyMetadataValue",
    "StrategyParameterValue",
    "StrategyRegistry",
    "StrategyResult",
    "TakeProfitRule",
    "TrailingStopRule",
    "default_strategy_registry",
]
