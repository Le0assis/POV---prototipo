
from pydantic import BaseModel
from typing import List

class CheckpointSchema(BaseModel):
    name: str

class EdgeSchema(BaseModel):
    source: str
    target: str
    distance_m: float
    heading_rad: float

class StepSensorSchema(BaseModel):
    step_length_m: float
    yaw_rad: float

# SCHEMAS PARA O ENVIOS DAS AMOSTRAS BRUTAS (GRAVAÇÃO DO CELULAR)
class RawSampleSchema(BaseModel):
    timestamp: float
    accel_x: float
    accel_y: float
    accel_z: float
    gyro_x: float
    gyro_y: float
    gyro_z: float
    mag_x: float = 0.0
    mag_y: float = 0.0
    mag_z: float = 0.0

    # Propriedades de compatibilidade com os seus adaptadores
    @property
    def gx(self) -> float: return self.gyro_x
    @property
    def gy(self) -> float: return self.gyro_y
    @property
    def gz(self) -> float: return self.gyro_z
    @property
    def ax(self) -> float: return self.accel_x
    @property
    def ay(self) -> float: return self.accel_y
    @property
    def az(self) -> float: return self.accel_z
    @property
    def mx(self) -> float: return self.mag_x
    @property
    def my(self) -> float: return self.mag_y
    @property
    def mz(self) -> float: return self.mag_z

class ProcessRawEdgeSchema(BaseModel):
    source: str
    target: str
    samples: List[RawSampleSchema]

