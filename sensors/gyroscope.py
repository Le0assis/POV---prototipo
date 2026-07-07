
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GyroscopeReading:
    """Uma leitura bruta e isolada do giroscópio.

    Attributes:
        timestamp: instante da leitura, em segundos.
        gx, gy, gz: velocidade angular nos eixos X, Y, Z, em rad/s.
    """

    timestamp: float
    gx: float
    gy: float
    gz: float


class GyroscopeReader(ABC):
    """Interface (porta) para qualquer fonte de dados do giroscópio.

    Assim como `AccelerometerReader`, permite trocar a fonte de dados
    (CSV gravado hoje, streaming ao vivo amanhã) sem alterar o restante
    do sistema (Open/Closed Principle).
    """

    @abstractmethod
    def read(self) -> Iterator[GyroscopeReading]:
        """Retorna um iterador de leituras do giroscópio, em ordem
        cronológica crescente de timestamp."""
        raise NotImplementedError


class CSVGyroscopeReader(GyroscopeReader):
    """Lê amostras do giroscópio a partir de um arquivo CSV."""

    def __init__(
        self,
        filepath: str | Path,
        timestamp_col: str = "timestamp",
        gx_col: str = "gx",
        gy_col: str = "gy",
        gz_col: str = "gz",
        input_in_degrees: bool = False,
    ) -> None:
        """
        Args:
            filepath: caminho do arquivo CSV com os dados do giroscópio.
            timestamp_col: nome da coluna de timestamp (em segundos).
            gx_col, gy_col, gz_col: nomes das colunas de velocidade angular.
            input_in_degrees: se True, converte os valores lidos de
                graus/s para rad/s (necessário para alguns apps de coleta
                que exportam nessa unidade).
        """
        self._filepath = Path(filepath)
        self._timestamp_col = timestamp_col
        self._gx_col = gx_col
        self._gy_col = gy_col
        self._gz_col = gz_col
        self._input_in_degrees = input_in_degrees

    def read(self) -> Iterator[GyroscopeReading]:
        """Lê o CSV e produz uma leitura por linha, já convertida para
        rad/s se necessário.

        Raises:
            FileNotFoundError: se o arquivo não existir.
            ValueError: se alguma coluna obrigatória estiver ausente.
        """
        if not self._filepath.exists():
            raise FileNotFoundError(
                f"Arquivo de dados do giroscópio não encontrado: {self._filepath}"
            )

        logger.info("Lendo dados do giroscópio de %s", self._filepath)
        df = pd.read_csv(self._filepath)

        required_cols = {self._timestamp_col, self._gx_col, self._gy_col, self._gz_col}
        missing = required_cols - set(df.columns)
        if missing:
            raise ValueError(f"Colunas ausentes no CSV do giroscópio: {missing}")

        df = df.sort_values(by=self._timestamp_col)

        for _, row in df.iterrows():
            gx, gy, gz = float(row[self._gx_col]), float(row[self._gy_col]), float(row[self._gz_col])
            if self._input_in_degrees:
                gx, gy, gz = np.radians([gx, gy, gz])
            yield GyroscopeReading(
                timestamp=float(row[self._timestamp_col]),
                gx=float(gx), gy=float(gy), gz=float(gz),
            )
