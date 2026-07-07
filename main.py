import numpy as np
# Importe as suas classes criadas:
from map.topological_map import TopologicalMap
from map.topological_matcher import TopologicalMatcher
from map.router import TopologicalRouter
from pdr.steps import StepEvent

def build_environment_map() -> TopologicalMap:
    """Função auxiliar para construir o grafo do prédio de testes."""
    topo_map = TopologicalMap()
    
    # 1. Adicione os checkpoints do local real do seu teste
    topo_map.add_checkpoint("Recepcao")
    topo_map.add_checkpoint("Corredor Central")
    topo_map.add_checkpoint("Escada")
    topo_map.add_checkpoint("Sala de TI")
    
    # 2. Crie as conexões com as distâncias em metros e ângulos em graus
    topo_map.connect_checkpoints("Recepcao", "Corredor Central", distance=5.0, angle_deg=90)
    topo_map.connect_checkpoints("Corredor Central", "Escada", distance=6.0, angle_deg=90)
    topo_map.connect_checkpoints("Recepcao", "Sala de TI", distance=4.0, angle_deg=180)
    
    return topo_map

def main():
    print("=== INICIANDO SISTEMA DE NAVEGAÇÃO E LOCALIZAÇÃO INDOOR ===")
    
    # 1. Inicializa o ambiente
    topo_map = build_environment_map()
    router = TopologicalRouter(topo_map)
    
    # 2. Define o ponto de partida conhecido e inicializa o Matcher
    ponto_inicial = "Recepcao"
    matcher = TopologicalMatcher(topo_map, starting_node=ponto_inicial)
    
    # 3. Define um destino final desejado pelo usuário para testar o Router
    destino_desejado = "Escada"
    rota_teorica = router.calculate_route(ponto_inicial, destino_desejado)
    print(f"Rota planejada pelo Dijkstra para chegar em '{destino_desejado}': {rota_teorica}\n")
    
    # 4. SIMULAÇÃO DOS SENSORES EM TEMPO REAL
    # Imagine que esses dados vieram do seu pipeline de PDR rodando sobre um arquivo CSV.
    # Vamos simular passos reais: o usuário anda 5 metros a 90 graus (deve ir para o Corredor Central)
    # Cada StepEvent simulado tem comprimento de passo de 1.0 metro.
    passos_simulados = [
        {"length": 1.0, "yaw_deg": 90},
        {"length": 1.0, "yaw_deg": 90},
        {"length": 1.0, "yaw_deg": 90},
        {"length": 1.0, "yaw_deg": 90},
        {"length": 1.0, "yaw_deg": 90}, # Aqui ele deve atingir os 5.0 metros do corredor!
        {"length": 1.0, "yaw_deg": 90}, # Próximo corredor...
    ]
    
    print("Iniciando caminhada. Processando passos do PDR...")
    no_anterior = ponto_inicial
    
    for i, passo in enumerate(passos_simulados):
        # A) Converte o ângulo do sensor simulado para radianos (como o Madgwick faz)
        yaw_rad = np.radians(passo["yaw_deg"])
        
        # B) Cria um objeto de passo simulado condizente com a interface do seu PDR
        # (Se a sua classe StepEvent exigir parâmetros, instancie-a aqui de forma correta)
        # Ex: step_event = StepEvent(step_length_m=passo["length"])
        
        for i, passo in enumerate(passos_simulados):
        # Converte o ângulo do sensor simulado para radianos
            yaw_rad = np.radians(passo["yaw_deg"])
            
            # CORREÇÃO AQUI: Passando os argumentos obrigatórios fictícios
            step_event = StepEvent(
                timestamp=float(i),     # Um segundo fictício por passo
                index=i,                # Índice do passo na caminhada
                cadence_spm=60.0,       # Cadência padrão de 60 passos por minuto
                step_length_m=passo["length"] # O comprimento simulado (1.0m)
            )
        
        # Injeta o passo no seu Módulo 2 (Matcher)
        no_atual = matcher.process_step(step_event, yaw_rad)
        
        # C) Injeta o passo no seu Módulo 2 (Matcher)
        # IMPORTANTE: Você precisa ajustar o argumento da chamada conforme sua implementação.
        no_atual = matcher.process_step(step_event, yaw_rad)
        
        # D) Só printa na tela se houver mudança de estado semântico
        if no_atual != no_anterior:
            print(f"[EVENTO] Mudança detectada no passo {i+1}!")
            print(f" -> Usuário saiu de '{no_anterior}' e entrou em '{no_atual}'")
            no_anterior = no_atual
            
            # Recalcula a rota a partir de onde ele está agora se necessário
            nova_rota = router.calculate_route(no_atual, destino_desejado)
            print(f" -> Nova rota até o destino atualizada: {nova_rota}")

    print("\nFim da simulação.")

if __name__ == "__main__":
    main()