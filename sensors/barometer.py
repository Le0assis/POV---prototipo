"""
barometer.py

Responsável EXCLUSIVAMENTE pela leitura dos dados do barômetro
(pressão atmosférica). Não conhece acelerômetro, giroscópio ou
magnetômetro.

Teoria
------
O barômetro mede a pressão atmosférica em hectopascal (hPa). Sozinho, não
diz nada sobre posição (x, y) — mas variações de pressão se traduzem em
variações de ALTITUDE (ver Etapa 10, fórmula barométrica internacional):

    Altitude = 44330 × (1 − (P / P0)^0.1903)

onde P0 é a pressão de referência ao nível do sensor (calibrada no início
da sessão). No contexto de um IPS, o barômetro não estima elevação
absoluta com precisão (isso exigiria uma estação de referência), mas é
excelente para detectar VARIAÇÕES relativas de pressão — o suficiente
para inferir que o usuário subiu ou desceu um andar (Etapa 10), o que é
uma informação valiosa para o mapa e para o roteamento.

Nota: a taxa de amostragem do barômetro costuma ser muito mais baixa
(tipicamente 1-10 Hz) que a do acelerômetro/giroscópio (50-100 Hz). Isso
será relevante na sincronização feita em `SensorSample.from_component_readings`.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BarometerReading:
    """Uma leitura bruta e isolada do barômetro.

    Attributes:
        timestamp: instante da leitura, em segundos.
        pressure: pressão atmosférica, em hectopascal (hPa).
    """

    timestamp: float
    pressure: float

    def __post_init__(self) -> None:
        """Valida que a pressão lida é fisicamente plausível (fail fast)."""
        if self.pressure <= 0:
            raise ValueError(
                f"Pressão inválida: {self.pressure} hPa. Deve ser positiva."
            )


class BarometerReader(ABC):
    """Interface (porta) para qualquer fonte de dados do barômetro."""

    @abstractmethod
    def read(self) -> Iterator[BarometerReading]:
        """Retorna um iterador de leituras do barômetro, em ordem
        cronológica crescente de timestamp."""
        raise NotImplementedError


class CSVBarometerReader(BarometerReader):
    """Lê amostras do barômetro a partir de um arquivo CSV."""

    def __init__(
        self,
        filepath: str | Path,
        timestamp_col: str = "timestamp",
        pressure_col: str = "pressure",
    ) -> None:
        """
        Args:
            filepath: caminho do arquivo CSV com os dados do barômetro.
            timestamp_col: nome da coluna de timestamp (em segundos).
            pressure_col: nome da coluna de pressão (em hPa).
        """
        self._filepath = Path(filepath)
        self._timestamp_col = timestamp_col
        self._pressure_col = pressure_col

    def read(self) -> Iterator[BarometerReading]:
        """Lê o CSV e produz uma leitura por linha.

        Raises:
            FileNotFoundError: se o arquivo não existir.
            ValueError: se alguma coluna obrigatória estiver ausente.
        """
        if not self._filepath.exists():
            raise FileNotFoundError(
                f"Arquivo de dados do barômetro não encontrado: {self._filepath}"
            )

        logger.info("Lendo dados do barômetro de %s", self._filepath)
        df = pd.read_csv(self._filepath)

        required_cols = {self._timestamp_col, self._pressure_col}
        missing = required_cols - set(df.columns)
        if missing:
            raise ValueError(f"Colunas ausentes no CSV do barômetro: {missing}")

        df = df.sort_values(by=self._timestamp_col)

        for _, row in df.iterrows():
            yield BarometerReading(
                timestamp=float(row[self._timestamp_col]),
                pressure=float(row[self._pressure_col]),
            )
