"""Tabela de erro por fixture, para colar no PR.

    python -m tests.utils.report
"""

from __future__ import annotations

from tests.conftest import SAMPLE_WALK_CSV, TARGETS, WALKS_DIR
from tests.utils.step_metrics import count_error_pct
from tests.utils.walk_loader import discover_walks, frame_to_samples, load_sensor_csv

from pdr.pipeline import detect_steps_from_samples


def _row(
    name: str,
    n_real: int,
    n_det: int,
    rate_hz: float,
    tolerance_steps: int | None = None,
) -> str:
    if tolerance_steps is not None:
        delta = abs(n_det - n_real)
        flag = "ok" if delta <= tolerance_steps else "FORA"
        return f"| {name} | {n_real} | {n_det} | ±{delta} | {rate_hz:.2f} | {flag} |"
    if n_real <= 0:
        flag = "ok" if n_det <= TARGETS["A2_phantoms_max"] else "FORA"
        return f"| {name} | {n_real} | {n_det} | fantasmas | {rate_hz:.2f} | {flag} |"
    error = count_error_pct(n_det, n_real)
    flag = "ok" if error <= TARGETS["A1_per_walk_error_pct"] else "FORA"
    return f"| {name} | {n_real} | {n_det} | {error:.2f}% | {rate_hz:.2f} | {flag} |"


def build_table() -> str:
    lines = [
        "| fixture | N_real | N_det | erro | taxa Hz | meta |",
        "|---|---:|---:|---:|---:|---|",
    ]
    frame = load_sensor_csv(SAMPLE_WALK_CSV)
    result = detect_steps_from_samples(frame_to_samples(frame))
    lines.append(_row("sample_walk.csv", 20, result.steps_count, result.sample_rate_hz))

    total_abs = 0
    total_real = 0
    for walk in discover_walks(WALKS_DIR):
        result = detect_steps_from_samples(walk.samples)
        lines.append(_row(
            walk.name,
            walk.labels.steps_real,
            result.steps_count,
            result.sample_rate_hz,
            walk.labels.tolerance_steps,
        ))
        if walk.labels.steps_real > 0:
            total_abs += abs(result.steps_count - walk.labels.steps_real)
            total_real += walk.labels.steps_real
    if total_real:
        aggregate = 100.0 * total_abs / total_real
        lines.append(
            f"\nErro agregado (informativo, meta desejável 3%, não bloqueia): {aggregate:.2f}%."
        )
    else:
        lines.append(
            "\nNenhuma caminhada rotulada em tests/fixtures/walks/ ainda. "
            "O agregado de 3% passa a ser calculado quando os CSV do Poco 6 Pro entrarem."
        )
    return "\n".join(lines)


def main() -> None:
    print(build_table())


if __name__ == "__main__":
    main()
