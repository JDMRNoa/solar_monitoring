# solar_simulator/simulator_core.py
"""
Motor de simulación fotovoltaica realista.
Genera datos con física real, clima variable, suciedad, degradación y fallas.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


# ─────────────────────────────────────────────
#  Tipos de Falla
# ─────────────────────────────────────────────

class FaultType(str, Enum):
    NONE             = ""
    INVERTER_DERATE  = "inverter_derate"      # Inversores limitando potencia
    SENSOR_FLATLINE  = "sensor_flatline"       # Sensor congelado
    PANEL_SOILING    = "panel_soiling"         # Suciedad acumulada en paneles
    STRING_FAULT     = "string_fault"          # Cortocircuito en string
    PID_EFFECT       = "pid_effect"            # Potential Induced Degradation
    GRID_DISCONNECT  = "grid_disconnect"       # Desconexión de red
    MPPT_FAILURE     = "mppt_failure"          # Fallo en seguidor de máxima potencia
    PARTIAL_SHADING  = "partial_shading"       # Sombra parcial (nube, árbol, edificio)


@dataclass
class FaultEvent:
    fault_type: FaultType
    severity: int          # 1-5
    duration_steps: int
    remaining: int
    params: Dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────
#  Configuración de Planta
# ─────────────────────────────────────────────

@dataclass
class PlantConfig:
    plant_id: int
    name: str
    latitude: float = 4.5709          # Default: Colombia
    longitude: float = -74.2973
    timezone_offset_h: float = -5.0   # UTC-5
    capacity_kw: float = 100.0         # Capacidad pico del inversor
    panel_count: int = 300
    panel_wp: float = 350.0            # Wp por panel
    inverter_count: int = 4
    tilt_deg: float = 15.0             # Inclinación paneles
    azimuth_deg: float = 180.0         # Sur=180

    # Estado inicial
    soiling_level: float = 0.0         # 0.0 (limpio) → 1.0 (muy sucio)
    degradation_pct: float = 0.0       # % degradación por PID/envejecimiento

    # Probabilidades de falla por paso (15min)
    fault_probs: Dict[str, float] = field(default_factory=lambda: {
        FaultType.INVERTER_DERATE: 0.0015,
        FaultType.SENSOR_FLATLINE: 0.0008,
        FaultType.PANEL_SOILING:   0.0000,  # Se acumula gradualment
        FaultType.STRING_FAULT:    0.0006,
        FaultType.PID_EFFECT:      0.0000,  # Gradual
        FaultType.GRID_DISCONNECT: 0.0004,
        FaultType.MPPT_FAILURE:    0.0010,
        FaultType.PARTIAL_SHADING: 0.0020,
    })


@dataclass
class WeatherState:
    """Estado climático actual en la simulación."""
    cloud_cover: float = 0.0       # 0=despejado, 1=nublado
    cloud_velocity: float = 0.0    # Velocidad de cambio de nubes
    rain_active: bool = False
    wind_speed_ms: float = 2.0
    humidity_pct: float = 60.0
    dust_event: bool = False


# ─────────────────────────────────────────────
#  Motor de Física Solar
# ─────────────────────────────────────────────

class SolarPhysicsEngine:
    """
    Calcula irradiancia, temperaturas y potencias usando modelos físicos reales.
    Modelo de cielo claro: Ineichen-Perez simplificado.
    Temperatura de módulo: NOCT model.
    Potencia: One-diode model simplificado con temperatura y suciedad.
    """

    STEFAN_BOLTZMANN = 5.67e-8
    NOCT = 45.0          # Normal Operating Cell Temperature
    T_REF = 25.0         # Temperatura referencia STC
    Pmax_COEFF = -0.004  # Coef temperatura potencia (%/°C)

    def __init__(self, cfg: PlantConfig):
        self.cfg = cfg
        self._peak_kw = (cfg.panel_count * cfg.panel_wp) / 1000.0

    def solar_position(self, dt: pd.Timestamp) -> Tuple[float, float]:
        """
        Calcula elevación y azimut solar (grados).
        Algoritmo de Spencer simplificado.
        """
        lat_rad = math.radians(self.cfg.latitude)
        lon = self.cfg.longitude
        tz_offset = self.cfg.timezone_offset_h

        # Día del año
        day_of_year = dt.timetuple().tm_yday
        B = 2 * math.pi * (day_of_year - 1) / 365

        # Ecuación del tiempo (minutos)
        EoT = 229.18 * (0.000075 + 0.001868 * math.cos(B) - 0.032077 * math.sin(B)
                        - 0.014615 * math.cos(2 * B) - 0.04089 * math.sin(2 * B))

        # Declinación solar
        decl = math.radians(23.45 * math.sin(math.radians(360 / 365 * (day_of_year - 81))))

        # Hora solar verdadera
        hour_decimal = dt.hour + dt.minute / 60.0
        solar_noon_offset = (lon - tz_offset * 15) / 15
        solar_time = hour_decimal + solar_noon_offset + EoT / 60
        hour_angle = math.radians(15 * (solar_time - 12))

        # Elevación solar
        sin_elev = (math.sin(lat_rad) * math.sin(decl) +
                    math.cos(lat_rad) * math.cos(decl) * math.cos(hour_angle))
        elevation = math.degrees(math.asin(max(-1.0, min(1.0, sin_elev))))

        # Azimut solar
        if elevation > 0.1:
            cos_az = ((math.sin(decl) - math.sin(lat_rad) * sin_elev) /
                      (math.cos(lat_rad) * math.cos(math.asin(sin_elev))))
            cos_az = max(-1.0, min(1.0, cos_az))
            azimuth = math.degrees(math.acos(cos_az))
            if hour_angle > 0:
                azimuth = 360 - azimuth
        else:
            azimuth = 180.0

        return max(0.0, elevation), azimuth

    def clear_sky_irradiance(self, elevation_deg: float) -> float:
        """
        Irradiancia en cielo claro (W/m²) en superficie horizontal.
        Modelo simplificado de Ineichen.
        """
        if elevation_deg <= 0.5:
            return 0.0

        elev_rad = math.radians(elevation_deg)
        # Air mass
        am = 1.0 / (math.sin(elev_rad) + 0.50572 * (elevation_deg + 6.07995) ** -1.6364)
        am = min(am, 40.0)

        # Irradiancia directa normal (simplificada)
        dni = 950 * math.exp(-0.09 * am)
        # Irradiancia difusa
        dhi = 120 * math.sin(elev_rad) ** 0.3

        # Horizontal total
        ghi = dni * math.sin(elev_rad) + dhi
        return max(0.0, ghi)

    def tilted_irradiance(self, ghi: float, elevation_deg: float, azimuth_sun: float) -> float:
        """
        Proyecta GHI a superficie inclinada (Perez simplificado).
        """
        if ghi <= 0:
            return 0.0

        tilt_rad = math.radians(self.cfg.tilt_deg)
        az_panel = math.radians(self.cfg.azimuth_deg)
        az_sun = math.radians(azimuth_sun)
        elev_rad = math.radians(max(0.1, elevation_deg))

        # Factor geométrico beam
        cos_inc = (math.cos(elev_rad) * math.sin(tilt_rad) * math.cos(az_sun - az_panel) +
                   math.sin(elev_rad) * math.cos(tilt_rad))

        # Beam en plano inclinado
        # Separamos DNI y DHI aproximados
        clearness = min(1.0, ghi / (1367 * math.sin(elev_rad) + 1e-6))
        if clearness > 0.6:
            dni = ghi * 0.85
            dhi = ghi - dni * math.sin(elev_rad)
        else:
            dni = ghi * 0.3
            dhi = ghi - dni * math.sin(elev_rad)

        beam_tilted = max(0.0, dni * cos_inc)
        diffuse_tilted = dhi * (1 + math.cos(tilt_rad)) / 2
        reflected = ghi * 0.2 * (1 - math.cos(tilt_rad)) / 2  # albedo=0.2

        poa = beam_tilted + diffuse_tilted + reflected
        return max(0.0, poa)

    def module_temperature(self, irr_poa: float, temp_ambient: float, wind_ms: float) -> float:
        """
        Temperatura de módulo: modelo NOCT con corrección de viento.
        T_cell = T_amb + irr * (NOCT - 20) / 800 * (1 - wind_factor)
        """
        if irr_poa <= 0:
            return temp_ambient
        wind_factor = max(0.1, min(0.5, wind_ms / 20.0))
        noct_factor = (self.NOCT - 20.0) / 800.0
        t_cell = temp_ambient + irr_poa * noct_factor * (1 - wind_factor * 0.3)
        return t_cell

    def dc_power(self, irr_poa: float, t_cell: float, soiling: float, degradation_pct: float) -> float:
        """
        Potencia DC: modelo de temperatura + suciedad + degradación.
        """
        if irr_poa < 5.0:
            return 0.0

        # Referencia STC: 1000 W/m², 25°C
        p_stc = self._peak_kw

        # Factor irradiancia (lineal para irr >= 200, sublineal abajo)
        if irr_poa >= 200:
            irr_factor = irr_poa / 1000.0
        else:
            irr_factor = (irr_poa / 1000.0) ** 1.1

        # Factor temperatura
        temp_factor = 1.0 + self.Pmax_COEFF * (t_cell - self.T_REF)
        temp_factor = max(0.5, temp_factor)

        # Factor suciedad (1=limpio, reduce hasta ~80% con suciedad máxima)
        soiling_factor = 1.0 - soiling * 0.25

        # Factor degradación
        degradation_factor = 1.0 - degradation_pct / 100.0

        p_dc = p_stc * irr_factor * temp_factor * soiling_factor * degradation_factor
        return max(0.0, p_dc)

    def ac_power(self, p_dc: float, inverter_efficiency: float = 0.97) -> float:
        """
        Potencia AC con curva de eficiencia de inversor.
        La eficiencia varía con carga (máxima ~80-90% de capacidad nominal).
        """
        if p_dc <= 0:
            return 0.0

        capacity = self.cfg.capacity_kw
        load_ratio = p_dc / max(capacity, 1.0)

        # Curva eficiencia inversor: baja a baja carga, óptima al 80%
        if load_ratio < 0.05:
            eff = 0.70
        elif load_ratio < 0.20:
            eff = 0.92 + (load_ratio - 0.05) * 0.4
        elif load_ratio < 0.80:
            eff = inverter_efficiency
        else:
            # Saturación/derate a alta carga
            eff = inverter_efficiency - (load_ratio - 0.80) * 0.05

        eff = max(0.70, min(0.99, eff))
        p_ac = min(p_dc * eff, capacity)  # Limitado por capacidad inversor
        return max(0.0, p_ac)


# ─────────────────────────────────────────────
#  Gestor de Clima
# ─────────────────────────────────────────────

class WeatherSimulator:
    """
    Simula clima variable: nubes, lluvia, polvo, temperatura ambiente.
    Usa procesos Ornstein-Uhlenbeck para variaciones realistas.
    """

    def __init__(self, seed: Optional[int] = None):
        self.rng = np.random.default_rng(seed)
        self.state = WeatherState()
        self._cloud_momentum = 0.0
        self._step = 0
        self._season_phase = 0.0

    def step(self, dt: pd.Timestamp) -> WeatherState:
        """Avanza el clima un paso de 15 minutos."""
        self._step += 1
        self._season_phase = 2 * math.pi * dt.timetuple().tm_yday / 365

        # Proceso O-U para nubes
        theta = 0.08   # Mean reversion
        mu = 0.25      # Cloud cover promedio
        sigma = 0.12

        dW = self.rng.normal(0, 1)
        self._cloud_momentum += theta * (mu - self.state.cloud_cover) + sigma * dW * 0.25
        new_cloud = self.state.cloud_cover + self._cloud_momentum * 0.15
        new_cloud = float(np.clip(new_cloud, 0.0, 1.0))

        # Probabilidad de lluvia aumenta con nubes altas
        rain_prob = max(0, new_cloud - 0.6) * 0.1
        rain_active = bool(self.rng.random() < rain_prob) or (self.state.rain_active and self.rng.random() < 0.7)

        # Lluvia limpia un poco los paneles
        rain_cleaning = 0.15 if rain_active else 0.0

        # Viento (O-U también)
        wind = max(0.2, self.state.wind_speed_ms + self.rng.normal(0, 0.5))
        wind = float(np.clip(wind, 0.2, 15.0))

        # Evento de polvo (Saharan dust, etc.)
        dust_event = bool(self.rng.random() < 0.001 and not rain_active)

        # Humedad
        base_humidity = 60 + 20 * math.sin(self._season_phase)
        humidity = float(np.clip(base_humidity + self.rng.normal(0, 5), 20, 98))

        self.state = WeatherState(
            cloud_cover=new_cloud,
            cloud_velocity=self._cloud_momentum,
            rain_active=rain_active,
            wind_speed_ms=wind,
            humidity_pct=humidity,
            dust_event=dust_event,
        )
        return self.state, rain_cleaning

    def ambient_temperature(self, dt: pd.Timestamp, base_temp: float = 25.0) -> float:
        """
        Temperatura ambiente con ciclo diurno y estacional.
        """
        hour = dt.hour + dt.minute / 60.0
        day_of_year = dt.timetuple().tm_yday

        # Variación estacional (±5°C)
        seasonal = 5 * math.sin(2 * math.pi * (day_of_year - 80) / 365)

        # Ciclo diurno (mínimo 5am, máximo 3pm)
        diurnal = 8 * math.sin(math.pi * (hour - 5) / 12) if 5 <= hour <= 21 else -4

        noise = float(self.rng.normal(0, 0.8))
        return base_temp + seasonal + diurnal + noise


# ─────────────────────────────────────────────
#  Gestor de Fallas
# ─────────────────────────────────────────────

class FaultManager:
    """
    Maneja la inyección, progresión y resolución de fallas.
    Cada tipo de falla tiene comportamiento físico realista.
    """

    FAULT_DURATIONS = {
        FaultType.INVERTER_DERATE:  (16, 96),    # 4h - 24h
        FaultType.SENSOR_FLATLINE:  (4, 20),     # 1h - 5h
        FaultType.PANEL_SOILING:    (192, 672),  # 2 días - 1 semana (gradual)
        FaultType.STRING_FAULT:     (8, 48),     # 2h - 12h
        FaultType.PID_EFFECT:       (288, 1440), # 3 días - 15 días (crónico)
        FaultType.GRID_DISCONNECT:  (1, 8),      # 15min - 2h
        FaultType.MPPT_FAILURE:     (8, 40),     # 2h - 10h
        FaultType.PARTIAL_SHADING:  (2, 12),     # 30min - 3h
    }

    def __init__(self, cfg: PlantConfig, seed: Optional[int] = None):
        self.cfg = cfg
        self.rng = np.random.default_rng(seed)
        self.active_faults: List[FaultEvent] = []
        self._soiling_level = cfg.soiling_level
        self._degradation_pct = cfg.degradation_pct

    @property
    def soiling_level(self) -> float:
        return self._soiling_level

    @property
    def degradation_pct(self) -> float:
        return self._degradation_pct

    def step(self, dt: pd.Timestamp, weather: WeatherState, rain_cleaning: float) -> List[FaultEvent]:
        """
        Actualiza fallas activas y genera nuevas si aplica.
        """
        # Actualizar suciedad gradual
        hour = dt.hour
        if 9 <= hour <= 17 and not weather.rain_active:
            # Acumula suciedad durante horas solares
            dust_rate = 0.0001
            if weather.dust_event:
                dust_rate = 0.005
            self._soiling_level = min(1.0, self._soiling_level + dust_rate)

        # Lluvia limpia paneles
        if weather.rain_active:
            self._soiling_level = max(0.0, self._soiling_level - rain_cleaning * 0.1)

        # PID: degradación acumulativa muy lenta
        self._degradation_pct = min(15.0, self._degradation_pct + 0.000015)

        # Decrementar duración de fallas activas
        expired = []
        for fault in self.active_faults:
            fault.remaining -= 1
            if fault.remaining <= 0:
                expired.append(fault)
        for f in expired:
            self.active_faults.remove(f)

        # Intentar generar nuevas fallas (solo una por paso para no saturar)
        active_types = {f.fault_type for f in self.active_faults}

        for fault_type, prob in self.cfg.fault_probs.items():
            if fault_type in active_types:
                continue
            if fault_type in (FaultType.PANEL_SOILING, FaultType.PID_EFFECT):
                continue  # Estos son graduales, no por evento

            # Ajustar probabilidad por condiciones
            adjusted_prob = prob
            if fault_type == FaultType.PARTIAL_SHADING:
                adjusted_prob = prob * (1 + weather.cloud_cover * 3)
            elif fault_type == FaultType.INVERTER_DERATE and 10 <= hour <= 14:
                adjusted_prob = prob * 2  # Más probable con alta carga

            if self.rng.random() < adjusted_prob:
                self._create_fault(fault_type)

        return list(self.active_faults)

    def _create_fault(self, fault_type: FaultType):
        duration_range = self.FAULT_DURATIONS[fault_type]
        duration = int(self.rng.integers(duration_range[0], duration_range[1]))
        severity = int(self.rng.integers(1, 6))

        params = {}
        if fault_type == FaultType.INVERTER_DERATE:
            params["derate_factor"] = float(self.rng.uniform(0.3, 0.75))
            params["affected_inverters"] = int(self.rng.integers(1, self.cfg.inverter_count + 1))

        elif fault_type == FaultType.STRING_FAULT:
            total_strings = self.cfg.panel_count // 20  # ~20 paneles por string
            params["affected_strings"] = int(self.rng.integers(1, max(2, total_strings // 3)))
            params["power_loss_pct"] = float(self.rng.uniform(0.05, 0.35))

        elif fault_type == FaultType.SENSOR_FLATLINE:
            params["freeze_value"] = None  # Se congela al primer paso

        elif fault_type == FaultType.MPPT_FAILURE:
            params["efficiency_loss"] = float(self.rng.uniform(0.10, 0.40))

        elif fault_type == FaultType.PARTIAL_SHADING:
            params["shade_fraction"] = float(self.rng.uniform(0.10, 0.60))
            params["shade_type"] = self.rng.choice(["cloud", "tree", "building", "bird"])

        elif fault_type == FaultType.GRID_DISCONNECT:
            params["complete_disconnect"] = bool(self.rng.random() < 0.4)

        fault = FaultEvent(
            fault_type=fault_type,
            severity=severity,
            duration_steps=duration,
            remaining=duration,
            params=params,
        )
        self.active_faults.append(fault)

    def apply_faults(
        self,
        p_dc: float,
        p_ac: float,
        irr: float,
        t_module: float,
    ) -> Tuple[float, float, str, int, Dict]:
        """
        Aplica efectos de fallas activas sobre potencia DC/AC.
        Retorna (p_dc_mod, p_ac_mod, fault_type_str, severity, extra_info)
        """
        if not self.active_faults:
            return p_dc, p_ac, "", 0, {}

        # Aplicar en orden de severidad (mayor primero)
        faults_sorted = sorted(self.active_faults, key=lambda f: f.severity, reverse=True)
        dominant = faults_sorted[0]

        extra = {"fault_desc": "", "affected_component": ""}

        if dominant.fault_type == FaultType.INVERTER_DERATE:
            factor = dominant.params.get("derate_factor", 0.6)
            inv_frac = dominant.params.get("affected_inverters", 1) / self.cfg.inverter_count
            p_ac = p_ac * (1 - inv_frac * (1 - factor))
            p_dc = p_dc  # DC no se ve afectado directamente
            extra["fault_desc"] = f"Inverter derate {factor:.0%}, {dominant.params['affected_inverters']}/{self.cfg.inverter_count} inversores"
            extra["affected_component"] = f"Inverter_{dominant.params['affected_inverters']}"

        elif dominant.fault_type == FaultType.SENSOR_FLATLINE:
            if dominant.params.get("freeze_value") is None:
                dominant.params["freeze_value_ac"] = p_ac
                dominant.params["freeze_value_dc"] = p_dc
            p_ac = dominant.params["freeze_value_ac"]
            p_dc = dominant.params["freeze_value_dc"]
            extra["fault_desc"] = "Sensor congelado, lecturas no varían"
            extra["affected_component"] = "Sensor_AC/DC"

        elif dominant.fault_type == FaultType.STRING_FAULT:
            loss = dominant.params.get("power_loss_pct", 0.15)
            p_dc = p_dc * (1 - loss)
            p_ac = p_ac * (1 - loss * 0.95)
            extra["fault_desc"] = f"Cortocircuito en {dominant.params['affected_strings']} string(s), pérdida {loss:.0%}"
            extra["affected_component"] = f"String_{dominant.params['affected_strings']}"

        elif dominant.fault_type == FaultType.PID_EFFECT:
            # PID: pérdida gradual que aumenta con el tiempo
            elapsed = dominant.duration_steps - dominant.remaining
            pid_loss = min(0.30, elapsed * 0.001)
            p_dc = p_dc * (1 - pid_loss)
            p_ac = p_ac * (1 - pid_loss)
            extra["fault_desc"] = f"PID effect, degradación acumulada {pid_loss:.1%}"
            extra["affected_component"] = "Panel_array"

        elif dominant.fault_type == FaultType.GRID_DISCONNECT:
            if dominant.params.get("complete_disconnect"):
                p_ac = 0.0
                extra["fault_desc"] = "Desconexión total de red"
            else:
                p_ac = p_ac * 0.3
                extra["fault_desc"] = "Desconexión parcial de red, reconectando"
            extra["affected_component"] = "Grid_connection"

        elif dominant.fault_type == FaultType.MPPT_FAILURE:
            loss = dominant.params.get("efficiency_loss", 0.20)
            p_dc = p_dc * (1 - loss)
            p_ac = p_ac * (1 - loss * 0.8)
            extra["fault_desc"] = f"MPPT operando fuera del punto óptimo, pérdida {loss:.0%}"
            extra["affected_component"] = "MPPT_controller"

        elif dominant.fault_type == FaultType.PARTIAL_SHADING:
            shade_frac = dominant.params.get("shade_fraction", 0.20)
            shade_type = dominant.params.get("shade_type", "cloud")
            # Shading es no lineal (hot-spot, bypass diodes)
            p_dc_loss = shade_frac * 1.3  # Pérdida mayor que fracción sombreada (hot-spot)
            p_dc = p_dc * max(0.1, 1 - p_dc_loss)
            p_ac = p_ac * max(0.1, 1 - shade_frac * 1.1)
            extra["fault_desc"] = f"Sombra parcial ({shade_type}), {shade_frac:.0%} área"
            extra["affected_component"] = f"Panel_shading_{shade_type}"

        # Añadir efecto de suciedad (siempre activo, ya incluido en dc_power pero aquí para registro)
        if self._soiling_level > 0.1:
            extra["soiling_level"] = self._soiling_level

        return max(0.0, p_dc), max(0.0, p_ac), dominant.fault_type.value, dominant.severity, extra


# ─────────────────────────────────────────────
#  Simulador de Planta
# ─────────────────────────────────────────────

class PlantSimulator:
    """
    Simulador completo de una planta fotovoltaica.
    Combina física, clima y fallas para generar lecturas realistas.
    """

    FREQ = pd.Timedelta(minutes=15)

    def __init__(self, cfg: PlantConfig, start_ts: pd.Timestamp, seed: Optional[int] = None):
        self.cfg = cfg
        self.physics = SolarPhysicsEngine(cfg)
        self.weather_sim = WeatherSimulator(seed=seed)
        self.fault_mgr = FaultManager(cfg, seed=(seed + 1) if seed else None)

        self.current_ts = start_ts
        self._energy_daily_kwh = 0.0
        self._energy_total_kwh = 0.0
        self._last_date = start_ts.date()
        self._step_count = 0

        # Historia corta para detectar flatlines reales
        self._power_history: List[float] = []

    def step(self) -> Dict[str, Any]:
        """Genera una lectura de 15 minutos."""
        dt = self.current_ts

        # 1. Clima
        weather, rain_cleaning = self.weather_sim.step(dt)
        t_ambient = self.weather_sim.ambient_temperature(dt, base_temp=27.0)

        # 2. Posición solar
        elevation, azimuth_sun = self.physics.solar_position(dt)

        # 3. Irradiancia
        ghi = self.physics.clear_sky_irradiance(elevation)
        cloud_factor = 1.0 - weather.cloud_cover * 0.85
        ghi_cloudy = ghi * cloud_factor + float(np.random.normal(0, 5))
        ghi_cloudy = max(0.0, ghi_cloudy)

        irr_poa = self.physics.tilted_irradiance(ghi_cloudy, elevation, azimuth_sun)

        # 4. Temperatura módulo
        t_module = self.physics.module_temperature(irr_poa, t_ambient, weather.wind_speed_ms)

        # 5. Potencias base (con suciedad y degradación)
        p_dc = self.physics.dc_power(
            irr_poa, t_module,
            self.fault_mgr.soiling_level,
            self.fault_mgr.degradation_pct
        )
        p_ac = self.physics.ac_power(p_dc)

        # Ruido realista pequeño
        noise_kw = float(np.random.normal(0, max(0.05, p_ac * 0.005)))
        p_ac = max(0.0, p_ac + noise_kw)
        p_dc = max(p_ac, p_dc + float(np.random.normal(0, max(0.03, p_dc * 0.003))))

        # 6. Gestionar y aplicar fallas
        active_faults = self.fault_mgr.step(dt, weather, rain_cleaning)
        p_dc_f, p_ac_f, fault_type_str, fault_severity, fault_extra = self.fault_mgr.apply_faults(
            p_dc, p_ac, irr_poa, t_module
        )

        label_is_fault = 1 if fault_type_str else 0

        # Soiling también es "fault" si nivel alto
        if self.fault_mgr.soiling_level > 0.15 and not fault_type_str:
            fault_type_str = FaultType.PANEL_SOILING.value
            fault_severity = int(min(5, self.fault_mgr.soiling_level * 10))
            label_is_fault = 1

        # 7. Energía acumulada
        dt_hours = 0.25  # 15 min
        inc_kwh = p_ac_f * dt_hours

        # Reset diario
        current_date = dt.date()
        if current_date != self._last_date:
            self._energy_daily_kwh = 0.0
            self._last_date = current_date

        self._energy_daily_kwh += inc_kwh
        self._energy_total_kwh += inc_kwh
        self._step_count += 1

        # Avanzar timestamp
        self.current_ts = dt + self.FREQ

        record = {
            "ts": dt.isoformat(),
            "plant_id": self.cfg.plant_id,
            "irradiance_wm2": round(irr_poa, 2),
            "temp_ambient_c": round(t_ambient, 2),
            "temp_module_c": round(t_module, 2),
            "power_ac_kw": round(p_ac_f, 4),
            "power_dc_kw": round(p_dc_f, 4),
            "energy_daily_kwh": round(self._energy_daily_kwh, 4),
            "energy_total_kwh": round(self._energy_total_kwh, 4),
            "label_is_fault": int(label_is_fault),
            "fault_type": fault_type_str,
            "fault_severity": int(fault_severity),
            # Metadata extra (no va a DB, útil para UI/debug)
            "_meta": {
                "elevation_deg": round(elevation, 2),
                "cloud_cover": round(weather.cloud_cover, 3),
                "wind_ms": round(weather.wind_speed_ms, 1),
                "soiling_level": round(self.fault_mgr.soiling_level, 4),
                "degradation_pct": round(self.fault_mgr.degradation_pct, 4),
                "rain_active": weather.rain_active,
                "active_fault_count": len(active_faults),
                "fault_extra": fault_extra,
            }
        }

        return record

    def run_steps(self, n: int) -> pd.DataFrame:
        records = [self.step() for _ in range(n)]
        df = pd.DataFrame(records)
        return df


# ─────────────────────────────────────────────
#  Multi-Plant Manager
# ─────────────────────────────────────────────

class MultiPlantSimulator:
    """
    Orquesta múltiples plantas con configuraciones independientes.
    """

    DEFAULT_PLANTS = [
        PlantConfig(plant_id=1, name="Planta Norte",  latitude=10.9, longitude=-74.8, capacity_kw=120.0, panel_count=350),
        PlantConfig(plant_id=2, name="Planta Sur",    latitude=4.71, longitude=-74.07, capacity_kw=85.0,  panel_count=250),
        PlantConfig(plant_id=3, name="Planta Este",   latitude=6.25, longitude=-75.56, capacity_kw=200.0, panel_count=580),
        PlantConfig(plant_id=4, name="Planta Oeste",  latitude=3.43, longitude=-76.52, capacity_kw=60.0,  panel_count=180),
    ]

    def __init__(self, plant_configs: Optional[List[PlantConfig]] = None, start_ts: Optional[pd.Timestamp] = None):
        configs = plant_configs or self.DEFAULT_PLANTS
        ts = start_ts or pd.Timestamp("2025-01-01 00:00:00")
        self.simulators = {
            cfg.plant_id: PlantSimulator(cfg, ts, seed=cfg.plant_id * 42)
            for cfg in configs
        }

    def step_all(self) -> List[Dict[str, Any]]:
        """Genera una lectura para todas las plantas."""
        return [sim.step() for sim in self.simulators.values()]

    def run_batch(self, n_steps: int) -> pd.DataFrame:
        """Genera n_steps para todas las plantas."""
        all_records = []
        for _ in range(n_steps):
            all_records.extend(self.step_all())
        df = pd.DataFrame(all_records)
        return df

    def get_plant_configs(self) -> List[PlantConfig]:
        return [sim.cfg for sim in self.simulators.values()]


if __name__ == "__main__":
    # Test básico
    ms = MultiPlantSimulator()
    df = ms.run_batch(96)  # 1 día de datos
    db_cols = ["ts", "plant_id", "irradiance_wm2", "temp_ambient_c", "temp_module_c",
               "power_ac_kw", "power_dc_kw", "energy_daily_kwh", "energy_total_kwh",
               "label_is_fault", "fault_type", "fault_severity"]
    print(df[db_cols].head(10).to_string())
    print(f"\nFallas: {df['label_is_fault'].sum()} / {len(df)}")
    print(f"Tipos: {df[df['label_is_fault']==1]['fault_type'].value_counts().to_dict()}")
