from pydantic import BaseModel, Field, field_validator
from typing import List, Optional

class ReadingIn(BaseModel):
    ts: str
    plant_id: int = 1
    inverter_id: str

    expected_power_ac_kw: float | None = None

    irradiance_wm2: float
    temp_ambient_c: float
    temp_module_c: float
    power_ac_kw: float
    power_dc_kw: float

    energy_daily_kwh: float = 0.0
    energy_total_kwh: float = 0.0

    label_is_fault: int = 0
    fault_type: Optional[str] = ""
    fault_severity: Optional[int] = 0

    @field_validator("fault_type", mode="before")
    @classmethod
    def coerce_fault_type(cls, v):
        if v is None or (isinstance(v, float) and v != v):  # NaN check
            return ""
        return str(v)

    @field_validator("fault_severity", mode="before")
    @classmethod
    def coerce_fault_severity(cls, v):
        if v is None or (isinstance(v, float) and v != v):
            return 0
        return int(v)


class BatchIn(BaseModel):
    readings: List[ReadingIn] = Field(..., min_length=1, max_length=5000)