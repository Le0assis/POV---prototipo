"""
altitude.py

Teoria
------
A pressão atmosférica diminui conforme a altitude aumenta. Usamos a
fórmula barométrica internacional para estimar a altitude relativa
(em metros) a partir da pressão medida pelo barômetro (em hPa).

Como o objetivo do PDR em ambientes internos é detectar mudança de
andares (escadas/elevadores), focamos na variação de altitude em relação
a uma pressão de referência inicial (pressão no térreo ou andar de início).
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
from typing import overload, Sequence


@overload
def compute_altitude(pressure_hpa: float, reference_pressure: float = 1013.25) -> float: ...
@overload
def compute_altitude(
    pressure_hpa: npt.NDArray[np.float64] | Sequence[float], 
    reference_pressure: float = 1013.25
) -> npt.NDArray[np.float64]: ...

def compute_altitude(
    pressure_hpa: float | npt.NDArray[np.float64] | Sequence[float],
    reference_pressure: float = 1013.25,
) -> float | npt.NDArray[np.float64]:
    """Calcula a altitude em metros a partir da pressão atmosférica.

    Args:
        pressure_hpa: Pressão medida no instante atual (hPa).
        reference_pressure: Pressão de referência no "nível zero" 
            (por padrão 1013.25 hPa, nível do mar).
            
    Returns:
        A altitude estimada em metros.
    """
    p_arr = np.asarray(pressure_hpa, dtype=np.float64)
    
    # Fórmula Barométrica
    altitude = 44330.0 * (1.0 - (p_arr / reference_pressure) ** (1 / 5.255))

    if altitude.ndim == 0:
        return float(altitude)
    return altitude