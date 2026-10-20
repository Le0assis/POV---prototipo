
from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from typing import List


def _clean_category_code(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("category_code vazio.")
    return cleaned


class CheckpointSchema(BaseModel):
    name: str
    category_code: str | None = None

    @field_validator("category_code")
    @classmethod
    def category_code_or_null(cls, value: str | None) -> str | None:
        return _clean_category_code(value)


class CheckpointCategorySchema(BaseModel):
    """PATCH de categoria. ``slug`` no corpo é recusado: o slug não se edita."""

    model_config = ConfigDict(extra="forbid")
    category_code: str | None

    @model_validator(mode="before")
    @classmethod
    def slug_is_immutable(cls, value):
        if isinstance(value, dict) and "slug" in value:
            raise ValueError("O slug não pode ser alterado.")
        return value

    @field_validator("category_code")
    @classmethod
    def category_code_or_null(cls, value: str | None) -> str | None:
        return _clean_category_code(value)

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


# SCHEMAS PARA ROTAS SALVAS
class RouteCreateSchema(BaseModel):
    start_node: str
    end_node: str
    name: str = None

class RouteResponseSchema(BaseModel):
    id: int
    name: str
    start_node: str
    end_node: str
    total_distance_m: float
    total_steps_estimated: int
    segments: list
    path_sequence: list
    created_at: str


class CheckpointPositionSchema(BaseModel):
    pos_x_px: float
    pos_y_px: float


class MapConfigSchema(BaseModel):
    plan_image: str | None = None
    px_per_m: float
    rotation_rad: float = 0.0

    @field_validator("px_per_m")
    @classmethod
    def px_per_m_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("px_per_m deve ser maior que zero.")
        return value

