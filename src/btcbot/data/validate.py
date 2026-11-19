"""Controles de calidad sobre series de velas OHLCV."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from btcbot.timeframes import timeframe_delta


@dataclass
class Gap:
    after: pd.Timestamp
    before: pd.Timestamp
    missing: int


@dataclass
class ValidationReport:
    rows: int
    start: pd.Timestamp | None
    end: pd.Timestamp | None
    duplicates: int = 0
    unsorted: bool = False
    misaligned: int = 0
    invalid_ohlc: int = 0
    non_positive_prices: int = 0
    negative_volume: int = 0
    zero_volume: int = 0
    gaps: list[Gap] = field(default_factory=list)

    @property
    def missing_candles(self) -> int:
        return sum(g.missing for g in self.gaps)

    @property
    def ok(self) -> bool:
        """Errores que invalidan los datos. Los huecos y el volumen cero son avisos:
        Binance tuvo mantenimientos reales sin operaciones y no se deben inventar velas."""
        return not (
            self.duplicates
            or self.unsorted
            or self.misaligned
            or self.invalid_ohlc
            or self.non_positive_prices
            or self.negative_volume
        )

    def summary(self) -> str:
        lines = [
            f"Velas: {self.rows}  ({self.start} → {self.end})",
            f"Duplicadas: {self.duplicates}",
            f"Desordenadas: {'sí' if self.unsorted else 'no'}",
            f"Desalineadas con el marco temporal: {self.misaligned}",
            f"OHLC incoherente (high/low fuera de rango): {self.invalid_ohlc}",
            f"Precios <= 0: {self.non_positive_prices}",
            f"Volumen negativo: {self.negative_volume}",
            f"Volumen cero (aviso): {self.zero_volume}",
            f"Huecos (aviso): {len(self.gaps)} huecos, {self.missing_candles} velas faltantes",
        ]
        for g in self.gaps[:10]:
            lines.append(f"  - {g.after} → {g.before}: faltan {g.missing}")
        if len(self.gaps) > 10:
            lines.append(f"  ... y {len(self.gaps) - 10} huecos más")
        lines.append("Resultado: " + ("OK" if self.ok else "CON ERRORES"))
        return "\n".join(lines)


def validate_candles(df: pd.DataFrame, timeframe: str) -> ValidationReport:
    step = timeframe_delta(timeframe)
    report = ValidationReport(
        rows=len(df),
        start=df.index.min() if len(df) else None,
        end=df.index.max() if len(df) else None,
    )
    if df.empty:
        return report

    idx = df.index
    report.duplicates = int(idx.duplicated().sum())
    report.unsorted = not idx.is_monotonic_increasing
    epoch = pd.Timestamp(0, tz="UTC")
    report.misaligned = int(((idx - epoch) % step != pd.Timedelta(0)).sum())

    prices = df[["open", "high", "low", "close"]]
    report.non_positive_prices = int((prices <= 0).any(axis=1).sum())
    bad_high = df["high"] < df[["open", "close", "low"]].max(axis=1)
    bad_low = df["low"] > df[["open", "close", "high"]].min(axis=1)
    report.invalid_ohlc = int((bad_high | bad_low).sum())
    report.negative_volume = int((df["volume"] < 0).sum())
    report.zero_volume = int((df["volume"] == 0).sum())

    unique = idx.unique().sort_values()
    diffs = unique[1:] - unique[:-1]
    for i in (diffs > step).nonzero()[0]:
        missing = int(diffs[i] / step) - 1
        report.gaps.append(Gap(after=unique[i], before=unique[i + 1], missing=missing))
    return report
