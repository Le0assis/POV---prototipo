"""Classe que declara se a caminhada relizada e um movimento humano ou nao"""

# pdr/processor.py
import numpy as np
from fastapi import HTTPException, status
from scipy.interpolate import interp1d
import csv
import io

from filters.butterworth import ButterworthLowPassFilter
from .steps import PeakStepDetector
from filters.madgwick import MadgwickAttitudeEstimator


def generate_sensors_csv(samples: list) -> str:
    """Converte a lista de dicionários/amostras em uma string CSV."""
    output = io.StringIO()
    if not samples:
        return ""
    
    # Extrai as chaves do primeiro elemento para o cabeçalho
    fieldnames = samples[0].keys() if isinstance(samples[0], dict) else ['timestamp', 'mag_y', 'accel_x', 'mag_x', 'mag_z', 'accel_y', 'gyro_y', 'accel_z', 'gyro_z', 'gyro_x']
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    
    writer.writeheader()
    for sample in samples:
        if isinstance(sample, dict):
            writer.writerow(sample)
        else:
            # Caso os objetos cheguem como modelo Pydantic
            writer.writerow(sample.dict())
            
    return output.getvalue()


def resample_sensor_data(samples, target_hz=30.0):
    """
    Interpola os dados dos sensores para garantir um intervalo de tempo 
    rigorosamente constante (dt = 1/30s), eliminando a oscilação do navegador.
    """
    if len(samples) < 15:
        return None, None, None, None, None, None, None

    t_orig = np.array([s.timestamp for s in samples], dtype=np.float64)
    duration = t_orig[-1] - t_orig[0]

    if duration <= 0:
        return None, None, None, None, None, None, None

    # Define a quantidade exata de pontos para manter 30 Hz fixos
    num_points = int(np.round(duration * target_hz))
    if num_points < 10:
        return None, None, None, None, None, None, None

    # Grade temporal perfeitamente uniforme
    t_uniform = np.linspace(t_orig[0], t_orig[-1], num_points)

    # Vetores originais
    ax = np.array([s.accel_x for s in samples])
    ay = np.array([s.accel_y for s in samples])
    az = np.array([s.accel_z for s in samples])
    gx = np.array([s.gyro_x for s in samples])
    gy = np.array([s.gyro_y for s in samples])
    gz = np.array([s.gyro_z for s in samples])

    # Interpolação linear para alinhar os eixos no tempo uniforme
    ax_u = interp1d(t_orig, ax, kind='linear', fill_value='extrapolate')(t_uniform)
    ay_u = interp1d(t_orig, ay, kind='linear', fill_value='extrapolate')(t_uniform)
    az_u = interp1d(t_orig, az, kind='linear', fill_value='extrapolate')(t_uniform)
    gx_u = interp1d(t_orig, gx, kind='linear', fill_value='extrapolate')(t_uniform)
    gy_u = interp1d(t_orig, gy, kind='linear', fill_value='extrapolate')(t_uniform)
    gz_u = interp1d(t_orig, gz, kind='linear', fill_value='extrapolate')(t_uniform)

    return t_uniform, ax_u, ay_u, az_u, gx_u, gy_u, gz_u

class RawEdgeProcessor:
    def __init__(self, db_manager, topo_map):
        self.db_manager = db_manager
        self.topo_map = topo_map

    def process_samples(self, source: str, target: str, samples: list):
        
        TARGET_HZ = 30.0
        
        if not samples or len(samples) < 20:
            raise HTTPException(status_code=400, detail="Amostras insuficientes (mínimo 20).")

        # GERAR CSV DOS DADOS BRUTOS
        csv_string = generate_sensors_csv(samples)
        
        # SALVAR LOG BRUTO NO BANCO
        self.db_manager.save_sensor_log(
            source=source, 
            target=target, 
            csv_data=csv_string
        )        

        # REAMOSTRAGEM DOS DADOS (Cria sinais perfeitamente alinhados no tempo)
        t_u, ax, ay, az, gx, gy, gz = resample_sensor_data(samples, target_hz=TARGET_HZ)

        if t_u is None:
            raise HTTPException(status_code=400, detail="Tempo de amostragem inválido.")

        estimator = MadgwickAttitudeEstimator(gain=0.033)
        dt = 1.0 / TARGET_HZ
        quaternions = []

        for i in range(len(t_u)):
            q = estimator.update(
                gx=gx[i], gy=gy[i], gz=gz[i],
                ax=ax[i], ay=ay[i], az=az[i],
                mx=0.0, my=0.0, mz=0.0,
                dt=dt
            )
            quaternions.append(q)
        
        vertical_acc = np.array([
            q.get_vertical_acceleration(ax[i], ay[i], az[i]) 
            for i, q in enumerate(quaternions)
        ])
        
        gyro_magnitude = np.sqrt(gx**2 + gy**2 + gz**2)
        max_gyro = np.max(gyro_magnitude)
        mean_gyro = np.mean(gyro_magnitude)

        # Só descarta a gravação inteira se ultrapassar 5.5 rad/s sustentados ou pico de 7.5 rad/s
        if max_gyro > 7.5 or mean_gyro > 4.0:
            return {
                "status": "warning",
                "valid": False,
                "source": source,
                "target": target,
                "message": f"Movimento descartado como chacoalhado (Giroscópio pico: {round(max_gyro, 1)} rad/s).",
                "steps_count": 0,
                "distance_m": 0.0,
                "mean_yaw_rad": 0.0
            }

        # FILTRAGEM ADAPTATIVA
 
        bw_filter = ButterworthLowPassFilter(cutoff_hz=2.2, sample_rate_hz=TARGET_HZ, order=2)
        filtered_magnitude = bw_filter.apply(vertical_acc, sample_rate_hz=TARGET_HZ)

        # DETECÇÃO DE PASSOS
        detector = PeakStepDetector(sample_rate_hz=TARGET_HZ, weinberg_k=0.45)
        
        step_events = detector.detect(
            timestamps=t_u,
            filtered_magnitude=filtered_magnitude,
            gyro_magnitude=gyro_magnitude,
            sample_rate_hz=TARGET_HZ
        )

        if not step_events:
            return {
                "status": "warning",
                "valid": False,
                "source": source,
                "target": target,
                "message": "Nenhum passo identificado.",
                "steps_count": 0,
                "distance_m": 0.0,
                "mean_yaw_rad": 0.0
            }

        # CÁLCULO DE DISTÂNCIA E ORIENTAÇÃO
        total_distance_m = sum(s.step_length_m for s in step_events)
        
        mean_yaw_rad = float(np.mean([q.yaw for q in quaternions]))

        # PERSISTÊNCIA NO BANCO E GRAFO
        self.db_manager.save_edge(source, target, total_distance_m, mean_yaw_rad)
        angle_deg = float(np.degrees(mean_yaw_rad))
        self.topo_map.connect_checkpoints(source, target, distance=total_distance_m, angle_deg=angle_deg)

        return {
            "status": "success",
            "valid": True,
            "source": source,
            "target": target,
            "message": f"Trecho validado com sucesso!",
            "steps_count": len(step_events),
            "distance_m": round(total_distance_m, 2),
            "mean_yaw_rad": round(mean_yaw_rad, 4)
        }