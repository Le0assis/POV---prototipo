"""
Pacote `sensors`.

Responsável exclusivamente pela LEITURA dos sensores inerciais e ambiental
do smartphone (acelerômetro, giroscópio, magnetômetro, barômetro).

Este pacote não conhece filtros, detecção de passos, fusão sensorial ou
qualquer lógica de PDR — apenas a aquisição e estruturação dos dados brutos.
Essa separação segue o Single Responsibility Principle (SRP).
"""

from .sensor_sample import SensorSample
from .accelerometer import AccelerometerReading, AccelerometerReader, CSVAccelerometerReader
from .gyroscope import GyroscopeReading, GyroscopeReader, CSVGyroscopeReader
from .magnetometer import MagnetometerReading, MagnetometerReader, CSVMagnetometerReader
from .barometer import BarometerReading, BarometerReader, CSVBarometerReader

__all__ = [
    "SensorSample",
    "AccelerometerReading",
    "AccelerometerReader",
    "CSVAccelerometerReader",
    "GyroscopeReading",
    "GyroscopeReader",
    "CSVGyroscopeReader",
    "MagnetometerReading",
    "MagnetometerReader",
    "CSVMagnetometerReader",
    "BarometerReading",
    "BarometerReader",
    "CSVBarometerReader",
]
