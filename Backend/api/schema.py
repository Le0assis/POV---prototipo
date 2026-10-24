
import math

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import List

# Tamanhos das colunas. Acima disso o MySQL recusa ou corta, e a API virava 500.
NAME_MAX = 100
CATEGORY_CODE_MAX = 32
PLAN_IMAGE_MAX = 512
# 100 Hz por 10 minutos. Sem teto, o POST parseava o corpo antes da senha.
MAX_RAW_SAMPLES = 60_000


def _finite(value: float, message: str) -> float:
    if not math.isfinite(value):
        raise ValueError(message)
    return value


def _clean_category_code(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("category_code vazio.")
    return cleaned


class CheckpointSchema(BaseModel):
    name: str = Field(max_length=NAME_MAX)
    category_code: str | None = Field(default=None, max_length=CATEGORY_CODE_MAX)

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
    source: str = Field(max_length=NAME_MAX)
    target: str = Field(max_length=NAME_MAX)
    distance_m: float
    heading_rad: float

    @field_validator("distance_m")
    @classmethod
    def distance_positive(cls, value: float) -> float:
        _finite(value, "A distância deve ser um número finito.")
        if value <= 0:
            raise ValueError("A distância deve ser maior que zero.")
        return value

    @field_validator("heading_rad")
    @classmethod
    def heading_finite(cls, value: float) -> float:
        return _finite(value, "O heading deve ser um número finito.")

class StepSensorSchema(BaseModel):
    step_length_m: float
    yaw_rad: float

    @field_validator("step_length_m")
    @classmethod
    def step_positive(cls, value: float) -> float:
        _finite(value, "O passo deve ser um número finito.")
        if value <= 0:
            raise ValueError("O passo deve ser maior que zero.")
        return value

    @field_validator("yaw_rad")
    @classmethod
    def yaw_finite(cls, value: float) -> float:
        return _finite(value, "O yaw deve ser um número finito.")

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
    source: str = Field(max_length=NAME_MAX)
    target: str = Field(max_length=NAME_MAX)
    samples: List[RawSampleSchema] = Field(max_length=MAX_RAW_SAMPLES)


# SCHEMAS PARA ROTAS SALVAS
class RouteCreateSchema(BaseModel):
    start_node: str = Field(max_length=NAME_MAX)
    end_node: str = Field(max_length=NAME_MAX)
    name: str | None = Field(default=None, max_length=NAME_MAX)

    @field_validator("name")
    @classmethod
    def blank_name_means_automatic(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

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

    @field_validator("pos_x_px", "pos_y_px")
    @classmethod
    def position_finite(cls, value: float) -> float:
        return _finite(value, "A posição deve ser um número finito.")


class MapConfigSchema(BaseModel):
    plan_image: str | None = Field(default=None, max_length=PLAN_IMAGE_MAX)
    px_per_m: float
    rotation_rad: float = 0.0

    @field_validator("px_per_m")
    @classmethod
    def px_per_m_positive(cls, value: float) -> float:
        _finite(value, "px_per_m deve ser um número finito.")
        if value <= 0:
            raise ValueError("px_per_m deve ser maior que zero.")
        return value

    @field_validator("rotation_rad")
    @classmethod
    def rotation_finite(cls, value: float) -> float:
        return _finite(value, "rotation_rad deve ser um número finito.")

