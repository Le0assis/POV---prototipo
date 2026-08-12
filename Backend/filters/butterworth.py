"""
butterworth.py

Etapa 3 — Filtro Butterworth passa-baixa.

Teoria
------
O sinal bruto de aceleração contém ruído de alta frequência (vibração do
sensor, tremor da mão) sobreposto ao sinal de interesse (o padrão
periódico do passo, tipicamente entre 0.5-3 Hz para caminhada humana).

Um filtro Butterworth passa-baixa é escolhido por ter resposta em
frequência MAXIMALMENTE PLANA na banda de passagem (sem ondulação, ao
contrário de Chebyshev/elíptico) — ou seja, não distorce a amplitude do
sinal de interesse, apenas atenua as frequências acima do corte.

Usamos `filtfilt` (filtragem bidirecional) em vez de `lfilter`: aplicar o
filtro para frente e para trás cancela o deslocamento de fase (phase lag)
que um filtro IIR normalmente introduz. Isso é importante aqui porque um
atraso de fase deslocaria no tempo o pico de cada passo, prejudicando a
precisão da detecção (Etapa 4) e do cálculo de cadência (Etapa 5).
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
from scipy.signal import butter, filtfilt  # type: ignore

from .signal_filter import SignalFilter # type: ignore

import numpy as np
import numpy.typing as npt
from scipy.signal import butter, filtfilt

class ButterworthLowPassFilter:
    """Filtro Butterworth passa-baixa adaptativo (zero-phase) para PDR."""

    def __init__(self, cutoff_hz: float = 2.2, sample_rate_hz: float = 30.0, order: int = 2) -> None:
        self._cutoff_hz = cutoff_hz
        self._sample_rate_hz = sample_rate_hz
        self._order = order

    def apply(self, signal: npt.ArrayLike, sample_rate_hz: float | None = None) -> npt.NDArray[np.float64]:
        signal_arr = np.asarray(signal, dtype=np.float64)
        
        # Usa a taxa informada na chamada ou a taxa padrão do construtor
        sr = sample_rate_hz if (sample_rate_hz is not None and sample_rate_hz > 0) else self._sample_rate_hz
        
        # 1. Proteção contra sinais muito curtos (retorna o sinal bruto sem quebrar)
        min_samples = 3 * self._order + 1
        if len(signal_arr) < min_samples:
            return signal_arr

        # 2. Ajuste dinâmico de Nyquist (evita o ValueError)
        nyquist = sr / 2.0
        # Mantém a frequência de corte sempre abaixo de 90% da frequência de Nyquist
        safe_cutoff = min(self._cutoff_hz, nyquist * 0.9)

        # Se a frequência útil for muito baixa, retorna o sinal original
        if safe_cutoff <= 0.1:
            return signal_arr

        normalized_cutoff = safe_cutoff / nyquist

        # 3. Re-calcula coeficientes com a frequência real do lote recebido
        b, a = butter(self._order, normalized_cutoff, btype="low", analog=False)

        try:
            return filtfilt(b, a, signal_arr)
        except Exception:
            # Fallback seguro caso ocorra qualquer instabilidade numérica no Scipy
            return signal_arr