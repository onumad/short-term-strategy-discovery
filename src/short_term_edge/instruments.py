from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InstrumentSpec:
    symbol: str
    tick_size: float
    tick_value: float
    point_value: float
    round_turn_fees: float
    base_slippage_ticks_per_side: float = 1.0
    stress_slippage_ticks_per_side: float = 2.0

    @property
    def base_cost(self) -> float:
        return self.round_turn_fees + 2 * self.base_slippage_ticks_per_side * self.tick_value

    @property
    def stress_cost(self) -> float:
        return self.round_turn_fees + 2 * self.stress_slippage_ticks_per_side * self.tick_value


INSTRUMENTS: dict[str, InstrumentSpec] = {
    "MNQ": InstrumentSpec(
        symbol="MNQ",
        tick_size=0.25,
        tick_value=0.50,
        point_value=2.0,
        round_turn_fees=1.74,
    ),
    "MGC": InstrumentSpec(
        symbol="MGC",
        tick_size=0.10,
        tick_value=1.00,
        point_value=10.0,
        round_turn_fees=1.22,
    ),
}


def get_instrument(symbol: str) -> InstrumentSpec:
    try:
        return INSTRUMENTS[symbol]
    except KeyError as exc:
        raise ValueError(f"Unsupported instrument: {symbol}") from exc

