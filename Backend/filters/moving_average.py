"""
moving_average.py

Etapa 3 — Filtro de média móvel (moving average).

Teoria
------
A média móvel é o filtro passa-baixa mais simples possível: substitui
cada ponto pela média de uma janela de `window_size` amostras ao redor
dele. É computacionalmente mais barato que o Butterworth e mais fácil de
entender/depurar, mas tem uma resposta em frequência muito menos nítida
(atenua menos as frequências indesejadas próximas ao corte). É incluído
aqui como alternativa mais simples, demonstrando a arquitetura plugável:
trocar `ButterworthLowPassFilter` por `MovingAverageFilter` em qualquer
lugar do pipeline não exige nenhuma outra mudança de código, pois ambos
implementam `SignalFilter`.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from filters.signal_filter import SignalFilter


class MovingAverageFilter(SignalFilter):
    """Filtro de média móvel centrada, com padding por reflexão nas bordas."""

    def __init__(self, window_size: int) -> None:
        """
        Args:
            window_size: tamanho da janela (número de amostras). Deve ser
                um inteiro positivo; janelas ímpares centralizam melhor o
                filtro (evitam deslocamento de fase de meia-amostra).
        """
        if window_size < 1:
            raise ValueError(f"window_size deve ser >= 1, recebido: {window_size}")
        self._window_size = window_size

    def apply(self, signal: npt.ArrayLike) -> npt.NDArray[np.float64]:
        """Aplica a média móvel centrada ao sinal.

        Usa `mode="reflect"` no padding das bordas para evitar que os
        primeiros/últimos pontos do sinal sejam artificialmente puxados
        para zero (o que aconteceria com padding por zeros).
        """
        signal_arr = np.asarray(signal, dtype=np.float64)
        if self._window_size > len(signal_arr):
            raise ValueError(
                f"window_size ({self._window_size}) maior que o sinal "
                f"({len(signal_arr)} amostras)."
            )

        half = self._window_size // 2
        padded = np.pad(signal_arr, pad_width=half, mode="reflect")
        kernel = np.ones(self._window_size) / self._window_size
        smoothed = np.convolve(padded, kernel, mode="valid")

        # Garante o mesmo comprimento da entrada mesmo com window_size par.
        return smoothed[: len(signal_arr)]