"""Roda o pipeline num CSV e imprime passos detectados contra o rótulo, se houver.

A partir de Backend/:

    python others/evaluate_steps.py datasets/sample_walk.csv --steps-real 20
    python others/evaluate_steps.py tests/fixtures/walks/20261020_normal_mao_01.csv
    python others/evaluate_steps.py arquivo.csv --max-gap-s 0.5
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from pdr.pipeline import detect_steps_from_samples  # noqa: E402
from pdr.steps import StepDetectorConfig  # noqa: E402
from tests.utils.step_metrics import count_error_pct  # noqa: E402
from tests.utils.walk_loader import frame_to_samples, load_sensor_csv, load_walk, rate_stats  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Conta passos de um CSV com o pipeline do backend.")
    parser.add_argument("csv", type=Path)
    parser.add_argument("--steps-real", type=int, default=None)
    parser.add_argument(
        "--max-gap-s",
        type=float,
        default=None,
        help=(
            "Substitui StepDetectorConfig.max_gap_s (padrão 0,25 s). "
            "Suba para ~0,5 s se o Chrome/MIUI furar o devicemotion."
        ),
    )
    args = parser.parse_args()
    config = None
    if args.max_gap_s is not None:
        config = replace(StepDetectorConfig(), max_gap_s=args.max_gap_s)
        print(f"max_gap_s={config.max_gap_s:.3f} s")

    labels_path = args.csv.with_suffix(".labels.json")
    n_real = args.steps_real
    if labels_path.exists():
        recording = load_walk(args.csv, labels_path)
        samples = recording.samples
        if n_real is None:
            n_real = recording.labels.steps_real
        print(
            f"taxa rotulada {recording.labels.sample_rate_hz:.2f} Hz "
            f"(dt mediano {recording.labels.dt_median_ms:.2f} ms, "
            f"p95 {recording.labels.dt_p95_ms:.2f} ms)"
        )
    else:
        frame = load_sensor_csv(args.csv)
        samples = frame_to_samples(frame)
        stats = rate_stats(frame["timestamp"].to_numpy())
        print(
            f"taxa medida {stats['sample_rate_hz']:.2f} Hz "
            f"(dt mediano {stats['dt_median_ms']:.2f} ms, p95 {stats['dt_p95_ms']:.2f} ms)"
        )

    result = detect_steps_from_samples(samples, config=config)
    print(f"passos detectados: {result.steps_count}")
    print(f"taxa usada no pipeline: {result.sample_rate_hz:.2f} Hz")
    print(f"distância: {result.distance_m:.2f} m")
    print(f"mensagem: {result.message}")
    if n_real is not None and n_real > 0:
        error = count_error_pct(result.steps_count, n_real)
        print(f"N_real={n_real}  erro={error:.2f}%")
    elif n_real == 0:
        print(f"N_real=0  fantasmas={result.steps_count}")
    for step in result.steps:
        print(
            f"  t={step.timestamp:.3f}s  "
            f"cadência={step.cadence_spm:.1f} spm  "
            f"comprimento={step.step_length_m:.2f} m"
        )


if __name__ == "__main__":
    main()
