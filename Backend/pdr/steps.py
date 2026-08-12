"""
steps.py — Detecção Adaptativa de Passos com Filtro de Jerk, FFT e Giroscópio
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from scipy.signal import find_peaks  # type: ignore


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
        sample_rate_hz: float | None = None
    ) -> list[StepEvent]:
        raise NotImplementedError


class PeakStepDetector(StepDetector):
    def __init__(self, sample_rate_hz: float = 30.0, weinberg_k: float = 0.48) -> None:
        self._sample_rate = sample_rate_hz
        self._k = weinberg_k

    def detect(
        self, 
        timestamps: npt.NDArray[np.float64], 
        filtered_magnitude: npt.NDArray[np.float64],
        gyro_magnitude: npt.NDArray[np.float64] | None = None,
        sample_rate_hz: float | None = None
    ) -> list[StepEvent]:
        n_samples = len(filtered_magnitude)
        if n_samples < 15:
            return []

        # ------------------------------------------------------------------
        # CÁLCULO DA TAXA DE AMOSTRAGEM REAL (VIA TIMESTAMPS)
        # ------------------------------------------------------------------
        if sample_rate_hz and sample_rate_hz > 0:
            sr = sample_rate_hz
        else:
            time_span = timestamps[-1] - timestamps[0]
            if time_span > 0:
                sr = float((n_samples - 1) / time_span)
            else:
                sr = self._sample_rate

        # Trava para manter sr dentro de limites aceitáveis de celulares
        sr = float(np.clip(sr, 10.0, 100.0))

        # ------------------------------------------------------------------
        # TRAVA 1: ANÁLISE FREQUENCIAL (FFT)
        # ------------------------------------------------------------------
        fft_vals = np.abs(np.fft.rfft(filtered_magnitude - np.mean(filtered_magnitude)))
        fft_freqs = np.fft.rfftfreq(n_samples, d=1.0 / sr)

        # Energia na faixa da caminhada humana (0.8 Hz - 3.0 Hz)
        walk_band_mask = (fft_freqs >= 0.8) & (fft_freqs <= 3.0)
        walk_energy = np.sum(fft_vals[walk_band_mask])

        # Energia na faixa do chacoalhado (> 4.0 Hz)
        shake_band_mask = (fft_freqs > 4.0) & (fft_freqs <= 15.0)
        shake_energy = np.sum(fft_vals[shake_band_mask])

        if shake_energy > (2.5 * walk_energy) and shake_energy > 30.0:
            return []

        # ------------------------------------------------------------------
        # TRAVA 2: FILTRO DE JERK (Taxa de variação com dt real)
        # ------------------------------------------------------------------
        dt = 1.0 / sr
        jerk = np.abs(np.diff(filtered_magnitude)) / dt
        mean_jerk = float(np.mean(jerk))

        # Limite de Jerk ajustado para taxa real
        if mean_jerk > 90.0:
            return []

        # ------------------------------------------------------------------
        # TRAVA 3: GIROSCÓPIO GLOBAL (Tolerante ao balanço natural do braço)
        # ------------------------------------------------------------------
        if gyro_magnitude is not None and len(gyro_magnitude) == n_samples:
            if float(np.mean(gyro_magnitude)) > 3.8:  # Permite movimento de caminhada normal
                return []

        # ------------------------------------------------------------------
        # LOCALIZAÇÃO DE PICOS
        # ------------------------------------------------------------------
        std_amplitude = float(np.std(filtered_magnitude))
        if std_amplitude < 0.35:  # Telefone totalmente parado
            return []

        mean_amplitude = float(np.mean(filtered_magnitude))
        
        # Mínimo de ~330ms entre passos humanos
        min_distance = max(1, int(0.33 * sr)) 

        # Limiares de picos redefinidos para detectar caminhadas suaves
        dynamic_height = max(10.2, mean_amplitude + 0.3)
        min_prominence = max(0.4, 0.25 * std_amplitude)
        
        candidate_peaks, _ = find_peaks(
            filtered_magnitude, 
            distance=min_distance, 
            height=dynamic_height,
            prominence=min_prominence
        )

        steps: list[StepEvent] = []
        
        for i, peak_idx in enumerate(candidate_peaks):
            peak_val = filtered_magnitude[peak_idx]

            # Trava de aceleração máxima (sacudidas violentas > 20.0 m/s²)
            if peak_val > 20.0:
                continue

            # Trava de Jerk Local no pico
            p_start = max(0, peak_idx - 2)
            p_end = min(len(jerk), peak_idx + 2)
            if float(np.max(jerk[p_start:p_end])) > 150.0:
                continue

            # Trava de Giroscópio Local no pico (Permite até 4.5 rad/s)
            if gyro_magnitude is not None and len(gyro_magnitude) == n_samples:
                w_start = max(0, peak_idx - min_distance // 2)
                w_end = min(n_samples, peak_idx + min_distance // 2)
                if float(np.max(gyro_magnitude[w_start:w_end])) > 4.5:
                    continue

            # Janela de variação de amplitude (Weinberg)
            window_start = max(0, peak_idx - min_distance // 2)
            window_end = min(n_samples, peak_idx + min_distance // 2)
            
            a_max = np.max(filtered_magnitude[window_start:window_end])
            a_min = np.min(filtered_magnitude[window_start:window_end])
            acc_diff = float(a_max - a_min)

            # Permite passadas mais leves (partindo de 1.1 m/s²)
            if not (1.1 <= acc_diff <= 10.0):
                continue

            t_current = timestamps[peak_idx]
            cadence = (60.0 / (t_current - timestamps[candidate_peaks[i - 1]])) if i > 0 else 0.0

            raw_step_length = self._k * (acc_diff ** 0.25)
            step_length = float(np.clip(raw_step_length, 0.40, 1.00))

            steps.append(
                StepEvent(
                    timestamp=t_current, 
                    index=peak_idx, 
                    cadence_spm=cadence, 
                    step_length_m=step_length
                )
            )
            
        return steps