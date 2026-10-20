"""Calcula sample_rate_hz, dt_median_ms e dt_p95_ms a partir do CSV.

Uso (a partir de Backend/):

    python -m tests.utils.make_labels tests/fixtures/walks/20261020_normal_mao_01.csv \\
        --steps-real 50 --scenario normal --position mao --device "Poco 6 Pro" \\
        --date 2026-10-20 --notes "contagem em voz alta"
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tests.utils.walk_loader import load_sensor_csv, rate_stats


def build_labels(
    csv_path: Path,
    steps_real: int,
    scenario: str | None = None,
    position: str | None = None,
    device: str | None = None,
    date: str | None = None,
    notes: str | None = None,
    step_times_s: list[float] | None = None,
    time_base: str | None = None,
) -> dict:
    frame = load_sensor_csv(csv_path)
    stats = rate_stats(frame["timestamp"].to_numpy())
    if step_times_s and time_base not in ("epoch", "relative"):
        raise ValueError("time_base é obrigatório quando há step_times_s.")
    return {
        "steps_real": int(steps_real),
        "scenario": scenario,
        "position": position,
        "device": device,
        "date": date,
        "sample_rate_hz": round(stats["sample_rate_hz"], 3),
        "dt_median_ms": round(stats["dt_median_ms"], 3),
        "dt_p95_ms": round(stats["dt_p95_ms"], 3),
        "step_times_s": step_times_s,
        "time_base": time_base if step_times_s else None,
        "notes": notes or "",
    }


def write_labels(csv_path: Path, payload: dict, force: bool = False) -> Path:
    destination = csv_path.with_suffix(".labels.json")
    if destination.exists() and not force:
        raise FileExistsError(
            f"{destination} já existe. Corrigir rótulo exige intenção explícita (--force)."
        )
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera o .labels.json com a taxa medida no CSV.")
    parser.add_argument("csv", type=Path)
    parser.add_argument("--steps-real", type=int, required=True)
    parser.add_argument("--scenario", default=None)
    parser.add_argument("--position", default=None)
    parser.add_argument("--device", default="Poco 6 Pro")
    parser.add_argument("--date", default=None)
    parser.add_argument("--notes", default="")
    parser.add_argument("--time-base", choices=("epoch", "relative"), default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    payload = build_labels(
        args.csv,
        steps_real=args.steps_real,
        scenario=args.scenario,
        position=args.position,
        device=args.device,
        date=args.date,
        notes=args.notes,
        time_base=args.time_base,
    )
    destination = write_labels(args.csv, payload, force=args.force)
    print(destination)


if __name__ == "__main__":
    main()
