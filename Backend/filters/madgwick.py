"""
madgwick.py

Etapa 7 — Fusão sensorial via algoritmo de Madgwick.

Teoria
------
O filtro de Madgwick estima orientação combinando:
    - Integração do giroscópio: resposta rápida, mas acumula deriva
      (drift) ao longo do tempo, pois cada pequeno erro de leitura é
      somado indefinidamente pela integração.
    - Um passo de correção por gradiente descendente que ajusta a
      orientação estimada para que o vetor de gravidade (do acelerômetro)
      e o vetor de campo magnético (do magnetômetro) predito pela
      orientação atual fiquem consistentes com o que os sensores
      efetivamente mediram.

O resultado é uma orientação que responde rápido a movimentos (graças ao
giroscópio) mas não deriva indefinidamente (graças à correção contínua
por acelerômetro + magnetômetro).

Implementação: em vez de reimplementar o algoritmo do zero, usamos a
biblioteca `ahrs` (explicitamente permitida na lista de dependências),
que já contém uma implementação de referência, validada, do artigo
original de Madgwick (2010). Este módulo é apenas um adaptador (wrapper)
que a expõe atrás da interface `AttitudeEstimator` do projeto — assim,
`pdr/pdr.py` não precisa saber que a implementação vem do `ahrs`.
"""

from __future__ import annotations
import numpy as np

from ahrs.filters import Madgwick as _AhrsMadgwick  #type: ignore

from filters.quaternion import Quaternion
from .attitude_estimator import AttitudeEstimator


class MadgwickAttitudeEstimator(AttitudeEstimator):
    """Estimador de orientação baseado no algoritmo de Madgwick (via `ahrs`)."""

    def __init__(self, gain: float = 0.033) -> None:
        """
        Args:
            gain: ganho do filtro (beta, no artigo original). Valores
                maiores dão mais peso à correção por
                acelerômetro/magnetômetro (menos deriva, porém mais
                sensível a acelerações não-gravitacionais); valores
                menores confiam mais no giroscópio (mais suave, porém
                mais deriva). 0.033 é o valor recomendado pela
                biblioteca `ahrs` para uso geral.
        """
        self._gain = gain
        self._orientation = Quaternion.identity()

    @property
    def current_orientation(self) -> Quaternion:
        return self._orientation

    def update(
        self,
        gx: float, gy: float, gz: float,
        ax: float, ay: float, az: float,
        mx: float, my: float, mz: float,
        dt: float,
    ) -> Quaternion:
        """Atualiza a orientação com uma nova amostra de giroscópio +
        acelerômetro + magnetômetro, usando o algoritmo MARG de Madgwick."""
        madgwick = _AhrsMadgwick(gain=self._gain, Dt=dt)
        q_updated = madgwick.updateMARG(
            q=self._orientation.to_array(),
            gyr=[gx, gy, gz],
            acc=[ax, ay, az],
            mag=[mx, my, mz],
        )
        self._orientation = Quaternion.from_array(q_updated).normalized()
        return self._orientation

    def update_imu(
        self,
        gx: float, gy: float, gz: float,
        ax: float, ay: float, az: float,
        dt: float,
    ) -> Quaternion:
        """Fusão só com giroscópio e acelerômetro.

        O ``mag_*`` gravado pelo recorder é alpha/beta/gamma da orientação,
        não o campo magnético. Passar zeros para o MARG (ou esses ângulos)
        não estima heading absoluto e pode contaminar a vertical. O modo IMU
        é o que os sensores realmente disponíveis sustentam.
        """
        if dt <= 0:
            dt = 1e-3
        madgwick = _AhrsMadgwick(gain=self._gain, Dt=dt)
        q_updated = madgwick.updateIMU(
            q=self._orientation.to_array(),
            gyr=[gx, gy, gz],
            acc=[ax, ay, az],
        )
        self._orientation = Quaternion.from_array(q_updated).normalized()
        return self._orientation

    def update_series(self, samples: list) -> list[Quaternion]:
        """Processa uma série de amostras temporalmente e atualiza a orientação passo a passo."""
        quaternions: list[Quaternion] = []
        timestamps = np.array([s.timestamp for s in samples], dtype=np.float64)
        positive_dt = np.diff(timestamps)
        positive_dt = positive_dt[positive_dt > 0]
        # Primeira amostra (e timestamps repetidos) reutilizam a mediana real.
        # 0,02 s só entra se a série inteira não tiver um único dt válido.
        fallback_dt = float(np.median(positive_dt)) if positive_dt.size else 0.02

        for i in range(len(samples)):
            s = samples[i]

            # 1. Calcula o delta de tempo (dt) entre a amostra atual e a anterior
            if i == 0:
                dt = fallback_dt
            else:
                dt = s.timestamp - samples[i - 1].timestamp
                # Proteção caso haja timestamps iguais ou com erro no CSV
                if dt <= 0:
                    dt = fallback_dt

            q_current = self.update(
                gx=s.gx, gy=s.gy, gz=s.gz,
                ax=s.ax,   ay=s.ay,   az=s.az,
                mx=s.mx,   my=s.my,   mz=s.mz,
                dt=dt
            )
            
            quaternions.append(q_current)
            
        return quaternions