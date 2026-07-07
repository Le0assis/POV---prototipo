"""
quaternion.py

Etapa 7/8 — Representação de orientação via quaternion.

Teoria
------
Um quaternion unitário q = [w, x, y, z] representa uma rotação 3D sem
sofrer de "gimbal lock" (perda de um grau de liberdade que ocorre com
ângulos de Euler quando dois eixos se alinham). Por isso, algoritmos de
fusão sensorial (Madgwick, Mahony, filtro complementar) trabalham
internamente com quaternions, e só convertem para ângulos de Euler
(roll/pitch/yaw) no final, quando um humano ou uma camada de aplicação
(aqui, `pdr/heading.py`) precisa de um número interpretável.

Convenção adotada: q = [w, x, y, z] (parte escalar primeiro), a mesma
convenção usada pela biblioteca `ahrs`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True, slots=True)
class Quaternion:
    """Quaternion unitário representando uma orientação 3D.

    Attributes:
        w: parte escalar (real).
        x, y, z: parte vetorial (imaginária).
    """

    w: float
    x: float
    y: float
    z: float

    @classmethod
    def identity(cls) -> "Quaternion":
        """Quaternion identidade (nenhuma rotação): w=1, x=y=z=0."""
        return cls(1.0, 0.0, 0.0, 0.0)

    @classmethod
    def from_array(cls, arr: npt.ArrayLike) -> "Quaternion":
        """Cria um Quaternion a partir de um array/sequência [w, x, y, z]."""
        np_arr = np.atleast_1d(arr).astype(np.float64)
        if np_arr.size != 4:
            raise ValueError("O array deve conter exatamente 4 elementos [w, x, y, z].")
        w, x, y, z = np_arr
        return cls(float(w), float(x), float(y), float(z))

    @classmethod
    def from_euler(cls, roll: float, pitch: float, yaw: float) -> "Quaternion":
        """Cria um Quaternion a partir de ângulos de Euler (radianos),
        convenção aeroespacial ZYX (yaw-pitch-roll) — inverso de `to_euler`.
        """
        cr, sr = np.cos(roll / 2), np.sin(roll / 2)
        cp, sp = np.cos(pitch / 2), np.sin(pitch / 2)
        cy, sy = np.cos(yaw / 2), np.sin(yaw / 2)

        return cls(
            w=float(cr * cp * cy + sr * sp * sy),
            x=float(sr * cp * cy - cr * sp * sy),
            y=float(cr * sp * cy + sr * cp * sy),
            z=float(cr * cp * sy - sr * sp * cy),
        )

    def to_array(self) -> npt.NDArray[np.float64]:
        """Converte para um array numpy [w, x, y, z]."""
        return np.array([self.w, self.x, self.y, self.z], dtype=np.float64)

    def normalized(self) -> "Quaternion":
        """Retorna uma cópia normalizada (norma unitária).

        Necessário porque erros de ponto flutuante acumulados ao longo de
        muitas atualizações do filtro de fusão podem fazer a norma do
        quaternion se afastar ligeiramente de 1.
        """
        norm = np.linalg.norm(self.to_array())
        if norm == 0:
            raise ValueError("Não é possível normalizar um quaternion nulo.")
        w, x, y, z = self.to_array() / norm
        return Quaternion(w, x, y, z)

    def conjugate(self) -> "Quaternion":
        """Conjugado do quaternion: [w, -x, -y, -z].

        Para um quaternion unitário, o conjugado é igual ao inverso e
        representa a rotação oposta.
        """
        return Quaternion(self.w, -self.x, -self.y, -self.z)

    def multiply(self, other: "Quaternion") -> "Quaternion":
        """Produto de Hamilton entre dois quaternions (self ⊗ other).

        A composição de rotações é feita via multiplicação de
        quaternions, não por soma — assim como matrizes de rotação são
        compostas por multiplicação, não soma.
        """
        w1, x1, y1, z1 = self.w, self.x, self.y, self.z
        w2, x2, y2, z2 = other.w, other.x, other.y, other.z
        return Quaternion(
            w=w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
            x=w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            y=w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            z=w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        )

    def to_euler(self) -> tuple[float, float, float]:
        """Converte o quaternion para ângulos de Euler (roll, pitch, yaw),
        em radianos, na convenção aeroespacial ZYX (yaw-pitch-roll).

        Returns:
            Tupla (roll, pitch, yaw) em radianos.
        """
        w, x, y, z = self.w, self.x, self.y, self.z

        # Roll (rotação em torno do eixo X)
        sinr_cosp = 2 * (w * x + y * z)
        cosr_cosp = 1 - 2 * (x * x + y * y)
        roll = np.arctan2(sinr_cosp, cosr_cosp)

        # Pitch (rotação em torno do eixo Y) — usa clip para evitar
        # domain error do arcsin por pequenos erros de ponto flutuante
        # quando sin(pitch) fica ligeiramente fora de [-1, 1].
        sinp = 2 * (w * y - z * x)
        pitch = np.arcsin(np.clip(sinp, -1.0, 1.0))

        # Yaw (rotação em torno do eixo Z, vertical) — é o ângulo que
        # o PDR usa para projetar cada passo no plano horizontal.
        siny_cosp = 2 * (w * z + x * y)
        cosy_cosp = 1 - 2 * (y * y + z * z)
        yaw = np.arctan2(siny_cosp, cosy_cosp)

        return float(roll), float(pitch), float(yaw)