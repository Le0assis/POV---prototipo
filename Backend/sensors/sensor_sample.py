
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .accelerometer import AccelerometerReading
    from .gyroscope import GyroscopeReading
    from .magnetometer import MagnetometerReading
    from .barometer import BarometerReading


@dataclass(frozen=True, slots=True)
class SensorSample:
    """Amostra sincronizada dos sensores inerciais e ambiental do smartphone.

    Attributes:
        timestamp: instante da leitura, em segundos.
        ax, ay, az: aceleração linear (m/s²).
        gx, gy, gz: velocidade angular (rad/s).
        mx, my, mz: campo magnético (µT).
        pressure: pressão atmosférica (hPa).
    """

    timestamp: float
    ax: float
    ay: float
    az: float
    gx: float
    gy: float
    gz: float
    mx: float
    my: float
    mz: float
    pressure: float

    def __post_init__(self) -> None:
        """Valida a consistência física mínima da amostra.

        Regra de negócio: pressão atmosférica não pode ser zero ou
        negativa. Isso faz a amostra "falhar cedo" (fail fast) caso um
        dataset venha corrompido, em vez de deixar um valor absurdo se
        propagar silenciosamente até o cálculo de altitude (Etapa 10).
        """
        if self.pressure <= 0:
            raise ValueError(
                f"Pressão inválida: {self.pressure} hPa. "
                "A pressão atmosférica deve ser estritamente positiva."
            )

    @classmethod
    def from_component_readings(
        cls,
        acc: "AccelerometerReading",
        gyro: "GyroscopeReading",
        mag: "MagnetometerReading",
        baro: "BarometerReading",
        timestamp_tolerance: float = 0.05,
    ) -> "SensorSample":
        """Combina quatro leituras independentes em uma SensorSample.

        Cada sensor (acelerômetro, giroscópio, magnetômetro, barômetro) é
        lido de forma independente (ver accelerometer.py, gyroscope.py,
        magnetometer.py, barometer.py). Este método assume o papel de
        SINCRONIZAR essas quatro leituras em uma única amostra coerente.

        Simplificação assumida na Etapa 1: assume-se que as quatro leituras
        já chegam aproximadamente alinhadas no tempo (ex.: extraídas de um
        único CSV com timestamp comum, ou de fontes com taxa de amostragem
        semelhante). Uma sincronização mais robusta — com interpolação para
        lidar com sensores de frequências distintas (ex.: barômetro
        tipicamente amostra a ~1-10 Hz, muito mais devagar que o
        acelerômetro a ~50-100 Hz) — é responsabilidade da camada de
        integração final (main.py / pdr/pdr.py), não deste módulo.

        Args:
            acc: leitura do acelerômetro.
            gyro: leitura do giroscópio.
            mag: leitura do magnetômetro.
            baro: leitura do barômetro.
            timestamp_tolerance: diferença máxima aceitável, em segundos,
                entre os timestamps das quatro leituras.

        Raises:
            ValueError: se os timestamps divergirem além da tolerância.
        """
        timestamps = (acc.timestamp, gyro.timestamp, mag.timestamp, baro.timestamp)
        if max(timestamps) - min(timestamps) > timestamp_tolerance:
            raise ValueError(
                "Leituras fora de sincronia: diferença de timestamp "
                f"{max(timestamps) - min(timestamps):.4f}s excede a "
                f"tolerância de {timestamp_tolerance}s. "
                f"Timestamps recebidos: {timestamps}"
            )

        return cls(
            timestamp=acc.timestamp,
            ax=acc.ax, ay=acc.ay, az=acc.az,
            gx=gyro.gx, gy=gyro.gy, gz=gyro.gz,
            mx=mag.mx, my=mag.my, mz=mag.mz,
            pressure=baro.pressure,
        )
