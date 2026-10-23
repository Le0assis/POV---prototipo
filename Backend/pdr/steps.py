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
com intervalo estável. Duas passadas calmas separadas do resto por uma
hesitação curta também ficam: o giro local ainda é de caminhada, não
de chacoalho.
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
    # Mínimo de amostras de um segmento contínuo. Não é a trava do POST.
    min_samples: int = 15
    # Trava do POST /api/edges/process-raw. Exposta como min_samples na API.
    min_request_samples: int = 20
    weinberg_exponent: float = 0.25
    step_length_default_m: float = 0.70
    snap_end_window_m: float = 1.5
    edge_match_tolerance_rad: float = 0.524

    # Abaixo disso o sinal já não traz a gravidade (foi high-pass). O teto
    # absoluto de 10,3 m/s² só faz sentido com a gravidade dentro.
    gravity_present_above: float = 8.0


def pdr_config_payload(config: StepDetectorConfig | None = None) -> dict:
    """Contrato de ``GET /api/pdr/config``. Valores saem de ``StepDetectorConfig``."""
    config = config or StepDetectorConfig()
    return {
        "status": "success",
        "version": "m02-1",
        "min_samples": config.min_request_samples,
        "step_length": {
            "model": "weinberg",
            "k": config.weinberg_k,
            "exponent": config.weinberg_exponent,
            "min_m": config.step_length_min_m,
            "max_m": config.step_length_max_m,
            "default_m": config.step_length_default_m,
        },
        "step_detection": {
            "min_step_interval_s": config.min_step_interval_s,
            "max_step_interval_s": config.max_step_interval_s,
            "lowpass_cutoff_hz": config.lowpass_cutoff_hz,
        },
        "heading": {
            "unit": "rad",
            "direction": "ccw",
            "reference": "relativo; recalibrar a cada checkpoint",
        },
        "localization": {
            "method": "projecao_por_distancia_acumulada",
            "snap_end_window_m": config.snap_end_window_m,
            "edge_match_tolerance_rad": config.edge_match_tolerance_rad,
        },
    }


@dataclass(frozen=True, slots=True)
class StepEvent:
    timestamp: float
    index: int
    cadence_spm: float
    step_length_m: float
    # Heading anti-horário relativo à pose no início da gravação. O detector
    # deixa 0; o pipeline preenche com o yaw do Madgwick menos o yaw inicial.
    heading_rad: float = 0.0


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
        # Fica na assinatura. ``detect`` mede a taxa pelos timestamps.
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
        # Não entra no cálculo: a taxa declarada mudava refratário e FFT.
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

        candidates, calm = self._candidate_indices(signal, time, gyro, sample_rate)
        accepted = _keep_regular_runs(candidates, time, self._config, calm)
        return self._events_from_indices(accepted, signal, time, sample_rate)

    def _candidate_indices(
        self,
        signal: npt.NDArray[np.float64],
        time: npt.NDArray[np.float64],
        gyro: npt.NDArray[np.float64] | None,
        sample_rate: float,
    ) -> tuple[list[int], set[int]]:
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
        calm: set[int] = set()
        for index, (peak, prominence) in enumerate(zip(peaks, prominences, strict=False)):
            peak = int(peak)
            own_swing = _bilateral_swing(signal, peaks, index, sample_rate, config)
            if self._peak_is_step(
                peak,
                float(prominence),
                signal,
                gyro,
                jerk,
                sample_rate,
                min_distance,
                gravity_present,
                own_swing,
            ):
                accepted.append(peak)
                if _peak_gyro_is_calm(gyro, peak, signal, sample_rate, min_distance, config):
                    calm.add(peak)
        return accepted, calm

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
        own_swing: float,
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

        prominence_limit = max(config.min_prominence_abs, config.prominence_std_factor * window_std)
        if prominence < prominence_limit:
            return False

        # Giro e jerk locais: rejeitam o pico, não o resto da gravação.
        # Média da janela acima de 2,8 rad/s é manuseio. Um pico de giro
        # na passada (braço, ~3–4 rad/s) com a média ainda baixa fica:
        # o teto que corta esse pico é o do processor (7,5), não o 3,0.
        # O 3,0 continua na decisão de impacto e do par calmo.
        if gyro is not None:
            if gyro_mean > config.max_mean_gyro or gyro_mean > config.gyro_mean_limit:
                return False
            if gyro_max_local > config.gyro_peak_limit:
                return False
        if local_jerk > config.max_local_jerk and gyro_max_local > config.max_local_gyro:
            return False

        if gravity_present:
            height_limit = max(config.min_height_abs, window_mean + config.height_offset)
        else:
            height_limit = window_mean + config.height_offset
        # O piso absoluto fica. Aceitar pico abaixo de 10,3 por proeminência
        # somava dois picos de arranque (9,8–10,1) numa caminhada curta do
        # Chrome e passava de 8 para 10. No Sensor Logger isso custava um
        # pico interior (30→29), ainda dentro de 5%.
        if float(signal[peak]) < height_limit:
            return False

        # O meio-refratário (±0,16 s) não alcança o vale de uma passada
        # de ~0,7 s. ``own_swing`` cobre esse vale, mas só se a janela
        # curta já viu quase o Δa mínimo: a folga é ``height_offset``
        # (0,35). Abaixo disso o bilateral está pegando o vizinho ou o
        # fim da gravação — no Chrome, um bump a 0,4 s do final com
        # Δa local 0,81 virava o sexto passo de uma contagem de 4.
        acc_diff = float(np.max(signal[step_lo:step_hi]) - np.min(signal[step_lo:step_hi]))
        local_floor = max(0.0, config.acc_diff_min - config.height_offset)
        if acc_diff < config.acc_diff_min and not (
            own_swing >= config.acc_diff_min and acc_diff >= local_floor
        ):
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


def _bilateral_swing(
    signal: npt.NDArray[np.float64],
    peaks: npt.NDArray[np.int64],
    index: int,
    sample_rate: float,
    config: StepDetectorConfig,
) -> float:
    """Subida do pico acima do vale mais alto dos dois lados.

    O olhar vai no máximo até metade de ``max_step_interval_s`` (0,6 s)
    e para no meio do caminho até o pico vizinho. Não usa o fundo de uma
    pausa nem a excursão do passo ao lado.
    """
    peak = int(peaks[index])
    n = len(signal)
    look = max(1, int(round(0.5 * config.max_step_interval_s * sample_rate)))
    left_peak = int(peaks[index - 1]) if index else None
    right_peak = int(peaks[index + 1]) if index + 1 < len(peaks) else None
    left_bound = 0 if left_peak is None else (left_peak + peak) // 2
    right_bound = n - 1 if right_peak is None else (right_peak + peak) // 2
    left_bound = max(left_bound, peak - look)
    right_bound = min(right_bound, peak + look)
    left_min = float(np.min(signal[left_bound:peak + 1]))
    right_min = float(np.min(signal[peak:right_bound + 1]))
    return float(signal[peak]) - max(left_min, right_min)


def _peak_gyro_is_calm(
    gyro: npt.NDArray[np.float64] | None,
    peak: int,
    signal: npt.NDArray[np.float64],
    sample_rate: float,
    min_distance: int,
    config: StepDetectorConfig,
) -> bool:
    """Giro de caminhada, não de chacoalho, na janela do pico."""
    n = len(signal)
    half_step = max(1, min_distance // 2)
    step_lo = max(0, peak - half_step)
    step_hi = min(n, peak + half_step + 1)
    win = max(8, int(round(config.analysis_window_s * sample_rate)))
    half_win = win // 2
    win_lo = max(0, peak - half_win)
    win_hi = min(n, peak + half_win + 1)
    gyro_mean, gyro_max_local, _ = _gyro_stats(gyro, win_lo, win_hi, step_lo, step_hi)
    return gyro_max_local <= config.max_local_gyro and gyro_mean <= config.max_mean_gyro


def _keep_regular_runs(
    peaks: list[int],
    timestamps: npt.NDArray[np.float64],
    config: StepDetectorConfig,
    calm: set[int] | None = None,
) -> list[int]:
    """Só fica o pico que pertence a uma série com intervalo de passada.

    A cadência é medida contra o último pico ainda candidato, e a série
    curta (1 pico, ou 2 com giro de manuseio) sai fora. É o que barra o
    toque isolado no celular parado, que o refratário sozinho deixava
    passar. Duas passadas com giro local ainda abaixo de ``max_local_gyro``
    sobrevivem a uma hesitação: no começo da caminhada isso são passos,
    no chacoalho o giro local passa de 3 rad/s e o par cai.
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
    calm_peaks = calm or set()
    for run in runs:
        if len(run) >= config.min_consecutive_steps:
            kept.extend(run)
        elif len(run) == 2 and all(peak in calm_peaks for peak in run):
            kept.extend(run)
    return kept
