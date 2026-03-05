# ☀️ Solar Plant Simulator

Simulador fotovoltaico realista para el proyecto **Solar Monitoring**.  
Genera datos sintéticos compatibles con tu esquema de base de datos y `stream_publisher.py`.

---

## Estructura

```
solar_simulator/
├── simulator_core.py   # Motor de física + fallas (Python)
├── run_simulator.py    # CLI orquestador multi-planta
├── simulator_ui.html   # Dashboard visual interactivo (abrir en browser)
└── output/
    ├── solar_stream.csv         # CSV generado
    └── simulator_state.json     # Checkpoint de estado
```

---

## Uso rápido

### 1. Dashboard Visual (sin dependencias)
Abrir `simulator_ui.html` en cualquier navegador. No requiere Python.

### 2. Generar CSV (batch)
```bash
pip install numpy pandas requests

# 1 día de datos (96 pasos × 4 plantas)
python run_simulator.py --batch 96 --plants 4

# 1 semana, alto nivel de fallas
python run_simulator.py --batch 672 --plants 4 --fault-level 4

# Enviar directamente a tu API
python run_simulator.py --batch 96 --api http://localhost:8000
```

### 3. Modo tiempo real (simula cada 15min en 2 segundos)
```bash
python run_simulator.py --plants 4 --delay 2.0
```

### 4. Combinar con stream_publisher.py existente
```bash
# 1. Generar CSV con el simulador
python run_simulator.py --batch 288 --output ./data_g

# 2. Publicar con tu publisher existente
python stream_publisher.py  # Lee data_g/solar_stream.csv
```

---

## Física implementada

### Modelo de irradiancia
- **Posición solar real**: algoritmo de Spencer (elevación + azimut por latitud/longitud/día del año)
- **Cielo claro**: modelo Ineichen simplificado con masa de aire
- **Superficie inclinada**: proyección POA (Perez simplificado)
- **Nubes**: proceso Ornstein-Uhlenbeck para variaciones realistas

### Temperatura
- **Ambiente**: ciclo diurno + estacional por latitud
- **Módulo**: modelo NOCT con corrección de viento

### Potencia
- **DC**: función de irradiancia (no lineal a baja luz), temperatura (−0.4%/°C), suciedad
- **AC**: curva de eficiencia de inversor (varía con carga, máx ~97%)

---

## Tipos de Falla

| Tipo | Descripción | Efecto físico |
|------|-------------|---------------|
| `inverter_derate` | Inversor limitando potencia | P_AC reducida proporcionalmente |
| `sensor_flatline` | Sensor congelado | Lecturas AC/DC constantes |
| `string_fault` | Cortocircuito en string | Pérdida 5–35% de P_DC/AC |
| `grid_disconnect` | Desconexión de red | P_AC = 0 (total) o 30% (parcial) |
| `mppt_failure` | Seguidor fuera del punto óptimo | Pérdida 10–40% de eficiencia |
| `partial_shading` | Sombra en paneles | Hot-spot effect (pérdida > fracción sombrada) |
| `panel_soiling` | Suciedad acumulada | Pérdida gradual hasta 25% |
| `pid_effect` | Degradación por tensión | Pérdida crónica acumulativa |

### Fenómenos graduales
- **Suciedad**: se acumula durante horas solares, polvo saháreo (+5% instantáneo), lluvia limpia
- **Degradación PID**: 0.0015%/paso, crónico, máx 15%

---

## Schema compatible con tu DB

Los campos generados coinciden exactamente con `solar_readings`:

```
ts, plant_id, irradiance_wm2, temp_ambient_c, temp_module_c,
power_ac_kw, power_dc_kw, energy_daily_kwh, energy_total_kwh,
label_is_fault, fault_type, fault_severity
```

---

## Variables de entorno

```bash
export SOLAR_API_URL=http://localhost:8000
export SOLAR_INGEST_ENDPOINT=/ingest_batch
export SOLAR_BATCH_SIZE=250
```

---

## Opciones CLI

```
--plants N       Número de plantas (1-8, default: 4)
--batch N        Pasos batch; omitir para modo real-time
--api URL        URL base de la API para publicar
--endpoint PATH  Endpoint de ingestión (default: /ingest_batch)
--delay S        Segundos entre pasos en real-time (default: 2.0)
--fault-level N  Nivel de fallas 1-5 (default: 2)
--start-ts TS    Timestamp inicio ISO (continúa desde checkpoint si omite)
--output DIR     Directorio de salida (default: ./output)
--no-soiling     Deshabilitar acumulación de suciedad
--quiet          Sin output verboso
```
