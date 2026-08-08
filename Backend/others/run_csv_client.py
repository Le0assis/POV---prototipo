import time
import requests
from pathlib import Path
import numpy as np

# Imports oficiais dos módulos do seu projeto
from sensors.repository import CSVSensorRepository
from filters.butterworth import ButterworthLowPassFilter
from filters.madgwick import MadgwickAttitudeEstimator
from pdr.steps import PeakStepDetector, StepEvent
from pdr.magnitude import compute_magnitude_series

API_URL = "http://127.0.0.1:8000/api/localize"


def process_csv_and_stream_to_web(csv_path: Path):
    """Carrega amostras do CSV, executa a filtragem Butterworth e a fusão de 
    sensores via Madgwick (1 parâmetro de ganho), e envia os passos para a API.
    """
    
    # 1. Carrega as amostras do CSV pelo Repositório
    repo = CSVSensorRepository(filepath=csv_path)
    samples = repo.get_samples()

    if not samples:
        print(f"[ERRO] Nenhuma amostra carregada do arquivo: {csv_path}")
        return

    print(f"\n=== Processando {len(samples)} amostras de sensores ===")

    timestamps = np.array([s.timestamp for s in samples], dtype=np.float64)
    
    # 2. Pipeline de Sinal (Magnitude + Filtro Butterworth)
    raw_magnitude = compute_magnitude_series(samples)
    bw_filter = ButterworthLowPassFilter(cutoff_hz=3.0, sample_rate_hz=50.0, order=4)
    
    filtered_magnitude = bw_filter.apply(raw_magnitude)

    # 3. Orientação 3D (Instanciação do Madgwick com 1 parâmetro: ganho)
    estimator = MadgwickAttitudeEstimator(gain=0.033)
    quaternions = estimator.update_series(samples)

    # 4. Detecção Adaptativa de Passos (PeakStepDetector + Weinberg)
    step_detector = PeakStepDetector(sample_rate_hz=50.0, weinberg_k=0.48)
    step_events: list[StepEvent] = step_detector.detect(
        timestamps=timestamps, 
        filtered_magnitude=filtered_magnitude
    )

    print(f"[PDR] Passos identificados: {len(step_events)}")

    last_timestamp = None

    # 5. Transmissão sequencial dos passos para o servidor FastAPI
    for i, step in enumerate(step_events, start=1):
        step_idx = step.index
        
        # Extrai o ângulo Yaw do quatérnio na amostra exata do impacto da pisada
        current_yaw = float(quaternions[step_idx].yaw)
        step_length = float(step.step_length_m)

        payload = {
            "step_length_m": step_length,
            "yaw_rad": current_yaw
        }

        try:
            response = requests.post(API_URL, json=payload, timeout=2.0)

            if response.status_code == 200:
                data = response.json()
                current_node = data.get("current_node", "N/A")
                accumulated_dist = data.get("accumulated_distance_m", 0.0)

                print(
                    f"[Passo {i:02d} | Amostra {step_idx:04d} | Cadência: {step.cadence_spm:.1f} SPM] "
                    f"➔ Enviado: {step_length:.2f}m | Yaw: {current_yaw:.2f} rad "
                    f"==> RESPOSTA API: '{current_node}' (Total: {accumulated_dist:.2f}m)"
                )
            else:
                print(f"[Erro API] Status {response.status_code}: {response.text}")

        except requests.exceptions.ConnectionError:
            print("\n[ERRO CRÍTICO] Servidor FastAPI desconectado! Inicie o Uvicorn na porta 8000.")
            break

        # Simula a cadência de caminhada com base nos timestamps reais das pisadas
        if last_timestamp is not None:
            dt = step.timestamp - last_timestamp
            sleep_time = float(np.clip(dt, 0.2, 1.0))
            time.sleep(sleep_time)

        last_timestamp = step.timestamp

    print(f"\n=== Processamento Concluído! Total de passos enviados: {len(step_events)} ===")


if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parent.parent
    caminho_csv = base_dir / "datasets" / "sample_walk.csv"

    process_csv_and_stream_to_web(caminho_csv)