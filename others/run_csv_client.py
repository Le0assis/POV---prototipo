import time
import requests
from pathlib import Path
import numpy as np

# Imports de infraestrutura e PDR do seu projeto
from sensors.repository import CSVSensorRepository
from filters.madgwick import MadgwickAttitudeEstimator
from filters.moving_average import MovingAverageFilter
from pdr.steps import PeakStepDetector 
from pdr.magnitude import compute_magnitude_series

API_URL = "http://127.0.0.1:8000/api/localize"


def process_csv_and_stream_to_web(csv_path: Path):
    """Carrega as amostras do CSV pelo Repositório, processa o PDR 
    e dispara os passos para o servidor Web FastAPI.
    """
    
    # 1. Carrega as amostras brutas via Repositório
    repo = CSVSensorRepository(filepath=csv_path)
    samples = repo.get_samples()

    if not samples:
        print("[ERRO] Nenhuma amostra carregada do CSV.")
        return

    print(f"\n=== Processando {len(samples)} amostras de sensores para a Web ===")

    timestamps = np.array([s.timestamp for s in samples], dtype=np.float64)
    
    # 2. Pipeline de Sinal (Magnitude + Filtro de Média Móvel)
    raw_magnitude = compute_magnitude_series(samples)
    ma_filter = MovingAverageFilter(window_size=7)
    filtered_magnitude = ma_filter.apply(raw_magnitude)
    
    # 3. Orientação 3D (Madgwick)
    magwick = MadgwickAttitudeEstimator(0.02)
    yaw_series = magwick.update_series(samples) 
    
    # 4. Detecção de Passos
    step_detector = PeakStepDetector(sample_rate_hz=50.0, weinberg_k=0.55)
    step_events = step_detector.detect(timestamps, filtered_magnitude=filtered_magnitude)
    
    print(f"\n[PDR] Passos identificados após filtro de Média Móvel: {len(step_events)}")
    
    realized_steps = 0
    
    # 5. Transmissão dos passos para o Servidor Web
    for i, step in enumerate(step_events, start=1):
        realized_steps += 1
        
        # Encontra o índice da amostra mais próxima do momento do passo
        step_idx = np.argmin(np.abs(timestamps - step.timestamp))

        current_yaw = float(yaw_series[step_idx].yaw)
        step_length = float(step.step_length_m)
        
        # Payload formatado para a API
        payload = {
            "step_length_m": step_length,
            "yaw_rad": current_yaw
        }

        try:
            response = requests.post(API_URL, json=payload, timeout=2.0)

            if response.status_code == 200:
                data = response.json()
                current_node = data.get("current_node")
                accumulated_dist = data.get("accumulated_distance_m", 0.0)

                print(
                    f"[Passo {realized_steps:02d} | Amostra {step_idx}] "
                    f"➔ Enviado: {step_length:.2f}m | Yaw: {current_yaw:.2f} rad "
                    f"==> RESPOSTA WEB: '{current_node}' (Total: {accumulated_dist:.2f}m)"
                )
            else:
                print(f"[Erro API] Status {response.status_code}: {response.text}")

        except requests.exceptions.ConnectionError:
            print("\n[ERRO CRÍTICO] Servidor FastAPI (Uvicorn) desconectado! Ligue o 'uvicorn app:app --reload'")
            break

        # Simula o tempo de caminhada entre os passos
        time.sleep(0.3)

    print(f"\n=== Processamento Concluído! Total de passos enviados: {realized_steps} ===")


if __name__ == "__main__":
    caminho_csv = Path("datasets\\sample_walk.csv") 
    process_csv_and_stream_to_web(caminho_csv)