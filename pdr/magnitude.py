"""
magnitude.py

Etapa 2 — Magnitude da aceleração.

Teoria
------
A magnitude do vetor aceleração:

    |A| = sqrt(Ax² + Ay² + Az²)

é usada em vez dos componentes brutos (Ax, Ay, Az) para a detecção de
passos (Etapa 4) porque é INVARIANTE À ORIENTAÇÃO do smartphone. Não
importa se o usuário segura o celular na mão, no bolso ou preso ao braço:
a norma do vetor aceleração não depende de como os eixos do dispositivo
estão alinhados com o corpo — apenas a distribuição entre Ax/Ay/Az muda,
não o módulo total.

Esta função é deliberadamente pura e desacoplada de `SensorSample`: recebe
e devolve apenas números/arrays, sem conhecer a existência de sensores,
CSVs ou qualquer outra camada do sistema. Isso facilita testá-la de forma
isolada e reaproveitá-la em qualquer contexto (ex.: diretamente com dados
simulados em um notebook).
"""

from __future__ import annotations

from typing import Sequence, overload

import numpy as np
import numpy.typing as npt


@overload
def compute_acceleration_magnitude(ax: float, ay: float, az: float) -> float: ...
@overload
def compute_acceleration_magnitude(
    ax: npt.NDArray[np.float64] | Sequence[float], 
    ay: npt.NDArray[np.float64] | Sequence[float], 
    az: npt.NDArray[np.float64] | Sequence[float]
) -> npt.NDArray[np.float64]: ...

def compute_acceleration_magnitude(ax, ay, az):
    """Calcula a magnitude do vetor aceleração: sqrt(ax² + ay² + az²).

    Aceita tanto escalares (float) quanto sequências/arrays, permitindo
    uso tanto amostra-a-amostra quanto vetorizado (para uma sessão
    inteira de dados).

    Args:
        ax, ay, az: componentes da aceleração (m/s²), escalares ou arrays
            do mesmo tamanho.

    Returns:
        A magnitude da aceleração, no mesmo formato de entrada (float se
        a entrada foi escalar, np.ndarray se foi um array/sequência).
    """
    ax_arr = np.asarray(ax, dtype=np.float64)
    ay_arr = np.asarray(ay, dtype=np.float64)
    az_arr = np.asarray(az, dtype=np.float64)

    magnitude = np.sqrt(ax_arr**2 + ay_arr**2 + az_arr**2)

    # Se a entrada era escalar, devolve um float puro em vez de um
    # array 0-dimensional do numpy (mais previsível para quem consome).
    if magnitude.ndim == 0:
        return float(magnitude)
    return magnitude


def compute_magnitude_series(samples: Sequence) -> npt.NDArray[np.float64]:
    """Calcula a magnitude da aceleração para uma sequência de SensorSample.

    Conveniência para o caso mais comum: extrair a série temporal de
    magnitude a partir de uma lista de amostras já sincronizadas.

    Args:
        samples: sequência de objetos com atributos `.ax`, `.ay`, `.az`
            (tipicamente `SensorSample`, mas não há import direto do
            pacote `sensors` aqui — duck typing mantém este módulo
            desacoplado da camada de leitura de sensores).

    Returns:
        Array numpy com a magnitude de cada amostra, na mesma ordem.
    """
    ax = np.array([s.ax for s in samples], dtype=np.float64)
    ay = np.array([s.ay for s in samples], dtype=np.float64)
    az = np.array([s.az for s in samples], dtype=np.float64)
    return compute_acceleration_magnitude(ax, ay, az)