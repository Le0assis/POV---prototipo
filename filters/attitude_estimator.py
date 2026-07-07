"""
attitude_estimator.py

Interface comum para qualquer algoritmo de fusão sensorial que estime
orientação (atitude) a partir de acelerômetro + giroscópio (+
magnetômetro). Permite trocar Madgwick por outro algoritmo (ex.: filtro
complementar, Mahony) sem alterar o restante do pipeline — mesmo
princípio de troca fácil já aplicado a `SignalFilter` e `StepDetector`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from filters.quaternion import Quaternion


class AttitudeEstimator(ABC):
    """Interface para um estimador de orientação (atitude) baseado em
    fusão sensorial."""

    @abstractmethod
    def update(
        self,
        gx: float, gy: float, gz: float,
        ax: float, ay: float, az: float,
        mx: float, my: float, mz: float,
        dt: float,
    ) -> Quaternion:
        """Atualiza a estimativa de orientação com uma nova amostra e
        retorna o quaternion resultante.

        Args:
            gx, gy, gz: velocidade angular (rad/s).
            ax, ay, az: aceleração linear (m/s²).
            mx, my, mz: campo magnético (µT).
            dt: intervalo de tempo desde a última atualização (segundos).

        Returns:
            O quaternion de orientação atualizado.
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def current_orientation(self) -> Quaternion:
        """Retorna a última orientação estimada, sem recalcular nada."""
        raise NotImplementedError