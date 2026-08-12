"""Classe que declara se a caminhada relizada e um movimento humano ou nao"""

# pdr/processor.py
import numpy as np
from fastapi import HTTPException, status
from filters.butterworth import ButterworthLowPassFilter
from .steps import PeakStepDetector
from filters.madgwick import MadgwickAttitudeEstimator

class RawEdgeProcessor:
    def __init__(self, db_manager, topo_map):
        self.db_manager = db_manager
        self.topo_map = topo_map

    def process_samples(self, source: str, target: str, samples: list):
        if not samples or len(samples) < 20:
            raise HTTPException(status_code=400, detail="Amostras insuficientes (mínimo 20).")

        # 1. Extração dos vetores NumPy
        timestamps = np.array([s.timestamp for s in samples], dtype=np.float64)
        ax = np.array([s.accel_x for s in samples])
        ay = np.array([s.accel_y for s in samples])
        az = np.array([s.accel_z for s in samples])
        
        gx = np.array([s.gyro_x for s in samples])
        gy = np.array([s.gyro_y for s in samples])
        gz = np.array([s.gyro_z for s in samples])

        # 2. CÁLCULO DA FREQUÊNCIA REAL DE AMOSTRAGEM (hz_real)
        time_delta = timestamps[-1] - timestamps[0]
        if time_delta > 0:
            actual_sample_rate = float((len(timestamps) - 1) / time_delta)
        else:
            actual_sample_rate = 25.0  # Média padrão de celulares na web

        # Trava para evitar valores discrepantes causados por bugs no browser
        actual_sample_rate = float(np.clip(actual_sample_rate, 10.0, 100.0))

        # 3. VERIFICAÇÃO DE CHACOALHADO GLOBAL (Limite liberado para balanço natural)
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

        # 4. FILTRAGEM ADAPTATIVA
        raw_acc_magnitude = np.sqrt(ax**2 + ay**2 + az**2)
        bw_filter = ButterworthLowPassFilter(cutoff_hz=2.2, sample_rate_hz=actual_sample_rate, order=2)
        filtered_magnitude = bw_filter.apply(raw_acc_magnitude, sample_rate_hz=actual_sample_rate)

        # 5. DETECÇÃO DE PASSOS
        detector = PeakStepDetector(sample_rate_hz=actual_sample_rate, weinberg_k=0.45)
        step_events = detector.detect(
            timestamps=timestamps,
            filtered_magnitude=filtered_magnitude,
            gyro_magnitude=gyro_magnitude,
            sample_rate_hz=actual_sample_rate
        )

        if not step_events:
            return {
                "status": "warning",
                "valid": False,
                "source": source,
                "target": target,
                "message": "Nenhum passo identificado (caminhada muito suave ou repouso).",
                "steps_count": 0,
                "distance_m": 0.0,
                "mean_yaw_rad": 0.0
            }

        # 6. CÁLCULO DE DISTÂNCIA E ORIENTAÇÃO
        total_distance_m = sum(s.step_length_m for s in step_events)
        
        estimator = MadgwickAttitudeEstimator(gain=0.033)
        quaternions = estimator.update_series(samples)
        mean_yaw_rad = float(np.mean([q.yaw for q in quaternions]))

        # 7. PERSISTÊNCIA NO BANCO E GRAFO
        self.db_manager.save_edge(source, target, total_distance_m, mean_yaw_rad)
        angle_deg = float(np.degrees(mean_yaw_rad))
        self.topo_map.connect_checkpoints(source, target, distance=total_distance_m, angle_deg=angle_deg)

        return {
            "status": "success",
            "valid": True,
            "source": source,
            "target": target,
            "message": f"Trecho validado! Rate: {round(actual_sample_rate, 1)}Hz",
            "steps_count": len(step_events),
            "distance_m": round(total_distance_m, 2),
            "mean_yaw_rad": round(mean_yaw_rad, 4)
        }