"""
tracker.py

Etapa 9 (Extração de Yaw) e Etapa 15 (Integração e Trajetória).

Teoria
------
O PDR (Pedestrian Dead Reckoning) é um sistema iterativo. Dado um 
ponto inicial (X0, Y0, Z0), cada novo passo desloca o usuário no mapa.

Usamos trigonometria básica para projetar o vetor:
    X_novo = X_anterior + comprimento_do_passo * cos(yaw)
    Y_novo = Y_anterior + comprimento_do_passo * sin(yaw)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from filters.quaternion import Quaternion
from pdr.steps import StepEvent


@dataclass(frozen=True, slots=True)
class PDRPosition:
    """Posição espacial (Dead Reckoning) em um dado instante."""
    timestamp: float
    x: float
    y: float
    z: float  # Altitude


class TrajectoryTracker:
    """Mantém o estado da trajetória e integra novos passos no mapa."""

    def __init__(self, start_x: float = 0.0, start_y: float = 0.0, start_z: float = 0.0) -> None:
        self._current_x = start_x
        self._current_y = start_y
        self._current_z = start_z
        self._trajectory: list[PDRPosition] = []

    @property
    def trajectory(self) -> list[PDRPosition]:
        """Retorna o histórico completo da trajetória calculada."""
        return self._trajectory.copy()

    def apply_step(self, step: StepEvent, orientation: Quaternion, altitude_m: float) -> PDRPosition:
        """Processa um novo passo, atualizando a posição no mundo.
        
        Args:
            step: O evento do passo detectado (contém timestamp e comprimento).
            orientation: O Quaternion de orientação exato no momento do passo.
            altitude_m: A altitude (em metros) calculada via barômetro no momento do passo.
            
        Returns:
            A nova posição (X, Y, Z) calculada.
        """
        # Etapa 9: Extrair o Yaw (guinada) a partir do quaternion
        _, _, yaw_rad = orientation.to_euler()

        # Etapa 15: Integração Trigonométrica (Vetor Deslocamento)
        self._current_x += step.step_length_m * math.cos(yaw_rad)
        self._current_y += step.step_length_m * math.sin(yaw_rad)
        self._current_z = altitude_m  # A altitude é absoluta, não acumula

        new_pos = PDRPosition(
            timestamp=step.timestamp,
            x=self._current_x,
            y=self._current_y,
            z=self._current_z,
        )
        
        self._trajectory.append(new_pos)
        return new_pos