"""
steps.py — detecção de passos por picos, sem trava global.

O detector antigo devolvia zero passos para a gravação inteira quando o
desvio-padrão, o jerk médio, o giro médio ou a energia de "chacoalho" na
FFT passavam de um teto. Uma pausa no meio, ou um segundo de manuseio,
apagava a caminhada. Aqui as mesmas constantes continuam valendo, mas
cada uma é aplicada na janela do pico. A taxa sai dos timestamps; o
refratário fica em segundos e vira amostras só na hora.

Um pico isolado (toque, pancada, celular na mão parado) não forma uma
sequência de cadência e é descartado. Passo de verdade vem em série,
com intervalo estável.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, replace

import numpy as np
import numpy.typing as npt
from scipy.signal import find_peaks

from pdr.sampling import estimate_sample_rate_hz, sanitize_rate_hz


@dataclass(frozen=True, slots=True)
class StepDetectorConfig:
    """Constantes do detector. Os defaults são os valores que estavam
    soltos em ``pdr/steps.py`` e na trava de giro de ``pdr/processor.py``.

    Não há taxa de amostragem aqui. ``min_step_interval_s`` é segundos;
    a conversão para amostras usa a taxa medida na chamada.
    """

    # Altura do pico no sinal vertical ainda com gravidade (~9,8 m/s²).
    min_height_abs: float = 10.3
    height_offset: float = 0.35
    min_prominence_abs: float = 0.45
    prominence_std_factor: float = 0.30

    # Refratário histórico de 0,33 s. O teto de 1,2 s separa uma passada
    # de uma pausa (abaixo de ~50 passos/minuto o pico não continua a série).
    min_step_interval_s: float = 0.33
    max_step_interval_s: float = 1.20
    # Série mínima: pancada e manuseio irregular não chegam a 3 picos regulares.
    min_consecutive_steps: int = 3

    # Janela em que std/FFT/jerk/giro são avaliados. Antes isso era a gravação toda.
    analysis_window_s: float = 2.0
    min_window_std: float = 0.35
    max_window_std: float = 3.8

    walk_band_hz: tuple[float, float] = (0.8, 2.8)
    shake_band_hz: tuple[float, float] = (3.2, 15.0)
    shake_energy_ratio: float = 1.5
    # 18,0 foi calibrado numa FFT de gravação (~500 amostras). É escalado
    # pelo tamanho da janela na hora de aplicar.
    shake_energy_min: float = 18.0
    shake_reference_samples: int = 500

    max_mean_jerk: float = 50.0
    max_local_jerk: float = 65.0
    max_mean_gyro: float = 2.8
    max_local_gyro: float = 3.0
    # Travas que o processor aplicava na gravação inteira (pico 7,5 / média 4,0).
    # Continuam na config e entram na mesma decisão, por janela — não zeram o lote.
    gyro_peak_limit: float = 7.5
    gyro_mean_limit: float = 4.0

    max_peak_abs: float = 15.5
    acc_diff_min: float = 1.2
    acc_diff_max: float = 5.0

    # k de Weinberg usado em process-raw. O construtor antigo do detector
    # aceitava 0,48; quem passar ``weinberg_k`` continua sobrescrevendo.
    weinberg_k: float = 0.45
    step_length_min_m: float = 0.40
    step_length_max_m: float = 0.95

    lowpass_cutoff_hz: float = 2.2
    lowpass_order: int = 2
    madgwick_gain: float = 0.033
    # Vão entre timestamps, em segundos, acima do qual a gravação vira outro
    # segmento (não se interpola por cima). 0,25 s absorve um dt perdido.
    # Se o Chrome no MIUI engasgar e o devicemotion furar ~0,5 s, suba para
    # 0,5 — senão um soluço parte a passada e a série de cadência pode cair.
    # Ex.: StepDetectorConfig(max_gap_s=0.5) ou evaluate_steps.py --max-gap-s 0.5.
    max_gap_s: float = 0.25
    min_samples: int = 15

    # Abaixo disso o sinal já não traz a gravidade (foi high-pass). O teto
    # absoluto de 10,3 m/s² só faz sentido com a gravidade dentro.
    gravity_present_above: float = 8.0


@dataclass(frozen=True, slots=True)
class StepEvent:
    timestamp: float
    index: int
    cadence_spm: float
    step_length_m: float


class StepDetector(ABC):
    @abstractmethod
    def detect(
        self,
        timestamps: npt.NDArray[np.float64],
        filtered_magnitude: npt.NDArray[np.float64],
        gyro_magnitude: npt.NDArray[np.float64] | None = None,
        sample_rate_hz: float | None = None,
    ) -> list[StepEvent]:
        raise NotImplementedError


class PeakStepDetector(StepDetector):
    def __init__(
        self,
        sample_rate_hz: float | None = None,
        weinberg_k: float | None = None,
        config: StepDetectorConfig | None = None,
    ) -> None:
        self._config = config or StepDetectorConfig()
        if weinberg_k is not None:
            self._config = replace(self._config, weinberg_k=float(weinberg_k))
        # Assinatura antiga (run_csv_client passa sample_rate_hz=50). A taxa
        # efetiva não é esta constante: ``detect`` mede pelos timestamps.
        self._declared_sample_rate_hz = sample_rate_hz

    @property
    def config(self) -> StepDetectorConfig:
        return self._config

    def detect(
        self,
        timestamps: npt.NDArray[np.float64],
        filtered_magnitude: npt.NDArray[np.float64],
        gyro_magnitude: npt.NDArray[np.float64] | None = None,
        sample_rate_hz: float | None = None,
    ) -> list[StepEvent]:
        # ``sample_rate_hz`` e o valor guardado no construtor ficam na
        # assinatura por causa de chamadas antigas (run_csv_client). Não
        # entram no cálculo: 30 Hz declarado em cima de um arquivo de 50 Hz
        # mudava o refratário e a FFT.
        _ = (sample_rate_hz, self._declared_sample_rate_hz)

        signal = np.asarray(filtered_magnitude, dtype=np.float64)
        time = np.asarray(timestamps, dtype=np.float64)
        if signal.ndim != 1 or time.ndim != 1 or len(signal) != len(time):
            return []
        if len(signal) < self._config.min_samples:
            return []
        if not np.all(np.isfinite(signal)) or not np.all(np.isfinite(time)):
            finite = np.isfinite(signal) & np.isfinite(time)
            signal = signal[finite]
            time = time[finite]
            if gyro_magnitude is not None and len(gyro_magnitude) == len(finite):
                gyro_magnitude = np.asarray(gyro_magnitude, dtype=np.float64)[finite]
            if len(signal) < self._config.min_samples:
                return []

        order = np.argsort(time, kind="mergesort")
        time = time[order]
        signal = signal[order]
        gyro = _align_gyro(gyro_magnitude, order, len(signal))

        # Timestamps duplicados quebram 1/dt. Fica o primeiro.
        keep = np.ones(len(time), dtype=bool)
        keep[1:] = np.diff(time) > 1e-4
        time = time[keep]
        signal = signal[keep]
        if gyro is not None:
            gyro = gyro[keep]
        if len(signal) < self._config.min_samples:
            return []

        sample_rate = _rate_from_timestamps(time)
        if not np.isfinite(sample_rate):
            return []

        candidates = self._candidate_indices(signal, time, gyro, sample_rate)
        accepted = _keep_regular_runs(candidates, time, self._config)
        return self._events_from_indices(accepted, signal, time, sample_rate)

    def _candidate_indices(
        self,
        signal: npt.NDArray[np.float64],
        time: npt.NDArray[np.float64],
        gyro: npt.NDArray[np.float64] | None,
        sample_rate: float,
    ) -> list[int]:
        config = self._config
        min_distance = max(1, int(np.ceil(config.min_step_interval_s * sample_rate - 1e-9)))
        peaks, properties = find_peaks(
            signal,
            distance=min_distance,
            prominence=config.min_prominence_abs,
        )
        prominences = properties.get("prominences", np.zeros(len(peaks)))
        jerk = np.abs(np.diff(signal)) * sample_rate
        gravity_present = float(np.median(signal)) >= config.gravity_present_above

        accepted: list[int] = []
        for peak, prominence in zip(peaks, prominences, strict=False):
            if self._peak_is_step(
                int(peak),
                float(prominence),
                signal,
                gyro,
                jerk,
                sample_rate,
                min_distance,
                gravity_present,
            ):
                accepted.append(int(peak))
        return accepted

    def _peak_is_step(
        self,
        peak: int,
        prominence: float,
        signal: npt.NDArray[np.float64],
        gyro: npt.NDArray[np.float64] | None,
        jerk: npt.NDArray[np.float64],
        sample_rate: float,
        min_distance: int,
        gravity_present: bool,
    ) -> bool:
        config = self._config
        n = len(signal)
        half_step = max(1, min_distance // 2)
        step_lo = max(0, peak - half_step)
        step_hi = min(n, peak + half_step + 1)

        win = max(8, int(round(config.analysis_window_s * sample_rate)))
        half_win = win // 2
        win_lo = max(0, peak - half_win)
        win_hi = min(n, peak + half_win + 1)
        window = signal[win_lo:win_hi]
        window_std = float(np.std(window))
        window_mean = float(np.mean(window))

        if window_std < config.min_window_std:
            return False

        gyro_mean, gyro_max_local, gyro_max_window = _gyro_stats(gyro, win_lo, win_hi, step_lo, step_hi)
        jerk_lo = max(0, peak - 2)
        jerk_hi = min(len(jerk), peak + 2)
        local_jerk = float(np.max(jerk[jerk_lo:jerk_hi])) if jerk_hi > jerk_lo else 0.0
        mean_jerk = float(np.mean(np.abs(np.diff(window)) * sample_rate)) if len(window) > 2 else 0.0

        handling = _window_is_handling(
            window,
            sample_rate,
            config,
            window_std=window_std,
            gyro_mean=gyro_mean,
            gyro_max_window=gyro_max_window,
            mean_jerk=mean_jerk,
        )
        if handling:
            return False

        if gravity_present:
            height_limit = max(config.min_height_abs, window_mean + config.height_offset)
        else:
            height_limit = window_mean + config.height_offset
        if float(signal[peak]) < height_limit:
            return False

        prominence_limit = max(config.min_prominence_abs, config.prominence_std_factor * window_std)
        if prominence < prominence_limit:
            return False

        # Giro e jerk locais: rejeitam o pico, não o resto da gravação.
        # O teto antigo do processor (7,5 / 4,0) entra junto; o mais estrito
        # (3,0 / 2,8) é o que efetivamente corta o manuseio.
        if gyro is not None:
            if gyro_max_local > config.max_local_gyro or gyro_max_local > config.gyro_peak_limit:
                return False
            if gyro_mean > config.max_mean_gyro or gyro_mean > config.gyro_mean_limit:
                return False
        if local_jerk > config.max_local_jerk and gyro_max_local > config.max_local_gyro:
            return False

        acc_diff = float(np.max(signal[step_lo:step_hi]) - np.min(signal[step_lo:step_hi]))
        if acc_diff < config.acc_diff_min:
            return False
        # O teto 5,0 foi posto para barrar pancada. Numa passada forte e
        # lisa (giro baixo, jerk baixo, std de caminhada) ele cortava pico
        # real — no sample_walk cru, 4 dos 20 picos caíam por 5,04–5,19.
        if acc_diff > config.acc_diff_max:
            impact = (
                local_jerk > config.max_local_jerk
                or gyro_max_local > config.max_local_gyro
                or window_std > config.max_window_std
                or float(signal[peak]) > config.max_peak_abs
            )
            if impact:
                return False
        elif float(signal[peak]) > config.max_peak_abs and local_jerk > config.max_local_jerk:
            return False

        return True

    def _events_from_indices(
        self,
        indices: list[int],
        signal: npt.NDArray[np.float64],
        time: npt.NDArray[np.float64],
        sample_rate: float,
    ) -> list[StepEvent]:
        config = self._config
        min_distance = max(1, int(np.ceil(config.min_step_interval_s * sample_rate - 1e-9)))
        half_step = max(1, min_distance // 2)
        events: list[StepEvent] = []
        previous_t: float | None = None
        for peak in indices:
            lo = max(0, peak - half_step)
            hi = min(len(signal), peak + half_step + 1)
            acc_diff = float(np.max(signal[lo:hi]) - np.min(signal[lo:hi]))
            acc_diff = max(acc_diff, 1e-6)
            length = float(np.clip(
                config.weinberg_k * (acc_diff ** 0.25),
                config.step_length_min_m,
                config.step_length_max_m,
            ))
            timestamp = float(time[peak])
            if previous_t is None:
                cadence = 0.0
            else:
                dt = timestamp - previous_t
                cadence = float(60.0 / dt) if dt > 0 else 0.0
            previous_t = timestamp
            events.append(
                StepEvent(
                    timestamp=timestamp,
                    index=int(peak),
                    cadence_spm=cadence,
                    step_length_m=length,
                )
            )
        return events


def _align_gyro(
    gyro_magnitude: npt.NDArray[np.float64] | None,
    order: npt.NDArray[np.int64],
    n_signal: int,
) -> npt.NDArray[np.float64] | None:
    if gyro_magnitude is None:
        return None
    gyro = np.asarray(gyro_magnitude, dtype=np.float64)
    if gyro.shape != (n_signal,):
        return None
    return gyro[order]


def _rate_from_timestamps(timestamps: npt.NDArray[np.float64]) -> float:
    return sanitize_rate_hz(estimate_sample_rate_hz(timestamps))


def _gyro_stats(
    gyro: npt.NDArray[np.float64] | None,
    win_lo: int,
    win_hi: int,
    step_lo: int,
    step_hi: int,
) -> tuple[float, float, float]:
    if gyro is None:
        return 0.0, 0.0, 0.0
    window = gyro[win_lo:win_hi]
    local = gyro[step_lo:step_hi]
    gyro_mean = float(np.mean(window)) if window.size else 0.0
    gyro_max_local = float(np.max(local)) if local.size else 0.0
    gyro_max_window = float(np.max(window)) if window.size else 0.0
    return gyro_mean, gyro_max_local, gyro_max_window


def _window_is_handling(
    window: npt.NDArray[np.float64],
    sample_rate: float,
    config: StepDetectorConfig,
    window_std: float,
    gyro_mean: float,
    gyro_max_window: float,
    mean_jerk: float,
) -> bool:
    """Manuseio na janela do pico: FFT de chacoalho, ou std alto com giro/jerk.

    Não olha o desvio da gravação inteira. Uma pausa longa não entra nesta
    janela e portanto não apaga os picos de quando a pessoa andou.
    """
    shake = _shake_dominates(window, sample_rate, config)
    violent_gyro = gyro_mean > config.max_mean_gyro or gyro_max_window > config.gyro_peak_limit
    violent_jerk = mean_jerk > config.max_mean_jerk
    if shake and (violent_gyro or violent_jerk or window_std > config.max_window_std):
        return True
    if window_std > config.max_window_std and (violent_gyro or violent_jerk):
        return True
    if violent_jerk and violent_gyro:
        return True
    return False


def _shake_dominates(
    window: npt.NDArray[np.float64],
    sample_rate: float,
    config: StepDetectorConfig,
) -> bool:
    n = len(window)
    if n < 16 or sample_rate <= 0:
        return False
    spectrum = np.abs(np.fft.rfft(window - np.mean(window)))
    freqs = np.fft.rfftfreq(n, d=1.0 / sample_rate)
    walk_lo, walk_hi = config.walk_band_hz
    shake_lo, shake_hi = config.shake_band_hz
    walk_energy = float(np.sum(spectrum[(freqs >= walk_lo) & (freqs <= walk_hi)]))
    shake_energy = float(np.sum(spectrum[(freqs > shake_lo) & (freqs <= shake_hi)]))
    scaled_min = config.shake_energy_min * (n / float(config.shake_reference_samples))
    return shake_energy > config.shake_energy_ratio * walk_energy and shake_energy > scaled_min


def _keep_regular_runs(
    peaks: list[int],
    timestamps: npt.NDArray[np.float64],
    config: StepDetectorConfig,
) -> list[int]:
    """Só fica o pico que pertence a uma série com intervalo de passada.

    A cadência é medida contra o último pico ainda candidato, e a série
    curta (1–2 picos) sai fora. É o que barra o toque isolado no celular
    parado, que o refratário sozinho deixava passar.
    """
    if not peaks:
        return []
    runs: list[list[int]] = [[peaks[0]]]
    for peak in peaks[1:]:
        dt = float(timestamps[peak] - timestamps[runs[-1][-1]])
        if config.min_step_interval_s - 1e-3 <= dt <= config.max_step_interval_s + 1e-3:
            runs[-1].append(peak)
        else:
            runs.append([peak])
    kept: list[int] = []
    for run in runs:
        if len(run) >= config.min_consecutive_steps:
            kept.extend(run)
    return kept
