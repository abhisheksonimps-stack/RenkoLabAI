from enum import Enum, unique

@unique
class AssetClass(str, Enum):
    EQUITY = "equity"
    FOREX = "forex"
    CRYPTO = "crypto"
    COMMODITIES = "commodities"
    FUTURES = "futures"
    INDICES = "indices"
    FIXED_INCOME = "fixed_income"

    def __str__(self) -> str:  # pragma: no cover
        return self.value


@unique
class Timeframe(str, Enum):
    ONE_MINUTE = "1m"
    FIVE_MINUTE = "5m"
    FIFTEEN_MINUTE = "15m"
    THIRTY_MINUTE = "30m"
    ONE_HOUR = "1h"
    FOUR_HOUR = "4h"
    ONE_DAY = "1d"
    ONE_WEEK = "1w"
    ONE_MONTH = "1M"

    def __str__(self) -> str:  # pragma: no cover
        return self.value
