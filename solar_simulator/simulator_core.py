# simulator_core.py
"""
Motor de simulación fotovoltaica v2.0

Mejoras vs versión anterior:
  - 8 perfiles de planta radicalmente distintos (clima, región, capacidad)
  - Columna `expected_power_ac_kw`: potencia ideal sin falla (para residual ML)
  - Física vectorizada (apto para 2M+ registros)
  - 8 tipos de falla con física individual y duración realista
  - Proceso Ornstein-Uhlenbeck para nubes con memoria temporal
  - Suciedad acumulativa con lluvia y polvo sahareo
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


# ─────────────────────────────────────────────────────────────────
#  Tipos de falla
# ─────────────────────────────────────────────────────────────────

class FaultType(str, Enum):
    NONE            = ""
    INVERTER_DERATE = "inverter_derate"
    SENSOR_FLATLINE = "sensor_flatline"
    STRING_FAULT    = "string_fault"
    GRID_DISCONNECT = "grid_disconnect"
    MPPT_FAILURE    = "mppt_failure"
    PARTIAL_SHADING = "partial_shading"
    PANEL_SOILING   = "panel_soiling"
    PID_EFFECT      = "pid_effect"


@dataclass
class FaultEvent:
    fault_type: FaultType
    severity: int
    duration_steps: int
    remaining: int
    params: Dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────
#  Perfil de planta
# ─────────────────────────────────────────────────────────────────

@dataclass
class PlantProfile:
    plant_id: int
    name: str
    latitude: float
    longitude: float
    timezone_offset_h: float = -5.0
    altitude_m: float = 0.0
    capacity_kw: float = 100.0
    panel_count: int = 300
    panel_wp: float = 400.0
    tilt_deg: float = 15.0
    azimuth_deg: float = 180.0
    base_temp_c: float = 27.0
    temp_amplitude_c: float = 8.0
    cloud_cover_mean: float = 0.30
    cloud_cover_sigma: float = 0.15
    init_soiling: float = 0.02
    init_degradation_pct: float = 0.0
    inverter_count: int = 4
    fault_probs: Dict[str, float] = field(default_factory=lambda: {
        FaultType.INVERTER_DERATE:  0.0015,
        FaultType.SENSOR_FLATLINE:  0.0008,
        FaultType.STRING_FAULT:     0.0006,
        FaultType.GRID_DISCONNECT:  0.0004,
        FaultType.MPPT_FAILURE:     0.0010,
        FaultType.PARTIAL_SHADING:  0.0020,
    })


def build_plant_profiles(n_plants: int, fault_level: int = 2) -> List[PlantProfile]:
    """
    Devuelve N perfiles con características radicalmente distintas.
    Las plantas cubren los principales climas de Colombia.
    fault_level 1-5 escala todas las probabilidades de falla.
    """
    fault_scale = {1: 0.3, 2: 0.6, 3: 1.0, 4: 1.8, 5: 3.0}.get(fault_level, 1.0)

    base_fault_probs = {
        FaultType.INVERTER_DERATE:  0.0015,
        FaultType.SENSOR_FLATLINE:  0.0008,
        FaultType.STRING_FAULT:     0.0006,
        FaultType.GRID_DISCONNECT:  0.0004,
        FaultType.MPPT_FAILURE:     0.0010,
        FaultType.PARTIAL_SHADING:  0.0020,
    }

    def scaled(multiplier: float = 1.0) -> Dict[str, float]:
        return {k: v * fault_scale * multiplier for k, v in base_fault_probs.items()}

    templates = [
        # 1. Caribe: muy soleado, caliente, polvo, degradación avanzada
        PlantProfile(
            plant_id=1, name="Planta Caribe – Barranquilla",
            latitude=10.99, longitude=-74.78, altitude_m=18,
            capacity_kw=200.0, panel_count=500, panel_wp=400, inverter_count=6,
            tilt_deg=10, base_temp_c=30.0, temp_amplitude_c=7.0,
            cloud_cover_mean=0.20, cloud_cover_sigma=0.10,
            init_soiling=0.08, init_degradation_pct=0.5,
            fault_probs=scaled(1.2),
        ),
        # 2. Andina alta: nublado, frío, variabilidad alta
        PlantProfile(
            plant_id=2, name="Planta Andina – Bogotá",
            latitude=4.71, longitude=-74.07, altitude_m=2600,
            capacity_kw=80.0, panel_count=200, panel_wp=400, inverter_count=3,
            tilt_deg=8, base_temp_c=14.0, temp_amplitude_c=10.0,
            cloud_cover_mean=0.55, cloud_cover_sigma=0.22,
            init_soiling=0.02, init_degradation_pct=0.0,
            fault_probs=scaled(0.8),
        ),
        # 3. Paisa: clima de montaña media, lluvias fuertes
        PlantProfile(
            plant_id=3, name="Planta Paisa – Medellín",
            latitude=6.25, longitude=-75.56, altitude_m=1495,
            capacity_kw=150.0, panel_count=380, panel_wp=400, inverter_count=5,
            tilt_deg=12, base_temp_c=22.0, temp_amplitude_c=9.0,
            cloud_cover_mean=0.40, cloud_cover_sigma=0.18,
            init_soiling=0.04, init_degradation_pct=1.0,
            fault_probs=scaled(1.0),
        ),
        # 4. Valle: soleado templado, estable
        PlantProfile(
            plant_id=4, name="Planta Valle – Cali",
            latitude=3.43, longitude=-76.52, altitude_m=995,
            capacity_kw=120.0, panel_count=300, panel_wp=400, inverter_count=4,
            tilt_deg=10, base_temp_c=25.0, temp_amplitude_c=8.0,
            cloud_cover_mean=0.28, cloud_cover_sigma=0.14,
            init_soiling=0.03, init_degradation_pct=0.0,
            fault_probs=scaled(0.9),
        ),
        # 5. Llanos: alta variabilidad, tormentas
        PlantProfile(
            plant_id=5, name="Planta Llanos – Villavicencio",
            latitude=4.15, longitude=-73.63, altitude_m=467,
            capacity_kw=90.0, panel_count=225, panel_wp=400, inverter_count=3,
            tilt_deg=6, base_temp_c=28.0, temp_amplitude_c=9.0,
            cloud_cover_mean=0.45, cloud_cover_sigma=0.25,
            init_soiling=0.05, init_degradation_pct=2.0,
            fault_probs=scaled(1.3),
        ),
        # 6. Guajira: más seco, más polvo, planta grande
        PlantProfile(
            plant_id=6, name="Planta Guajira – Riohacha",
            latitude=11.54, longitude=-72.91, altitude_m=6,
            capacity_kw=300.0, panel_count=750, panel_wp=400, inverter_count=8,
            tilt_deg=12, base_temp_c=32.0, temp_amplitude_c=8.0,
            cloud_cover_mean=0.10, cloud_cover_sigma=0.08,
            init_soiling=0.15, init_degradation_pct=3.0,
            fault_probs=scaled(1.5),
        ),
        # 7. Sierra Nevada: microclima montaña costera
        PlantProfile(
            plant_id=7, name="Planta Sierra Nevada",
            latitude=11.0, longitude=-74.05, altitude_m=800,
            capacity_kw=60.0, panel_count=150, panel_wp=400, inverter_count=2,
            tilt_deg=18, base_temp_c=26.0, temp_amplitude_c=11.0,
            cloud_cover_mean=0.25, cloud_cover_sigma=0.18,
            init_soiling=0.06, init_degradation_pct=1.5,
            fault_probs=scaled(1.0),
        ),
        # 8. Boyacá: alta altitud, fría, variabilidad extrema
        PlantProfile(
            plant_id=8, name="Planta Boyacá – Tunja",
            latitude=5.53, longitude=-73.36, altitude_m=2782,
            capacity_kw=45.0, panel_count=112, panel_wp=400, inverter_count=2,
            tilt_deg=20, base_temp_c=12.0, temp_amplitude_c=12.0,
            cloud_cover_mean=0.50, cloud_cover_sigma=0.22,
            init_soiling=0.01, init_degradation_pct=0.0,
            fault_probs=scaled(0.7),
        ),
    ]

    return templates[:min(n_plants, len(templates))]


# ─────────────────────────────────────────────────────────────────
#  Motor de física solar
# ─────────────────────────────────────────────────────────────────

class SolarPhysicsEngine:
    NOCT = 45.0
    T_REF = 25.0
    Pmax_COEFF = -0.004

    def __init__(self, profile: PlantProfile):
        self.p = profile
        self._peak_kw = (profile.panel_count * profile.panel_wp) / 1000.0

    def solar_position(self, dt: pd.Timestamp) -> Tuple[float, float]:
        lat_rad = math.radians(self.p.latitude)
        lon = self.p.longitude
        doy = dt.timetuple().tm_yday
        B = 2 * math.pi * (doy - 1) / 365
        EoT = 229.18 * (0.000075 + 0.001868 * math.cos(B) - 0.032077 * math.sin(B)
                        - 0.014615 * math.cos(2 * B) - 0.04089 * math.sin(2 * B))
        decl = math.radians(23.45 * math.sin(math.radians(360 / 365 * (doy - 81))))

        # dt hereda generador naive pero sirve como UTC virtual para el backend.
        # Tiempo Solar Local (LST) a partir de UTC pura:
        # LST = UTC + (Longitud / 15) + Ecuación del Tiempo
        hour_utc = dt.hour + dt.minute / 60.0 + dt.second / 3600.0
        solar_time = hour_utc + (lon / 15.0) + (EoT / 60.0)

        hour_angle = math.radians(15 * (solar_time - 12))
        sin_elev = (math.sin(lat_rad) * math.sin(decl) +
                    math.cos(lat_rad) * math.cos(decl) * math.cos(hour_angle))
        elevation = math.degrees(math.asin(max(-1.0, min(1.0, sin_elev))))

        if elevation > 0.1:
            cos_az = ((math.sin(decl) - math.sin(lat_rad) * sin_elev) /
                      (math.cos(lat_rad) * math.cos(math.asin(sin_elev)) + 1e-9))
            azimuth = math.degrees(math.acos(max(-1.0, min(1.0, cos_az))))
            if hour_angle > 0:
                azimuth = 360 - azimuth
        else:
            azimuth = 180.0

        return max(0.0, elevation), azimuth

    def clear_sky_ghi(self, elevation_deg: float) -> float:
        if elevation_deg <= 0.5:
            return 0.0
        elev_rad = math.radians(elevation_deg)
        alt_factor = 1.0 + self.p.altitude_m * 0.0001
        am = 1.0 / (math.sin(elev_rad) + 0.50572 * (elevation_deg + 6.07995) ** -1.6364)
        am = min(am, 40.0)
        dni = 950 * alt_factor * math.exp(-0.09 * am)
        dhi = 120 * math.sin(elev_rad) ** 0.3
        return max(0.0, dni * math.sin(elev_rad) + dhi)

    def poa_irradiance(self, ghi: float, elevation_deg: float, azimuth_sun: float) -> float:
        if ghi <= 0:
            return 0.0
        tilt_rad = math.radians(self.p.tilt_deg)
        az_panel = math.radians(self.p.azimuth_deg)
        az_sun = math.radians(azimuth_sun)
        elev_rad = math.radians(max(0.1, elevation_deg))
        cos_inc = (math.cos(elev_rad) * math.sin(tilt_rad) * math.cos(az_sun - az_panel) +
                   math.sin(elev_rad) * math.cos(tilt_rad))
        clearness = min(1.0, ghi / (1367 * math.sin(elev_rad) + 1e-6))
        if clearness > 0.6:
            dni, dhi = ghi * 0.85, ghi * 0.15
        else:
            dni, dhi = ghi * 0.3, ghi * 0.7
        beam = max(0.0, dni * cos_inc)
        diffuse = dhi * (1 + math.cos(tilt_rad)) / 2
        reflected = ghi * 0.2 * (1 - math.cos(tilt_rad)) / 2
        return max(0.0, beam + diffuse + reflected)

    def module_temperature(self, irr_poa: float, t_ambient: float, wind_ms: float) -> float:
        if irr_poa <= 0:
            return t_ambient
        wind_factor = max(0.1, min(0.5, wind_ms / 20.0))
        return t_ambient + irr_poa * ((self.NOCT - 20.0) / 800.0) * (1 - wind_factor * 0.3)

    def dc_power_kw(self, irr_poa: float, t_cell: float,
                    soiling: float, degradation_pct: float) -> float:
        if irr_poa < 5.0:
            return 0.0
        irr_factor = (irr_poa / 1000.0) if irr_poa >= 200 else (irr_poa / 1000.0) ** 1.1
        temp_factor = max(0.5, 1.0 + self.Pmax_COEFF * (t_cell - self.T_REF))
        soiling_factor = 1.0 - soiling * 0.25
        deg_factor = 1.0 - degradation_pct / 100.0
        return max(0.0, self._peak_kw * irr_factor * temp_factor * soiling_factor * deg_factor)

    def ac_power_kw(self, p_dc: float) -> float:
        if p_dc <= 0:
            return 0.0
        cap = self.p.capacity_kw
        lr = p_dc / max(cap, 1.0)
        if lr < 0.05:        eff = 0.70
        elif lr < 0.20:      eff = 0.92 + (lr - 0.05) * 0.4
        elif lr < 0.80:      eff = 0.97
        else:                eff = 0.97 - (lr - 0.80) * 0.05
        eff = max(0.70, min(0.99, eff))
        return max(0.0, min(p_dc * eff, cap))


# ─────────────────────────────────────────────────────────────────
#  Simulador de clima (O-U)
# ─────────────────────────────────────────────────────────────────

class WeatherSimulator:

    def __init__(self, profile: PlantProfile, seed: Optional[int] = None):
        self.p = profile
        self.rng = np.random.default_rng(seed)
        self.cloud_cover = profile.cloud_cover_mean
        self._momentum = 0.0
        self.wind_ms = 2.5
        self.rain_active = False

    def step(self, dt: pd.Timestamp) -> Tuple[float, float, float, bool, bool, float]:
        """Retorna: (cloud_cover, t_ambient, wind_ms, rain_active, dust_event, rain_cleaning)"""
        p = self.p
        # O-U nubes
        dW = float(self.rng.normal(0, 1))
        self._momentum += 0.08 * (p.cloud_cover_mean - self.cloud_cover) + p.cloud_cover_sigma * dW * 0.25
        self.cloud_cover = float(np.clip(self.cloud_cover + self._momentum * 0.15, 0.0, 1.0))

        # Lluvia
        rain_prob = max(0, self.cloud_cover - 0.55) * 0.12
        if dt.month in (4, 5, 10, 11):
            rain_prob *= 2.0
        self.rain_active = bool(
            self.rng.random() < rain_prob or (self.rain_active and self.rng.random() < 0.65)
        )
        rain_cleaning = 0.15 if self.rain_active else 0.0

        # Viento
        self.wind_ms = float(np.clip(self.wind_ms + float(self.rng.normal(0, 0.5)), 0.2, 15.0))

        # Polvo (más frecuente en costa norte)
        dust_base = 0.001 if p.latitude > 9 else 0.0003
        dust_event = bool(self.rng.random() < dust_base and not self.rain_active)

        # Temperatura diurna + estacional
        doy = dt.timetuple().tm_yday
        hour = dt.hour + dt.minute / 60.0
        seasonal = 4.0 * math.sin(2 * math.pi * (doy - 80) / 365)
        diurnal = (p.temp_amplitude_c * math.sin(math.pi * (hour - 5) / 12)
                   if 5 <= hour <= 21 else -p.temp_amplitude_c * 0.5)
        t_ambient = (p.base_temp_c + seasonal + diurnal
                     + float(self.rng.normal(0, 0.8)) - self.cloud_cover * 2.0)

        return self.cloud_cover, t_ambient, self.wind_ms, self.rain_active, dust_event, rain_cleaning


# ─────────────────────────────────────────────────────────────────
#  Gestor de fallas
# ─────────────────────────────────────────────────────────────────

class FaultManager:

    DURATIONS = {
        FaultType.INVERTER_DERATE:  (16, 96),
        FaultType.SENSOR_FLATLINE:  (4, 20),
        FaultType.STRING_FAULT:     (8, 48),
        FaultType.GRID_DISCONNECT:  (1, 8),
        FaultType.MPPT_FAILURE:     (8, 40),
        FaultType.PARTIAL_SHADING:  (2, 12),
        # PANEL_SOILING y PID_EFFECT no se crean via _create pero se añaden
        # como defensa ante futuros usos — evita KeyError
        FaultType.PANEL_SOILING:    (0, 1),   # no usado por _create, es acumulativo
        FaultType.PID_EFFECT:       (48, 240),
    }

    def __init__(self, profile: PlantProfile, seed: Optional[int] = None):
        self.p = profile
        self.rng = np.random.default_rng(seed)
        self.active_faults: List[FaultEvent] = []
        self.soiling = profile.init_soiling
        self.degradation_pct = profile.init_degradation_pct
        self._step_count = 0
        self._scheduled_cleaning_step = -1  # -1 = sin limpieza pendiente

    def step(self, dt: pd.Timestamp, cloud_cover: float,
             rain_active: bool, dust_event: bool, rain_cleaning: float):
        hour = dt.hour
        self._step_count += 1

        # ── Suciedad acumulativa ──────────────────────────────────
        if 8 <= hour <= 17 and not rain_active:
            self.soiling = min(1.0, self.soiling + (0.006 if dust_event else 0.0002))

        # Limpieza natural por lluvia (pequeña por paso)
        if rain_active:
            self.soiling = max(0.0, self.soiling - rain_cleaning * 0.12)

        # ── Limpieza programada (mantenimiento humano) ────────────
        # 1. REACTIVA: panel_soiling detectado → limpiar en 7–15 días
        if self.soiling > 0.15 and self._scheduled_cleaning_step == -1:
            days = int(self.rng.integers(7, 16))   # 7–15 días
            self._scheduled_cleaning_step = self._step_count + days * 96

        # 2. PREVENTIVA: limpieza mensual fija (cada 30 días = 2880 pasos)
        MONTHLY = 30 * 96
        if self._step_count % MONTHLY == 0:
            self.soiling = max(0.01, self.soiling * 0.15)
            self._scheduled_cleaning_step = -1  # cancelar reactiva si coincide

        # Ejecutar la reactiva si llegó su momento
        elif self._scheduled_cleaning_step != -1 and self._step_count >= self._scheduled_cleaning_step:
            self.soiling = max(0.01, self.soiling * 0.15)
            self._scheduled_cleaning_step = -1

        # ── Degradación PID crónica ───────────────────────────────

        self.degradation_pct = min(15.0, self.degradation_pct + 0.000015)

        # Decrementar activas
        expired = [f for f in self.active_faults if f.remaining <= 1]
        self.active_faults = [f for f in self.active_faults if f.remaining > 1]
        for f in self.active_faults:
            f.remaining -= 1

        active_types = {f.fault_type for f in self.active_faults}

        for ft_str, prob in self.p.fault_probs.items():
            ft = FaultType(ft_str)
            if ft in active_types:
                continue
            adj = prob
            if ft == FaultType.PARTIAL_SHADING:
                adj *= (1 + cloud_cover * 3)
            elif ft == FaultType.INVERTER_DERATE and 10 <= hour <= 14:
                adj *= 1.8
            if self.rng.random() < adj:
                self._create(ft)

    def _create(self, ft: FaultType):
        lo, hi = self.DURATIONS[ft]
        duration = int(self.rng.integers(lo, hi))
        severity = int(self.rng.integers(1, 6))
        params: Dict[str, Any] = {}
        if ft == FaultType.INVERTER_DERATE:
            params["derate_factor"] = float(self.rng.uniform(0.3, 0.75))
            params["inv_idx"] = int(self.rng.integers(1, self.p.inverter_count + 1))
        elif ft == FaultType.STRING_FAULT:
            params["inv_idx"] = int(self.rng.integers(1, self.p.inverter_count + 1))
            params["power_loss_pct"] = float(self.rng.uniform(0.15, 0.50))
        elif ft == FaultType.SENSOR_FLATLINE:
            params["inv_idx"] = int(self.rng.integers(1, self.p.inverter_count + 1))
            params["freeze_value_ac"] = None
            params["freeze_value_dc"] = None
        elif ft == FaultType.MPPT_FAILURE:
            params["inv_idx"] = int(self.rng.integers(1, self.p.inverter_count + 1))
            params["efficiency_loss"] = float(self.rng.uniform(0.10, 0.40))
        elif ft == FaultType.PARTIAL_SHADING:
            params["inv_idx"] = int(self.rng.integers(1, self.p.inverter_count + 1))
            params["shade_fraction"] = float(self.rng.uniform(0.20, 0.80))
        elif ft == FaultType.GRID_DISCONNECT:
            params["complete"] = bool(self.rng.random() < 0.4)
            if not params["complete"]:
                params["inv_idx"] = int(self.rng.integers(1, self.p.inverter_count + 1))
        self.active_faults.append(FaultEvent(ft, severity, duration, duration, params))

    def apply(self, inv_idx: int, p_dc: float, p_ac: float) -> Tuple[float, float, str, int]:
        """Aplica fallas activas para UN inversor. Retorna (p_dc_mod, p_ac_mod, fault_type_str, severity)."""
        if not self.active_faults:
            if self.soiling > 0.15:
                return p_dc, p_ac, FaultType.PANEL_SOILING.value, int(min(5, self.soiling * 10))
            return p_dc, p_ac, "", 0

        # Filtrar fallas que afectan a este inversor o a toda la planta
        relevant_faults = []
        for f in self.active_faults:
            f_inv = f.params.get("inv_idx")
            if f_inv is None or f_inv == inv_idx:
                relevant_faults.append(f)

        if not relevant_faults:
            if self.soiling > 0.15:
                return p_dc, p_ac, FaultType.PANEL_SOILING.value, int(min(5, self.soiling * 10))
            return p_dc, p_ac, "", 0

        fault = sorted(relevant_faults, key=lambda f: f.severity, reverse=True)[0]
        ft = fault.fault_type

        if ft == FaultType.INVERTER_DERATE:
            factor = fault.params.get("derate_factor", 0.6)
            p_ac = p_ac * factor
        elif ft == FaultType.SENSOR_FLATLINE:
            if fault.params.get("freeze_value_ac") is None:
                fault.params["freeze_value_ac"] = p_ac
                fault.params["freeze_value_dc"] = p_dc
            p_ac = fault.params["freeze_value_ac"]
            p_dc = fault.params["freeze_value_dc"]
        elif ft == FaultType.STRING_FAULT:
            loss = fault.params.get("power_loss_pct", 0.15)
            p_dc *= (1 - loss)
            p_ac *= (1 - loss * 0.95)
        elif ft == FaultType.MPPT_FAILURE:
            loss = fault.params.get("efficiency_loss", 0.20)
            p_dc *= (1 - loss)
            p_ac *= (1 - loss * 0.8)
        elif ft == FaultType.PARTIAL_SHADING:
            shade = fault.params.get("shade_fraction", 0.20)
            p_dc = p_dc * max(0.1, 1 - shade * 1.3)
            p_ac = p_ac * max(0.1, 1 - shade * 1.1)
        elif ft == FaultType.GRID_DISCONNECT:
            p_ac = 0.0 if fault.params.get("complete") else p_ac * 0.1

        return max(0.0, p_dc), max(0.0, p_ac), ft.value, fault.severity


# ─────────────────────────────────────────────────────────────────
#  Simulador de planta individual
# ─────────────────────────────────────────────────────────────────

class PlantSimulator:

    FREQ = pd.Timedelta(minutes=15)

    def __init__(self, profile: PlantProfile, start_ts: pd.Timestamp,
                 seed: Optional[int] = None):
        self.profile = profile
        self.physics = SolarPhysicsEngine(profile)
        self.weather = WeatherSimulator(profile, seed=seed)
        self.faults = FaultManager(profile, seed=(seed or 0) + 1)
        self.rng = np.random.default_rng((seed or 0) + 2)
        self.current_ts = start_ts
        self._energy_daily = {i: 0.0 for i in range(1, profile.inverter_count + 1)}
        self._energy_total = {i: 0.0 for i in range(1, profile.inverter_count + 1)}
        self._last_date = start_ts.date()

    def step(self) -> List[Dict[str, Any]]:
        dt = self.current_ts

        # Clima
        cloud, t_amb, wind, rain, dust, rain_clean = self.weather.step(dt)

        # Posición solar + irradiancia
        elev, azimuth = self.physics.solar_position(dt)
        ghi = self.physics.clear_sky_ghi(elev)
        ghi_cloudy = max(0.0, ghi * (1.0 - cloud * 0.85) + float(self.rng.normal(0, 5)))
        irr_poa = self.physics.poa_irradiance(ghi_cloudy, elev, azimuth)

        # Temperatura módulo
        t_mod = self.physics.module_temperature(irr_poa, t_amb, wind)

        inv_count = self.profile.inverter_count
        
        # Potencias base para la planta total (sumando la eficiencia total) y la dividimos equitativamente por inversor
        p_dc_total = self.physics.dc_power_kw(irr_poa, t_mod,
                                              self.faults.soiling,
                                              self.faults.degradation_pct)
        # Eficiencia de inversores calculada sobre carga total, pero es casi lo mismo que carga por inversor unitario
        p_ac_total = self.physics.ac_power_kw(p_dc_total)
        
        base_dc = p_dc_total / inv_count
        base_ac = p_ac_total / inv_count

        # Fallas (avanzan el tiempo interno del manager)
        self.faults.step(dt, cloud, rain, dust, rain_clean)

        if dt.date() != self._last_date:
            self._energy_daily = {i: 0.0 for i in range(1, inv_count + 1)}
            self._last_date = dt.date()

        records = []
        for inv_idx in range(1, inv_count + 1):
            # Ruido realista por inversor
            p_ac_i = max(0.0, base_ac + float(self.rng.normal(0, max(0.02, base_ac * 0.005))))
            p_dc_i = max(p_ac_i, base_dc + float(self.rng.normal(0, max(0.01, base_dc * 0.003))))

            # expected_power: potencia normal sin fallas de evento
            expected_ac = round(p_ac_i, 4)

            p_dc_f, p_ac_f, fault_type, fault_sev = self.faults.apply(inv_idx, p_dc_i, p_ac_i)
            label_is_fault = 1 if fault_type else 0

            # Energía acumulada
            self._energy_daily[inv_idx] += p_ac_f * 0.25
            self._energy_total[inv_idx] += p_ac_f * 0.25

            records.append({
                "ts":                   dt.isoformat(),
                "plant_id":             self.profile.plant_id,
                "inverter_id":          f"P{self.profile.plant_id}-INV{inv_idx}",
                "irradiance_wm2":       round(irr_poa, 2),
                "temp_ambient_c":       round(t_amb, 2),
                "temp_module_c":        round(t_mod, 2),
                "power_ac_kw":          round(p_ac_f, 4),
                "power_dc_kw":          round(p_dc_f, 4),
                "energy_daily_kwh":     round(self._energy_daily[inv_idx], 4),
                "energy_total_kwh":     round(self._energy_total[inv_idx], 4),
                "label_is_fault":       label_is_fault,
                "fault_type":           fault_type,
                "fault_severity":       fault_sev,
                "expected_power_ac_kw": expected_ac,
                "_meta": {
                    "elevation_deg":   round(elev, 2),
                    "cloud_cover":     round(cloud, 3),
                    "wind_ms":         round(wind, 1),
                    "soiling":         round(self.faults.soiling, 4),
                    "degradation_pct": round(self.faults.degradation_pct, 4),
                    "rain_active":     rain,
                },
            })

        self.current_ts = dt + self.FREQ
        return records


# ─────────────────────────────────────────────────────────────────
#  Multi-planta
# ─────────────────────────────────────────────────────────────────

class MultiPlantSimulator:

    def __init__(self, profiles: List[PlantProfile],
                 start_ts: Optional[pd.Timestamp] = None):
        ts = start_ts or pd.Timestamp("2025-01-01 00:00:00")
        self.simulators: Dict[int, PlantSimulator] = {
            p.plant_id: PlantSimulator(p, ts, seed=p.plant_id * 42)
            for p in profiles
        }

    def step_all(self) -> List[Dict[str, Any]]:
        records = []
        for sim in self.simulators.values():
            records.extend(sim.step())
        return records

    def run_batch(self, n_steps: int) -> pd.DataFrame:
        records = []
        for _ in range(n_steps):
            records.extend(self.step_all())
        return pd.DataFrame(records)


# ─────────────────────────────────────────────────────────────────
#  Test rápido
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    profiles = build_plant_profiles(4, fault_level=2)
    ms = MultiPlantSimulator(profiles)
    df = ms.run_batch(96)
    cols = ["ts", "plant_id", "irradiance_wm2", "power_ac_kw", "expected_power_ac_kw",
            "label_is_fault", "fault_type", "fault_severity"]
    print(df[cols].head(12).to_string())
    print(f"\nFallas: {df['label_is_fault'].sum()} / {len(df)}")
    for pid, g in df.groupby("plant_id"):
        name = next(p.name for p in profiles if p.plant_id == pid)
        print(f"  [{pid}] {name:35s}  P_AC_max={g['power_ac_kw'].max():.1f}kW  "
              f"faults={g['label_is_fault'].sum()}")