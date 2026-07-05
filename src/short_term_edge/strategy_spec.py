from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

ALLOWED_INSTRUMENTS = {"MNQ", "MGC"}
ALLOWED_FAMILIES = {
    "opening_range_failure",
    "opening_range_breakout",
    "vwap_reclaim_rejection",
    "prior_session_levels",
}
ALLOWED_ENTRY_RULES = {
    "close_back_inside",
    "close_outside_range",
    "vwap_cross",
    "prior_level_reaction",
}
ALLOWED_EXIT_RULES = {"range_target", "fixed_ticks", "r_multiple"}
ALLOWED_RISK_RULES = {"one_open_position"}


def _normalized_params(params: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in sorted(params):
        value = params[key]
        if isinstance(value, dict):
            out[key] = _normalized_params(value)
        elif isinstance(value, (list, tuple)):
            out[key] = list(value)
        else:
            out[key] = value
    return out


@dataclass(frozen=True)
class EntryRule:
    name: str
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "params": _normalized_params(self.params)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EntryRule":
        return cls(name=str(data["name"]), params=dict(data.get("params", {})))


@dataclass(frozen=True)
class ExitRule:
    name: str
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "params": _normalized_params(self.params)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExitRule":
        return cls(name=str(data["name"]), params=dict(data.get("params", {})))


@dataclass(frozen=True)
class RiskRule:
    name: str
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "params": _normalized_params(self.params)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RiskRule":
        return cls(name=str(data["name"]), params=dict(data.get("params", {})))


@dataclass(frozen=True)
class StrategySpec:
    instrument: str
    family: str
    timeframe: int
    entry: EntryRule
    exit: ExitRule
    risk: RiskRule
    version: int = 1
    notes: str = ""

    def validate(self) -> "StrategySpec":
        if self.instrument not in ALLOWED_INSTRUMENTS:
            raise ValueError(f"Unsupported instrument: {self.instrument}")
        if self.family not in ALLOWED_FAMILIES:
            raise ValueError(f"Unsupported strategy family: {self.family}")
        if self.entry.name not in ALLOWED_ENTRY_RULES:
            raise ValueError(f"Unsupported entry rule: {self.entry.name}")
        if self.exit.name not in ALLOWED_EXIT_RULES:
            raise ValueError(f"Unsupported exit rule: {self.exit.name}")
        if self.risk.name not in ALLOWED_RISK_RULES:
            raise ValueError(f"Unsupported risk rule: {self.risk.name}")
        if int(self.timeframe) <= 0:
            raise ValueError("timeframe must be positive")
        max_trades = int(self.risk.params.get("max_trades_per_day", 1))
        if max_trades < 1 or max_trades > 3:
            raise ValueError("max_trades_per_day must be between 1 and 3 for Phase 5A")
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "instrument": self.instrument,
            "family": self.family,
            "timeframe": int(self.timeframe),
            "entry": self.entry.to_dict(),
            "exit": self.exit.to_dict(),
            "risk": self.risk.to_dict(),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StrategySpec":
        return cls(
            version=int(data.get("version", 1)),
            instrument=str(data["instrument"]),
            family=str(data["family"]),
            timeframe=int(data["timeframe"]),
            entry=EntryRule.from_dict(dict(data["entry"])),
            exit=ExitRule.from_dict(dict(data["exit"])),
            risk=RiskRule.from_dict(dict(data["risk"])),
            notes=str(data.get("notes", "")),
        ).validate()

    def to_json(self) -> str:
        self.validate()
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, payload: str) -> "StrategySpec":
        return cls.from_dict(json.loads(payload))

    def canonical_id(self) -> str:
        payload = self.to_json().encode("utf-8")
        digest = hashlib.sha1(payload).hexdigest()[:10]
        return f"{self.instrument}_{self.family}_tf{int(self.timeframe)}_{digest}"


@dataclass(frozen=True)
class SearchSpace:
    symbols: tuple[str, ...] = ("MNQ", "MGC")
    timeframes: tuple[int, ...] = (1, 3, 5, 10)
    opening_range_minutes: tuple[int, ...] = (15, 30, 60)
    max_trades_per_day: tuple[int, ...] = (1, 2)

    def validate(self) -> "SearchSpace":
        for symbol in self.symbols:
            if symbol not in ALLOWED_INSTRUMENTS:
                raise ValueError(f"Unsupported symbol in search space: {symbol}")
        return self
