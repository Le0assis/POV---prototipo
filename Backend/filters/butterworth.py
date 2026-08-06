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


class ButterworthLowPassFilter(SignalFilter):
    """Filtro Butterworth passa-baixa aplicado em ambos os sentidos
    (zero-phase), via `scipy.signal.filtfilt`.
    """

    def __init__(self, cutoff_hz: float, sample_rate_hz: float, order: int = 4) -> None:
        """
        Args:
            cutoff_hz: frequência de corte, em Hz (ex.: 3 Hz para
                caminhada humana normal, já com margem de segurança acima
                da cadência típica de 1.5-2.5 Hz).
            sample_rate_hz: taxa de amostragem do sinal de entrada, em Hz.
            order: ordem do filtro. Ordens mais altas têm transição mais
                abrupta na banda de corte, mas podem introduzir
                instabilidade numérica se altas demais; 4 é um valor
                seguro e comum para este tipo de sinal.
        """
        if cutoff_hz >= sample_rate_hz / 2:
            raise ValueError(
                f"cutoff_hz ({cutoff_hz}) deve ser menor que a frequência "
                f"de Nyquist ({sample_rate_hz / 2} Hz)."
            )
        self._cutoff_hz = cutoff_hz
        self._sample_rate_hz = sample_rate_hz
        self._order = order

        nyquist = sample_rate_hz / 2.0
        normalized_cutoff = cutoff_hz / nyquist
        self._b, self._a = butter(order, normalized_cutoff, btype="low", analog=False)

    def apply(self, signal: npt.ArrayLike) -> npt.NDArray[np.float64]:
        """Aplica o filtro Butterworth passa-baixa (zero-phase) ao sinal.

        Args:
            signal: sinal de entrada (ex.: série temporal de magnitude
                da aceleração).

        Returns:
            Sinal filtrado, com o mesmo tamanho da entrada.
        """
        signal_arr = np.asarray(signal, dtype=np.float64)
        min_len_required = 3 * (max(len(self._a), len(self._b)) - 1)
        if len(signal_arr) <= min_len_required:
            raise ValueError(
                f"Sinal curto demais ({len(signal_arr)} amostras) para "
                f"filtfilt com esta ordem de filtro (mínimo: "
                f"{min_len_required + 1} amostras)."
            )
        return filtfilt(self._b, self._a, signal_arr)