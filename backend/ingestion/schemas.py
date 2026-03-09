from pydantic import BaseModel, Field
from typing import List

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
    fault_type: str = ""
    fault_severity: int = 0


class BatchIn(BaseModel):
    readings: List[ReadingIn] = Field(..., min_length=1, max_length=5000)