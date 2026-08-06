import time
import requests

# Endereço da sua API FastAPI rodando no Uvicorn
API_URL = "http://127.0.0.1:8000/api/localize"

def simular_envio_passos():
    """
    Simula o envio dos eventos de passos (PDR) para o backend Web.
    Você pode adaptar a lista de passos para ser alimentada em tempo real 
    pelo seu script que lê e processa o arquivo CSV.
    """
    
    # Sequência de passos simulada: (comprimento_metros, angulo_yaw_radianos)
    # Supondo 5 passos em linha reta (~0 rad) e depois 4 passos após virar (~1.57 rad)
    passos_simulados = [
        {"step_length_m": 0.70, "yaw_rad": 0.0},
        {"step_length_m": 0.75, "yaw_rad": 0.02},
        {"step_length_m": 0.72, "yaw_rad": -0.01},
        {"step_length_m": 0.70, "yaw_rad": 0.01},
        {"step_length_m": 0.73, "yaw_rad": 0.0},
        # Curva / Mudança de corredor
        {"step_length_m": 0.71, "yaw_rad": 1.57},
        {"step_length_m": 0.74, "yaw_rad": 1.55},
        {"step_length_m": 0.72, "yaw_rad": 1.58},
        {"step_length_m": 0.70, "yaw_rad": 1.57},
    ]

    print("\n=== INICIANDO SIMULAÇÃO DE NAVEGAÇÃO ONLINE (CLIENTE -> API) ===\n")

    for i, passo in enumerate(passos_simulados, start=1):
        try:
            # Envia o payload JSON idêntico ao exigido pelo StepSensorSchema da API
            response = requests.post(API_URL, json=passo)

            if response.status_code == 200:
                dados = response.json()
                no_atual = dados.get("current_node")
                dist_acumulada = dados.get("accumulated_distance_m", 0.0)

                print(f"[Passo {i:02d}] ➔ Enviando: {passo['step_length_m']}m | Yaw: {passo['yaw_rad']} rad")
                print(f"           ↳ RESPOSTA DA API: Usuário está em '{no_atual}' (Acumulado: {dist_acumulada:.2f}m)\n")
            else:
                print(f"[Passo {i:02d}] Erro na API ({response.status_code}): {response.text}")

        except requests.exceptions.ConnectionError:
            print("[ERRO CRÍTICO] Falha ao conectar. Verifique se o Uvicorn está rodando em http://127.0.0.1:8000")
            break

        # Pausa de 0.8s para simular o tempo real do usuário caminhando
        time.sleep(0.8)

if __name__ == "__main__":
    simular_envio_passos()