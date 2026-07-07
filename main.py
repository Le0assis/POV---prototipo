from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

# Importações das suas camadas coerentes
from sensors.repository import CSVSensorRepository
from filters.butterworth import ButterworthLowPassFilter
from filters.madgwick import MadgwickAttitudeEstimator
from pdr.magnitude import compute_magnitude_series
from pdr.altitude import compute_altitude
from pdr.steps import PeakStepDetector
from pdr.tracker import TrajectoryTracker

def run_pdr_pipeline(repository, sample_rate_hz: float = 100.0):
    print("====== INICIANDO ENGINE PDR INDOOR ======")
    
    # 1. Carrega via Repositório (Independente de Infra)
    samples = repository.get_samples()
    if not samples:
        print("Erro: Nenhum dado encontrado.")
        return
        
    timestamps = np.array([s.timestamp for s in samples])
    
    # 2. Calcula a Magnitude Invariante (Etapa 2)
    raw_magnitude = compute_magnitude_series(samples)
    
    # 3. Filtra ruídos harmônicos com Butterworth (Etapa 3)
    lpf = ButterworthLowPassFilter(cutoff_hz=3.0, sample_rate_hz=sample_rate_hz, order=4)
    filtered_magnitude = lpf.apply(raw_magnitude)
    
    # 4. Detecção Física de Passos (Etapas 4, 5 e 6)
    step_detector = PeakStepDetector(sample_rate_hz=sample_rate_hz, weinberg_k=0.55)
    detected_steps = step_detector.detect(timestamps, filtered_magnitude)
    print(f"[Engine] Passos físicos detectados com sucesso: {len(detected_steps)}")
    
    # 5. Atualização Contínua de Orientação por Fusão (Madgwick) e Altitude
    madgwick = MadgwickAttitudeEstimator(gain=0.033)
    orientations = []
    altitudes = []
    
    for i, s in enumerate(samples):
        dt = timestamps[i] - timestamps[i - 1] if i > 0 else (1.0 / sample_rate_hz)
        q = madgwick.update(
            gx=s.gx, gy=s.gy, gz=s.gz,
            ax=s.ax, ay=s.ay, az=s.az,
            mx=s.mx, my=s.my, mz=s.mz,
            dt=dt
        )
        orientations.append(q)
        altitudes.append(compute_altitude(s.pressure))
        
    # 6. Integração Trigonométrica no Espaço Map (Etapas 9 e 15)
    tracker = TrajectoryTracker(start_x=0.0, start_y=0.0, start_z=altitudes[0])
    for step in detected_steps:
        idx = step.index
        tracker.apply_step(step, orientations[idx], altitudes[idx])
        
    # 7. Renderização Gráfica do Deslocamento Final
    render_map(tracker.trajectory)

def render_map(trajectory):
    if not trajectory:
        print("Erro: Trajetória vazia.")
        return
    x = [p.x for p in trajectory]
    y = [p.y for p in trajectory]
    
    plt.figure(figsize=(9, 7))
    plt.plot(x, y, marker='o', linestyle='-', color='#1f77b4', markersize=4, label="Trajetória PDR")
    plt.plot(x[0], y[0], marker='s', color='green', markersize=9, label="Origem (0,0)")
    plt.plot(x[-1], y[-1], marker='X', color='red', markersize=9, label="Destino Final")
    
    plt.title("Sistema de Posicionamento Interno (PDR) — Resultado Final")
    plt.xlabel("Eixo X (Metros)"); plt.ylabel("Eixo Y (Metros)")
    plt.legend(); plt.grid(True, linestyle=":", alpha=0.6); plt.axis('equal')
    plt.show()

if __name__ == "__main__":
    # Certifique-se de que o arquivo sample_walk.csv está dentro da pasta 'datasets'
    DATA_PATH = Path(__file__).parent / "datasets" / "sample_walk.csv"
    
    # Passamos a infraestrutura via Injeção de Dependência
    csv_repo = CSVSensorRepository(DATA_PATH)
    run_pdr_pipeline(repository=csv_repo, sample_rate_hz=100.0)