
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AccelerometerReading:
    """Uma leitura bruta e isolada do acelerômetro.

    Attributes:
        timestamp: instante da leitura, em segundos.
        ax, ay, az: aceleração linear nos eixos X, Y, Z, em m/s².
    """

    timestamp: float
    ax: float
    ay: float
    az: float


class AccelerometerReader(ABC):
    """Interface (porta) para qualquer fonte de dados do acelerômetro.

    Este é o ponto de extensão da arquitetura (Open/Closed Principle):
    hoje implementamos a leitura a partir de um CSV gravado
    (`CSVAccelerometerReader`), mas no futuro pode-se implementar uma
    leitura ao vivo (ex.: via app de streaming de sensores, socket,
    WebSocket, BLE) apenas criando uma nova classe que implemente esta
    mesma interface — nenhum código que já depende de
    `AccelerometerReader` precisa mudar.
    """

    @abstractmethod
    def read(self) -> Iterator[AccelerometerReading]:
        """Retorna um iterador de leituras do acelerômetro, em ordem
        cronológica crescente de timestamp."""
        raise NotImplementedError


class CSVAccelerometerReader(AccelerometerReader):
    """Lê amostras do acelerômetro a partir de um arquivo CSV.

    Os nomes das colunas são configuráveis para acomodar diferentes apps
    de coleta de dados (ex.: Sensor Logger, Physics Toolbox Sensor Suite),
    que usam convenções de nome distintas.
    """

    def __init__(
        self,
        filepath: str | Path,
        timestamp_col: str = "timestamp",
        ax_col: str = "ax",
        ay_col: str = "ay",
        az_col: str = "az",
    ) -> None:
        """
        Args:
            filepath: caminho do arquivo CSV com os dados do acelerômetro.
            timestamp_col: nome da coluna de timestamp (em segundos).
            ax_col, ay_col, az_col: nomes das colunas de aceleração.
        """
        self._filepath = Path(filepath)
        self._timestamp_col = timestamp_col
        self._ax_col = ax_col
        self._ay_col = ay_col
        self._az_col = az_col

    def read(self) -> Iterator[AccelerometerReading]:
        """Lê o CSV e produz uma leitura por linha, em ordem crescente
        de timestamp.

        Raises:
            FileNotFoundError: se o arquivo não existir.
            ValueError: se alguma coluna obrigatória estiver ausente.
        """
        if not self._filepath.exists():
            raise FileNotFoundError(
                f"Arquivo de dados do acelerômetro não encontrado: {self._filepath}"
            )

        logger.info("Lendo dados do acelerômetro de %s", self._filepath)
        df = pd.read_csv(self._filepath)

        required_cols = {self._timestamp_col, self._ax_col, self._ay_col, self._az_col}
        missing = required_cols - set(df.columns)
        if missing:
            raise ValueError(f"Colunas ausentes no CSV do acelerômetro: {missing}")

        df = df.sort_values(by=self._timestamp_col)

        for _, row in df.iterrows():
            yield AccelerometerReading(
                timestamp=float(row[self._timestamp_col]),
                ax=float(row[self._ax_col]),
                ay=float(row[self._ay_col]),
                az=float(row[self._az_col]),
            )
