"""
example_sensors.py

Exemplo de uso do pacote `sensors` (Etapa 1).

Demonstra:
    1. Leitura independente de cada sensor a partir do dataset sintético.
    2. Combinação (zip) das quatro leituras em uma lista de SensorSample.
    3. Inspeção básica dos dados (primeira e última amostra).

Como rodar (a partir da raiz do projeto IndoorIPS/):
    python examples/example_sensors.py
"""

import logging
from pathlib import Path

from sensors.sensor_sample import SensorSample
from sensors.accelerometer import CSVAccelerometerReader
from sensors.gyroscope import CSVGyroscopeReader
from sensors.magnetometer import CSVMagnetometerReader
from sensors.barometer import CSVBarometerReader

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

DATASET_PATH = Path(__file__).parent.parent / "datasets" / "sample_walk.csv"


def main() -> None:
    # 1. Cada sensor é lido de forma independente, sem que um módulo
    #    conheça o outro (Single Responsibility Principle).
    acc_readings = list(CSVAccelerometerReader(DATASET_PATH).read())
    gyro_readings = list(CSVGyroscopeReader(DATASET_PATH).read())
    mag_readings = list(CSVMagnetometerReader(DATASET_PATH).read())
    baro_readings = list(CSVBarometerReader(DATASET_PATH).read())

    print(f"\nLeituras carregadas: {len(acc_readings)} amostras por sensor.\n")

    # 2. Combina as quatro leituras (aqui, no mesmo CSV, os timestamps
    #    já são idênticos) em uma lista de SensorSample sincronizadas.
    samples = [
        SensorSample.from_component_readings(acc, gyro, mag, baro)
        for acc, gyro, mag, baro in zip(
            acc_readings, gyro_readings, mag_readings, baro_readings
        )
    ]

    # 3. Inspeciona a primeira e a última amostra.
    first, last = samples[0], samples[-1]
    print("Primeira amostra:")
    print(f"  t={first.timestamp:.3f}s | "
          f"a=({first.ax:.3f}, {first.ay:.3f}, {first.az:.3f}) m/s² | "
          f"g=({first.gx:.4f}, {first.gy:.4f}, {first.gz:.4f}) rad/s | "
          f"m=({first.mx:.2f}, {first.my:.2f}, {first.mz:.2f}) µT | "
          f"P={first.pressure:.2f} hPa")

    print("Última amostra:")
    print(f"  t={last.timestamp:.3f}s | "
          f"a=({last.ax:.3f}, {last.ay:.3f}, {last.az:.3f}) m/s² | "
          f"g=({last.gx:.4f}, {last.gy:.4f}, {last.gz:.4f}) rad/s | "
          f"m=({last.mx:.2f}, {last.my:.2f}, {last.mz:.2f}) µT | "
          f"P={last.pressure:.2f} hPa")

    print(f"\nTotal de SensorSample sincronizadas: {len(samples)}")


if __name__ == "__main__":
    main()
