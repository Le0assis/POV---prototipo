"""
repository.py

Define a interface para fontes de dados do sistema PDR.
Garante que o pipeline principal não dependa de arquivos físicos ou bancos de dados específicos.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from .sensor_sample import SensorSample
from .accelerometer import CSVAccelerometerReader
from .gyroscope import CSVGyroscopeReader
from .magnetometer import CSVMagnetometerReader
from .barometer import CSVBarometerReader


class SensorDataRepository(ABC):
    """Interface abstrata (contrato) para fornecer amostras de sensores."""

    @abstractmethod
    def get_samples(self) -> list[SensorSample]:
        """Recupera e retorna a lista de SensorSample sincronizadas."""
        raise NotImplementedError


class CSVSensorRepository(SensorDataRepository):
    """Implementação que busca os dados a partir de arquivos CSV mistos."""

    def __init__(self, filepath: Path, timestamp_tolerance: float = 0.05) -> None:
        self._filepath = filepath
        self._tolerance = timestamp_tolerance

    def get_samples(self) -> list[SensorSample]:
        print(f"[Repo] Carregando dados do CSV: {self._filepath.name}")
        
        acc_reader = CSVAccelerometerReader(self._filepath)
        gyro_reader = CSVGyroscopeReader(self._filepath)
        mag_reader = CSVMagnetometerReader(self._filepath)
        baro_reader = CSVBarometerReader(self._filepath)
        
        samples: list[SensorSample] = []
        
        # O zip consome as linhas em paralelo de forma eficiente
        readers_zip = zip(
            acc_reader.read(), 
            gyro_reader.read(), 
            mag_reader.read(), 
            baro_reader.read()
        )
        
        for acc, gyro, mag, baro in readers_zip:
            sample = SensorSample.from_component_readings(
                acc=acc, gyro=gyro, mag=mag, baro=baro,
                timestamp_tolerance=self._tolerance
            )
            samples.append(sample)
            
        print(f"[Repo] Sincronização concluída. {len(samples)} amostras prontas.")
        return samples


# EXEMPLO FUTURO: Se você mudar para Banco de Dados, bastará criar isso em outro arquivo:
# class DatabaseSensorRepository(SensorDataRepository):
#     def __init__(self, connection_string: str) -> None: ...
#     def get_samples(self) -> list[SensorSample]:
#         # Faz o SELECT no banco, monta os objetos SensorSample e retorna a lista.