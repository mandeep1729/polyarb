from dataclasses import dataclass
from typing import Protocol

import structlog

logger = structlog.get_logger()


@dataclass
class Signal:
    """Trading signal emitted when a profitable spread is detected."""

    side_a: str
    outcome_a: str
    price_a: float
    side_b: str
    outcome_b: str
    price_b: float
    quantity: int
    expected_spread: float
    expected_profit: float


class Strategy(Protocol):
    """Protocol for trading strategies. Implement evaluate() to create new strategies."""

    name: str

    def evaluate(
        self,
        prices_a: dict[str, float],
        prices_b: dict[str, float],
        fees_a: float,
        fees_b: float,
        config: dict,
        outcome_mapping: dict[str, str] | None = None,
    ) -> Signal | None: ...


def normalize_outcomes(
    prices_a: dict[str, float],
    prices_b: dict[str, float],
    outcome_mapping: dict[str, str] | None = None,
) -> tuple[dict[str, float], dict[str, float]]:
    """Remap outcome keys so both price dicts share common labels.

    If outcome_mapping is provided, keys in prices_a are remapped to match
    prices_b. Returns (remapped_a, prices_b) with aligned keys.
    """
    if not outcome_mapping:
        return prices_a, prices_b
    remapped_a = {}
    for key_a, key_b in outcome_mapping.items():
        if key_a in prices_a:
            remapped_a[key_b] = prices_a[key_a]
    return remapped_a, prices_b


def estimate_fee(
    platform: str,
    price: float,
    quantity: int,
    config: dict,
) -> float:
    """Estimate trading fees for a platform.

    Uses per-bot config overrides if present, otherwise platform defaults.
    """
    if platform == "polymarket":
        rate = config.get("polymarket_fee_rate", 0.02)
        return price * quantity * rate
    elif platform == "kalshi":
        per_contract = config.get("kalshi_fee_per_contract", 0.07)
        return quantity * per_contract
    return 0.0


class SimpleArbStrategy:
    """Cross-outcome arbitrage: buy Yes on cheap platform + buy No on expensive platform.

    In prediction markets, Yes + No = $1.00. If you can buy both sides across
    platforms for less than $1.00 total, you lock in guaranteed profit.

    Profit = 1.00 - ask_yes - ask_no - fees
    """

    name = "simple_arb"

    def evaluate(
        self,
        prices_a: dict[str, float],
        prices_b: dict[str, float],
        fees_a: float,
        fees_b: float,
        config: dict,
        outcome_mapping: dict[str, str] | None = None,
    ) -> Signal | None:
        if not prices_a or not prices_b:
            return None

        norm_a, norm_b = normalize_outcomes(prices_a, prices_b, outcome_mapping)
        common = set(norm_a.keys()) & set(norm_b.keys())
        if not common:
            return None

        min_profit = config.get("min_profit", 0.02)
        max_position = config.get("max_position_size", 100)

        best_signal: Signal | None = None
        best_profit = 0.0

        for outcome in common:
            ask_a = norm_a[outcome]
            ask_b = norm_b[outcome]

            # Cross-outcome arb: buy the outcome on the cheaper platform,
            # buy the opposite outcome on the other platform.
            # We need to find the complementary outcome.
            other_outcomes_b = [o for o in norm_b if o != outcome]
            other_outcomes_a = [o for o in norm_a if o != outcome]

            # Case 1: Buy outcome on A (cheaper), buy complement on B
            for other_b in other_outcomes_b:
                total_cost = ask_a + norm_b[other_b]
                profit = (1.0 - total_cost) - fees_a - fees_b
                if profit > best_profit and profit > min_profit:
                    best_profit = profit
                    best_signal = Signal(
                        side_a="buy",
                        outcome_a=outcome,
                        price_a=ask_a,
                        side_b="buy",
                        outcome_b=other_b,
                        price_b=norm_b[other_b],
                        quantity=max_position,
                        expected_spread=round(1.0 - total_cost, 4),
                        expected_profit=round(profit, 4),
                    )

            # Case 2: Buy outcome on B (cheaper), buy complement on A
            for other_a in other_outcomes_a:
                total_cost = ask_b + norm_a[other_a]
                profit = (1.0 - total_cost) - fees_a - fees_b
                if profit > best_profit and profit > min_profit:
                    best_profit = profit
                    best_signal = Signal(
                        side_a="buy",
                        outcome_a=other_a,
                        price_a=norm_a[other_a],
                        side_b="buy",
                        outcome_b=outcome,
                        price_b=ask_b,
                        quantity=max_position,
                        expected_spread=round(1.0 - total_cost, 4),
                        expected_profit=round(profit, 4),
                    )

        return best_signal
