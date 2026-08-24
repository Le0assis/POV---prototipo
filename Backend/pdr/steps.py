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
        
        
        # TRAVA 1: DESVIO PADRÃO MÁXIMO (BARRAGEM DIRETA DE CHACOALHO)
        # ------------------------------------------------------------------
        std_amplitude = float(np.std(filtered_magnitude))
        if std_amplitude < 0.35:   # Telefone parado
            return []
        if std_amplitude > 3.8:    # Chacoalho manual violento/médio
            return []

        # ------------------------------------------------------------------
        # TRAVA 2: ANÁLISE FREQUENCIAL (FFT COM FAIXA DE SHAKE REAJUSTADA)
        # ------------------------------------------------------------------
        fft_vals = np.abs(np.fft.rfft(filtered_magnitude - np.mean(filtered_magnitude)))
        fft_freqs = np.fft.rfftfreq(n_samples, d=1.0 / sr)

        walk_band_mask = (fft_freqs >= 0.8) & (fft_freqs <= 2.8)
        walk_energy = np.sum(fft_vals[walk_band_mask])

        # Pega a faixa de 3.2 Hz a 15.0 Hz onde o chacoalho humano se concentra
        shake_band_mask = (fft_freqs > 3.2) & (fft_freqs <= 15.0)
        shake_energy = np.sum(fft_vals[shake_band_mask])

        if shake_energy > (1.5 * walk_energy) and shake_energy > 18.0:
            return []

        # ------------------------------------------------------------------
        # TRAVA 3: JERK GLOBAL E GIROSCÓPIO GLOBAL
        # ------------------------------------------------------------------
        dt = 1.0 / sr
        jerk = np.abs(np.diff(filtered_magnitude)) / dt
        mean_jerk = float(np.mean(jerk))

        if mean_jerk > 50.0:  # Reduzido de 90.0
            return []

        if gyro_magnitude is not None and len(gyro_magnitude) == n_samples:
            if float(np.mean(gyro_magnitude)) > 2.8:  # Reduzido de 3.8
                return []

        # ------------------------------------------------------------------
        # LOCALIZAÇÃO E FILTRAGEM DE PICOS
        # ------------------------------------------------------------------
        mean_amplitude = float(np.mean(filtered_magnitude))
        min_distance = max(1, int(0.33 * sr)) 

        dynamic_height = max(10.3, mean_amplitude + 0.35)
        min_prominence = max(0.45, 0.30 * std_amplitude)
        
        candidate_peaks, _ = find_peaks(
            filtered_magnitude, 
            distance=min_distance, 
            height=dynamic_height,
            prominence=min_prominence
        )

        steps: list[StepEvent] = []
        
        for i, peak_idx in enumerate(candidate_peaks):
            peak_val = filtered_magnitude[peak_idx]

            if peak_val > 15.5:  # Reduzido de 20.0
                continue

            # Jerk Local no pico
            p_start = max(0, peak_idx - 2)
            p_end = min(len(jerk), peak_idx + 2)
            if float(np.max(jerk[p_start:p_end])) > 65.0:  # Reduzido de 150.0
                continue

            # Giroscópio Local no pico
            if gyro_magnitude is not None and len(gyro_magnitude) == n_samples:
                w_start = max(0, peak_idx - min_distance // 2)
                w_end = min(n_samples, peak_idx + min_distance // 2)
                if float(np.max(gyro_magnitude[w_start:w_end])) > 3.0:  # Reduzido de 4.5
                    continue

            # Variação de Amplitude (Weinberg)
            window_start = max(0, peak_idx - min_distance // 2)
            window_end = min(n_samples, peak_idx + min_distance // 2)
            
            a_max = np.max(filtered_magnitude[window_start:window_end])
            a_min = np.min(filtered_magnitude[window_start:window_end])
            acc_diff = float(a_max - a_min)

            # Faixa restrita para passada real
            if not (1.2 <= acc_diff <= 5.0):  # Reduzido limite superior de 10.0 para 5.0
                continue

            t_current = timestamps[peak_idx]
            cadence = (60.0 / (t_current - timestamps[candidate_peaks[i - 1]])) if i > 0 else 0.0

            raw_step_length = self._k * (acc_diff ** 0.25)
            step_length = float(np.clip(raw_step_length, 0.40, 0.95))

            steps.append(
                StepEvent(
                    timestamp=t_current, 
                    index=peak_idx, 
                    cadence_spm=cadence, 
                    step_length_m=step_length
                )
            )
            
        return steps