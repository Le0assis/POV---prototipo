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

        # 1. Converte e extrai vetores NumPy
        timestamps = np.array([s.timestamp for s in samples], dtype=np.float64)
        ax = np.array([s.accel_x for s in samples])
        ay = np.array([s.accel_y for s in samples])
        az = np.array([s.accel_z for s in samples])
        
        gx = np.array([s.gyro_x for s in samples])
        gy = np.array([s.gyro_y for s in samples])
        gz = np.array([s.gyro_z for s in samples])

        # 2. Magnitude do giroscópio (rad/s) para trava de chacoalhado
        gyro_magnitude = np.sqrt(gx**2 + gy**2 + gz**2)

        # 3. Filtro Butterworth na magnitude da aceleração
        raw_acc_magnitude = np.sqrt(ax**2 + ay**2 + az**2)
        bw_filter = ButterworthLowPassFilter(cutoff_hz=3.0, sample_rate_hz=50.0, order=4)
        filtered_magnitude = bw_filter.apply(raw_acc_magnitude)

        # 4. Detecção de passos com trava de giroscópio
        detector = PeakStepDetector(sample_rate_hz=50.0, weinberg_k=0.48)
        step_events = detector.detect(
            timestamps=timestamps,
            filtered_magnitude=filtered_magnitude,
            gyro_magnitude=gyro_magnitude
        )

        # Trata o caso em que o movimento foi descartado/chacoalhado
        if not step_events:
            return {
                "status": "warning",
                "valid": False,
                "source": source,
                "target": target,
                "message": "Movimento descartado (chacoalhado/repouso detectado pelo giroscópio).",
                "steps_count": 0,
                "distance_m": 0.0,
                "mean_yaw_rad": 0.0
            }

        # 5. Cálculo de distância (Weinberg) e orientação (Madgwick)
        total_distance_m = sum(s.step_length_m for s in step_events)
        
        estimator = MadgwickAttitudeEstimator(gain=0.033)
        quaternions = estimator.update_series(samples)
        mean_yaw_rad = float(np.mean([q.yaw for q in quaternions]))

        # 6. Persistência no banco MySQL e grafo
        self.db_manager.save_edge(source, target, total_distance_m, mean_yaw_rad)
        angle_deg = float(np.degrees(mean_yaw_rad))
        self.topo_map.connect_checkpoints(source, target, distance=total_distance_m, angle_deg=angle_deg)

        return {
            "status": "success",
            "valid": True,
            "source": source,
            "target": target,
            "message": "Trecho validado e registrado no grafo/banco.",
            "steps_count": len(step_events),
            "distance_m": round(total_distance_m, 2),
            "mean_yaw_rad": round(mean_yaw_rad, 4)
        }