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
        gyro_magnitude: npt.NDArray[np.float64] | None = None
    ) -> list[StepEvent]:
        raise NotImplementedError


class PeakStepDetector(StepDetector):
    def __init__(self, sample_rate_hz: float = 50.0, weinberg_k: float = 0.48) -> None:
        self._sample_rate = sample_rate_hz
        self._k = weinberg_k

    def detect(
        self, 
        timestamps: npt.NDArray[np.float64], 
        filtered_magnitude: npt.NDArray[np.float64],
        gyro_magnitude: npt.NDArray[np.float64] | None = None
    ) -> list[StepEvent]:
        n_samples = len(filtered_magnitude)
        if n_samples < int(self._sample_rate * 0.8):  # Requer pelo menos ~0.8s de dados
            return []

        # ------------------------------------------------------------------
        # TRAVA 1: ANÁLISE FREQUENCIAL (FFT)
        # Caminhada humana tem pico de energia entre 1.0Hz e 2.8Hz.
        # Chacoalhado de mão joga a energia para acima de 3.5Hz.
        # ------------------------------------------------------------------
        fft_vals = np.abs(np.fft.rfft(filtered_magnitude - np.mean(filtered_magnitude)))
        fft_freqs = np.fft.rfftfreq(n_samples, d=1.0 / self._sample_rate)

        # Energia na faixa da caminhada (1.0 Hz - 2.8 Hz)
        walk_band_mask = (fft_freqs >= 1.0) & (fft_freqs <= 2.8)
        walk_energy = np.sum(fft_vals[walk_band_mask])

        # Energia na faixa do chacoalhado (> 3.5 Hz)
        shake_band_mask = (fft_freqs > 3.5) & (fft_freqs <= 15.0)
        shake_energy = np.sum(fft_vals[shake_band_mask])

        if shake_energy > (1.3 * walk_energy) and shake_energy > 15.0:
            # O sinal é predominantemente vibração/chacoalhado de alta frequência
            return []

        # ------------------------------------------------------------------
        # TRAVA 2: FILTRO DE JERK (Taxa de variação da aceleração: da/dt)
        # Chacoalhar gera variações bruscas em milissegundos.
        # ------------------------------------------------------------------
        dt = 1.0 / self._sample_rate
        jerk = np.abs(np.diff(filtered_magnitude)) / dt
        mean_jerk = float(np.mean(jerk))

        # Se a média do Jerk for muito alta, é chacoalhada vigorosa
        if mean_jerk > 42.0:
            return []

        # ------------------------------------------------------------------
        # TRAVA 3: GIROSCÓPIO GLOBAL (Se a API do navegador forneceu os dados)
        # ------------------------------------------------------------------
        if gyro_magnitude is not None and len(gyro_magnitude) == n_samples:
            if float(np.mean(gyro_magnitude)) > 1.6:  # Rotação contínua de pulso
                return []

        # ------------------------------------------------------------------
        # LOCALIZAÇÃO DE PICOS (CAMINHADA REAL)
        # ------------------------------------------------------------------
        std_amplitude = float(np.std(filtered_magnitude))
        if std_amplitude < 0.75:  # Telefone parado ou em repouso
            return []

        mean_amplitude = float(np.mean(filtered_magnitude))
        
        # Mínimo de 360ms entre passos (máximo de ~166 passos por minuto)
        min_distance = int(0.36 * self._sample_rate) 

        dynamic_height = max(11.0, mean_amplitude + 0.7)
        min_prominence = max(1.1, 0.38 * std_amplitude)
        
        candidate_peaks, _ = find_peaks(
            filtered_magnitude, 
            distance=min_distance, 
            height=dynamic_height,
            prominence=min_prominence
        )

        steps: list[StepEvent] = []
        
        for i, peak_idx in enumerate(candidate_peaks):
            peak_val = filtered_magnitude[peak_idx]

            # Trava de aceleração máxima humana (Picos > 16.0 m/s² são chacoalhadas bruscas)
            if peak_val > 16.0:
                continue

            # Trava de Jerk Local no pico
            p_start = max(0, peak_idx - 2)
            p_end = min(len(jerk), peak_idx + 2)
            if float(np.max(jerk[p_start:p_end])) > 75.0:
                continue

            # Trava de Giroscópio Local no pico
            if gyro_magnitude is not None and len(gyro_magnitude) == n_samples:
                w_start = max(0, peak_idx - min_distance // 2)
                w_end = min(n_samples, peak_idx + min_distance // 2)
                if float(np.max(gyro_magnitude[w_start:w_end])) > 1.4:
                    continue

            # Janela de análise de amplitude (Weinberg)
            window_start = max(0, peak_idx - min_distance // 2)
            window_end = min(n_samples, peak_idx + min_distance // 2)
            
            a_max = np.max(filtered_magnitude[window_start:window_end])
            a_min = np.min(filtered_magnitude[window_start:window_end])
            acc_diff = float(a_max - a_min)

            if not (2.1 <= acc_diff <= 8.0):
                continue

            t_current = timestamps[peak_idx]
            cadence = (60.0 / (t_current - timestamps[candidate_peaks[i - 1]])) if i > 0 else 0.0

            raw_step_length = self._k * (acc_diff ** 0.25)
            step_length = float(np.clip(raw_step_length, 0.45, 1.00))

            steps.append(
                StepEvent(
                    timestamp=t_current, 
                    index=peak_idx, 
                    cadence_spm=cadence, 
                    step_length_m=step_length
                )
            )
            
        return steps