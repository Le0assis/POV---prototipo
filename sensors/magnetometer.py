
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator
import pandas as pd 

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MagnetometerReading:
    """Uma leitura bruta e isolada do magnetômetro.

    Attributes:
        timestamp: instante da leitura, em segundos.
        mx, my, mz: campo magnético nos eixos X, Y, Z, em microtesla (µT).
    """

    timestamp: float
    mx: float
    my: float
    mz: float


class MagnetometerReader(ABC):
    """Interface (porta) para qualquer fonte de dados do magnetômetro."""

    @abstractmethod
    def read(self) -> Iterator[MagnetometerReading]:
        """Retorna um iterador de leituras do magnetômetro, em ordem
        cronológica crescente de timestamp."""
        raise NotImplementedError


class CSVMagnetometerReader(MagnetometerReader):
    """Lê amostras do magnetômetro a partir de um arquivo CSV."""

    def __init__(
        self,
        filepath: str | Path,
        timestamp_col: str = "timestamp",
        mx_col: str = "mx",
        my_col: str = "my",
        mz_col: str = "mz",
    ) -> None:
        """
        Args:
            filepath: caminho do arquivo CSV com os dados do magnetômetro.
            timestamp_col: nome da coluna de timestamp (em segundos).
            mx_col, my_col, mz_col: nomes das colunas de campo magnético.
        """
        self._filepath = Path(filepath)
        self._timestamp_col = timestamp_col
        self._mx_col = mx_col
        self._my_col = my_col
        self._mz_col = mz_col

    def read(self) -> Iterator[MagnetometerReading]:
        """Lê o CSV e produz uma leitura por linha.

        Raises:
            FileNotFoundError: se o arquivo não existir.
            ValueError: se alguma coluna obrigatória estiver ausente.
        """
        if not self._filepath.exists():
            raise FileNotFoundError(
                f"Arquivo de dados do magnetômetro não encontrado: {self._filepath}"
            )

        logger.info("Lendo dados do magnetômetro de %s", self._filepath)
        df = pd.read_csv(self._filepath)

        required_cols = {self._timestamp_col, self._mx_col, self._my_col, self._mz_col}
        missing = required_cols - set(df.columns)
        if missing:
            raise ValueError(f"Colunas ausentes no CSV do magnetômetro: {missing}")

        df = df.sort_values(by=self._timestamp_col)

        for _, row in df.iterrows():
            yield MagnetometerReading(
                timestamp=float(row[self._timestamp_col]),
                mx=float(row[self._mx_col]),
                my=float(row[self._my_col]),
                mz=float(row[self._mz_col]),
            )
