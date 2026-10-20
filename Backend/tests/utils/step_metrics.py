"""Métricas de contagem. O casamento por evento é informativo, não é aceite."""

from __future__ import annotations


def count_error_pct(n_det: int, n_real: int) -> float:
    """|N_det − N_real| / N_real × 100. N_real == 0 não tem erro percentual."""
    if n_real <= 0:
        raise ValueError(
            "erro percentual exige N_real > 0; gravação parada usa a contagem de fantasmas"
        )
    return abs(int(n_det) - int(n_real)) / int(n_real) * 100.0


def match_events(
    detected_times_s: list[float],
    real_times_s: list[float],
    window_s: float = 0.250,
) -> dict[str, float]:
    """Casa cada passo detectado com no máximo um passo real dentro de ±window_s."""
    detected = sorted(float(t) for t in detected_times_s)
    real = sorted(float(t) for t in real_times_s)
    used = [False] * len(real)
    true_positives = 0
    for detected_t in detected:
        best_index = None
        best_dt = window_s
        for index, real_t in enumerate(real):
            if used[index]:
                continue
            delta = abs(detected_t - real_t)
            if delta <= best_dt:
                best_dt = delta
                best_index = index
        if best_index is not None:
            used[best_index] = True
            true_positives += 1
    false_positives = len(detected) - true_positives
    false_negatives = len(real) - true_positives
    precision = true_positives / (true_positives + false_positives) if detected else 0.0
    recall = true_positives / (true_positives + false_negatives) if real else 0.0
    return {
        "tp": true_positives,
        "fp": false_positives,
        "fn": false_negatives,
        "precision": precision,
        "recall": recall,
    }
