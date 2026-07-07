"""
steps.py

Teoria
------
Um "passo" físico gera um impacto que se traduz em um pico na magnitude
da aceleração filtrada. Usamos a detecção de picos para encontrar o 
instante de cada impacto.

A cadência (passos por minuto) é o inverso do delta de tempo entre passos.
O comprimento do passo (Step Length) é estimado pelo Modelo de Weinberg,
que relaciona a amplitude do pico de aceleração (A_max - A_min) com o 
tamanho físico da passada.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from scipy.signal import find_peaks  # type: ignore


@dataclass(frozen=True, slots=True)
class StepEvent:
    """Dados de um único passo detectado no sinal."""
    timestamp: float
    index: int               # Índice no array do sinal onde o passo ocorreu
    cadence_spm: float       # Passos por minuto (Steps Per Minute)
    step_length_m: float     # Comprimento estimado do passo em metros


class StepDetector(ABC):
    """Interface para algoritmos de detecção e modelagem de passos."""
    
    @abstractmethod
    def detect(
        self, timestamps: npt.NDArray[np.float64], filtered_magnitude: npt.NDArray[np.float64]
    ) -> list[StepEvent]:
        """Detecta passos em uma série temporal de aceleração filtrada."""
        raise NotImplementedError


class PeakStepDetector(StepDetector):
    """Detecção via picos (scipy) com modelo de comprimento de Weinberg."""

    def __init__(self, sample_rate_hz: float, weinberg_k: float = 0.55) -> None:
        """
        Args:
            sample_rate_hz: Taxa de amostragem do sensor.
            weinberg_k: Constante de calibração do modelo de Weinberg. 
                Varia com o usuário, geralmente entre 0.4 e 0.55.
        """
        self._sample_rate = sample_rate_hz
        self._k = weinberg_k

    def detect(
        self, timestamps: npt.NDArray[np.float64], filtered_magnitude: npt.NDArray[np.float64]
    ) -> list[StepEvent]:
        # Estima a distância mínima entre passos baseado na taxa de amostragem (~0.3 segundos)
        min_distance = int(0.3 * self._sample_rate)
        
        # MUDANÇA AQUI: Dinâmico em vez de fixo em 10.5
        # Se o sinal estiver na casa dos 9.8 m/s², ele vai detectar. 
        # Se for um dataset simulado flutuando perto de 1.0, ele se adapta!
        mean_amplitude = np.mean(filtered_magnitude)
        std_amplitude = np.std(filtered_magnitude)
        
        # O limiar vira a média mais uma fração do desvio padrão (ajustável)
        dynamic_height = mean_amplitude + (0.2 * std_amplitude)
        
        # Executa a busca de picos do scipy
        peaks, _ = find_peaks(filtered_magnitude, distance=min_distance, height=dynamic_height)
        
        steps: list[StepEvent] = []
        for i, peak_idx in enumerate(peaks):
            t_current = timestamps[peak_idx]
            cadence = 0.0 if i == 0 else (60.0 / (t_current - timestamps[peaks[i - 1]]))
            
            window_start = peaks[i - 1] if i > 0 else max(0, peak_idx - min_distance)
            window_end = min(len(filtered_magnitude), peak_idx + min_distance)
            
            a_max = np.max(filtered_magnitude[window_start:window_end])
            a_min = np.min(filtered_magnitude[window_start:window_end])
            step_length = self._k * ((a_max - a_min) ** 0.25)

            steps.append(StepEvent(timestamp=t_current, index=peak_idx, cadence_spm=cadence, step_length_m=step_length))
        return steps