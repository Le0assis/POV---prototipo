import numpy as np
from datasets.ManagerDatabase import ConexaoBD

class MapDatabaseManager:
    """Responsável por salvar e carregar o grafo diretamente do MySQL do XAMPP."""

    def __init__(self, database: ConexaoBD):
        self.db = database
    
    def save_checkpoint(self, name: str):
        """Salva um novo nó semântico no banco de dados."""
        sql = """INSERT INTO checkpoints (name) VALUES (%s)"""
        # IMPORTANTE: Notar a vírgula (name,) para o Python entender que é uma tupla de 1 elemento
        succsses = self.db.executar_comando(sql, (name,))
        
        if succsses:
            print(f"Checkpoint {name} adicionado com sucesso")
            return True
        else:
            print(f"Erro ao adicionar checkpoint {name}")
            return False
        
    def save_edge(self, source: str, target: str, distance: float, heading_rad: float):
        """Executa os INSERTS na tabela de arestas para salvar a ida e a volta."""
        sql = """INSERT INTO edges (source_node, target_node, distance_m, heading_rad) 
                 VALUES (%s, %s, %s, %s)"""
        
        # 1. Salva o caminho de IDA (Source -> Target)
        succes = self.db.executar_comando(sql, (source, target, distance, heading_rad))
        
        # 2. Calcula o ângulo inverso de VOLTA em radianos (Target -> Source)
        # Adiciona 180 graus (pi radianos) e usa o mod (2*pi) para manter entre 0 e 2*pi
        inverse_heading = (heading_rad + np.pi) % (2 * np.pi)
        
        # 3. Salva o caminho de VOLTA (Target -> Source)
        succes_back = self.db.executar_comando(sql, (target, source, distance, inverse_heading))
        
        if succes and succes_back:
            print("Edge com {target, source} de ida e volta foi adicionado com suceso ")
            return True
        else:
            print(f"Erro ao adicionar edge com {target, source}")
            return False
                
    def load_map_into_system(self, topo_map) -> None:
        """Carrega todos os dados persistidos no MySQL e reconstrói o grafo na memória."""
        
        # --- PASSO 1: CARREGAR OS CHECKPOINTS ---
        sql_nodes = "SELECT name FROM checkpoints"
        # O executar_consulta vai te retornar uma lista de dicionários se você usou dictionary=True
        # Ex: [{'name': 'Recepcao'}, {'name': 'Corredor Central'}]
        rows_nodes = self.db.executar_consulta(sql_nodes)
        
        if rows_nodes:
            for row in rows_nodes:
                # Extraia o nome do nó e adicione ao topo_map usando a função add_checkpoint
                node_name = row['name']
                topo_map.add_checkpoint(node_name)
                print(f"[BD -> Sistema] Checkpoint carregado: {node_name}")

        # --- PASSO 2: CARREGAR AS ARESTAS ---
        sql_edges = "SELECT source_node, target_node, distance_m, heading_rad FROM edges"
        rows_edges = self.db.executar_consulta(sql_edges)
        
        if rows_edges:
            for row in rows_edges:
                # Extraia os dados de cada coluna do dicionário da linha
                source = row['source_node']
                target = row['target_node']
                distance = row['distance_m']
                heading_rad = row['heading_rad']
                
                # Como connect_checkpoints do seu módulo original pedia em graus, 
                # converta de volta de radianos para graus usando np.degrees()
                heading_deg = np.degrees(heading_rad)
                
                # Chame o método do seu mapa para criar a conexão na memória
                topo_map.connect_checkpoints(source, target, distance, heading_deg)
                print(f"[BD -> Sistema] Conexão carregada: {source} -> {target} ({distance}m)")