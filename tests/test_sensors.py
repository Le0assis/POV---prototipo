"""
test_sensors.py

Testes unitários da Etapa 1 (Leitura dos Sensores).

Usa `unittest` (biblioteca padrão do Python) em vez de um framework
externo como pytest, para manter o projeto restrito às dependências
explicitamente permitidas (numpy, scipy, pandas, matplotlib, ahrs,
typing, dataclasses, logging, pathlib).

Como rodar:
    python -m unittest tests.test_sensors -v
    (a partir da raiz do projeto IndoorIPS/)
"""

import unittest
from pathlib import Path

from sensors.sensor_sample import SensorSample
from sensors.accelerometer import AccelerometerReading, CSVAccelerometerReader
from sensors.gyroscope import GyroscopeReading, CSVGyroscopeReader
from sensors.magnetometer import MagnetometerReading, CSVMagnetometerReader
from sensors.barometer import BarometerReading, CSVBarometerReader

DATASET_PATH = Path(__file__).parent.parent / "datasets" / "sample_walk.csv"


class TestSensorSample(unittest.TestCase):
    """Testes da estrutura de dados SensorSample."""

    def test_creation_with_valid_values(self) -> None:
        sample = SensorSample(
            timestamp=0.0,
            ax=0.1, ay=0.2, az=9.8,
            gx=0.01, gy=0.02, gz=0.03,
            mx=20.0, my=-5.0, mz=-40.0,
            pressure=1013.25,
        )
        self.assertEqual(sample.timestamp, 0.0)
        self.assertEqual(sample.pressure, 1013.25)

    def test_is_immutable(self) -> None:
        """Uma SensorSample não pode ser alterada após a criação (frozen)."""
        sample = SensorSample(
            timestamp=0.0, ax=0, ay=0, az=9.8,
            gx=0, gy=0, gz=0, mx=0, my=0, mz=0, pressure=1013.25,
        )
        with self.assertRaises(AttributeError):
            sample.ax = 5.0  # type: ignore[misc]

    def test_rejects_non_positive_pressure(self) -> None:
        with self.assertRaises(ValueError):
            SensorSample(
                timestamp=0.0, ax=0, ay=0, az=9.8,
                gx=0, gy=0, gz=0, mx=0, my=0, mz=0, pressure=-1.0,
            )

    def test_from_component_readings_combines_correctly(self) -> None:
        acc = AccelerometerReading(timestamp=1.0, ax=0.1, ay=0.2, az=9.8)
        gyro = GyroscopeReading(timestamp=1.01, gx=0.01, gy=0.02, gz=0.03)
        mag = MagnetometerReading(timestamp=1.02, mx=20.0, my=-5.0, mz=-40.0)
        baro = BarometerReading(timestamp=1.0, pressure=1013.25)

        sample = SensorSample.from_component_readings(acc, gyro, mag, baro)

        self.assertEqual(sample.timestamp, 1.0)
        self.assertEqual(sample.ax, 0.1)
        self.assertEqual(sample.gz, 0.03)
        self.assertEqual(sample.mx, 20.0)
        self.assertEqual(sample.pressure, 1013.25)

    def test_from_component_readings_rejects_desynchronized_data(self) -> None:
        acc = AccelerometerReading(timestamp=1.0, ax=0.1, ay=0.2, az=9.8)
        gyro = GyroscopeReading(timestamp=5.0, gx=0.01, gy=0.02, gz=0.03)  # muito atrasado
        mag = MagnetometerReading(timestamp=1.02, mx=20.0, my=-5.0, mz=-40.0)
        baro = BarometerReading(timestamp=1.0, pressure=1013.25)

        with self.assertRaises(ValueError):
            SensorSample.from_component_readings(acc, gyro, mag, baro)


class TestCSVAccelerometerReader(unittest.TestCase):
    """Testes do leitor de acelerômetro baseado em CSV."""

    def test_reads_all_rows_from_dataset(self) -> None:
        reader = CSVAccelerometerReader(DATASET_PATH)
        readings = list(reader.read())
        self.assertEqual(len(readings), 500)
        self.assertIsInstance(readings[0], AccelerometerReading)

    def test_readings_are_sorted_by_timestamp(self) -> None:
        reader = CSVAccelerometerReader(DATASET_PATH)
        readings = list(reader.read())
        timestamps = [r.timestamp for r in readings]
        self.assertEqual(timestamps, sorted(timestamps))

    def test_raises_for_missing_file(self) -> None:
        reader = CSVAccelerometerReader("arquivo_que_nao_existe.csv")
        with self.assertRaises(FileNotFoundError):
            list(reader.read())


class TestCSVGyroscopeReader(unittest.TestCase):
    """Testes do leitor de giroscópio baseado em CSV."""

    def test_reads_all_rows_from_dataset(self) -> None:
        reader = CSVGyroscopeReader(DATASET_PATH)
        readings = list(reader.read())
        self.assertEqual(len(readings), 500)
        self.assertIsInstance(readings[0], GyroscopeReading)

    def test_degree_to_radian_conversion(self) -> None:
        """Se input_in_degrees=True, os valores devem ser convertidos
        (180 graus/s deve virar aproximadamente pi rad/s)."""
        import tempfile
        import pandas as pd
        import math

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            pd.DataFrame({
                "timestamp": [0.0], "gx": [180.0], "gy": [0.0], "gz": [0.0],
            }).to_csv(f.name, index=False)
            reader = CSVGyroscopeReader(f.name, input_in_degrees=True)
            reading = next(reader.read())
            self.assertAlmostEqual(reading.gx, math.pi, places=4)


class TestCSVMagnetometerReader(unittest.TestCase):
    """Testes do leitor de magnetômetro baseado em CSV."""

    def test_reads_all_rows_from_dataset(self) -> None:
        reader = CSVMagnetometerReader(DATASET_PATH)
        readings = list(reader.read())
        self.assertEqual(len(readings), 500)
        self.assertIsInstance(readings[0], MagnetometerReading)


class TestCSVBarometerReader(unittest.TestCase):
    """Testes do leitor de barômetro baseado em CSV."""

    def test_reads_all_rows_from_dataset(self) -> None:
        reader = CSVBarometerReader(DATASET_PATH)
        readings = list(reader.read())
        self.assertEqual(len(readings), 500)
        self.assertIsInstance(readings[0], BarometerReading)
        self.assertTrue(all(r.pressure > 0 for r in readings))


if __name__ == "__main__":
    unittest.main()
