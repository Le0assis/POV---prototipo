"""
signal_filter.py

Interface comum a todos os filtros de sinal (Etapa 3), garantindo que
qualquer filtro possa ser trocado por outro sem alterar o código que o
utiliza — exatamente o requisito "possibilidade de trocar facilmente por
outros filtros" do enunciado (Open/Closed Principle).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
import numpy.typing as npt


class SignalFilter(ABC):
    """Interface para um filtro de sinal unidimensional."""

    @abstractmethod
    def apply(self, signal: npt.ArrayLike) -> npt.NDArray[np.float64]:
        """Aplica o filtro a um sinal e retorna o sinal filtrado, com o
        mesmo comprimento da entrada."""
        raise NotImplementedError