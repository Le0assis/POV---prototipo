import numpy as np
from datasets.ManagerDatabase import ConexaoBD

class MapDatabaseManager:
    """Responsável por salvar e carregar o grafo diretamente do MySQL do XAMPP."""

    def __init__(self, database: ConexaoBD):
        self.db = database
    
    def save_checkpoint(self, session_id: str, name: str):
        """Salva um novo nó semântico no banco de dados associado à sessão."""
        sql = """INSERT INTO checkpoints (session_id, name) VALUES (%s, %s)"""
        success = self.db.execute_query(sql, (session_id, name))
        
        if success:
            print(f"[BD] Checkpoint '{name}' adicionado com sucesso na sessão '{session_id}'.")
            return True
        else:
            print(f"[BD ERRO] Erro ao adicionar checkpoint '{name}'.")
            return False
        
    def save_edge(self, session_id: str, source: str, target: str, distance: float, heading_rad: float):
        """Executa os INSERTS na tabela de arestas para salvar a ida e a volta com session_id."""
        # CORRIGIDO: session_id adicionado às colunas para bater com os 5 placeholders (%s)
        sql = """INSERT INTO edges (session_id, source_node, target_node, distance_m, heading_rad) 
                 VALUES (%s, %s, %s, %s, %s)"""
        
        # 1. Salva o caminho de IDA (Source -> Target)
        success_go = self.db.execute_query(sql, (session_id, source, target, distance, heading_rad))
        
        # 2. Calcula o ângulo inverso de VOLTA em radianos (Target -> Source)
        inverse_heading = (heading_rad + np.pi) % (2 * np.pi)
        
        # 3. Salva o caminho de VOLTA (Target -> Source)
        success_back = self.db.execute_query(sql, (session_id, target, source, distance, inverse_heading))
        
        if success_go and success_back:
            print(f"[BD] Edge '{source}' <-> '{target}' adicionado com sucesso.")
            return True
        else:
            print(f"[BD ERRO] Erro ao adicionar edge com {source, target}.")
            return False
                
    def load_map_into_system(self, topo_map, session_id="default_session") -> None:
        """Carrega os checkpoints e conexões persistidos no MySQL filtrados pelo session_id."""
        
        # --- PASSO 1: CARREGAR OS CHECKPOINTS DA SESSÃO ---
        sql_nodes = "SELECT name FROM checkpoints WHERE session_id = %s"
        rows_nodes = self.db.execute_search(sql_nodes, (session_id,))
        
        if rows_nodes:
            for row in rows_nodes:
                node_name = row['name']
                topo_map.add_checkpoint(node_name)
                print(f"[BD -> Sistema] Checkpoint carregado: {node_name}")

        # --- PASSO 2: CARREGAR AS ARESTAS DA SESSÃO ---
        sql_edges = "SELECT source_node, target_node, distance_m, heading_rad FROM edges WHERE session_id = %s"
        rows_edges = self.db.execute_search(sql_edges, (session_id,))
        
        if rows_edges:
            for row in rows_edges:
                source = row['source_node']
                target = row['target_node']
                distance = row['distance_m']
                heading_rad = row['heading_rad']
                
                # Converte de radianos para graus
                heading_deg = float(np.degrees(heading_rad))
                
                topo_map.connect_checkpoints(source, target, distance, heading_deg)
                print(f"[BD -> Sistema] Conexão carregada: {source} -> {target} ({distance}m)")
                
    def save_sensor_log(self, session_id: str, source: str, target: str, csv_data: str):
        """Salva a string CSV dos sensores brutos na tabela sensors_log vinculada à sessão."""
        query = """
            INSERT INTO sensors_log (session_id, source, target, raw_csv)
            VALUES (%s, %s, %s, %s)
        """
        success = self.db.execute_query(query, (session_id, source, target, csv_data))

        if success:
            print(f"[BD] Log de sensores salvo com sucesso para a sessão '{session_id}'.")
            return True
        else:
            print(f"[BD ERRO] Erro ao processar log de sensores.")
            return False
        
    def get_sensor_log_csv(self, log_id: int) -> str | None:
        """Busca o conteúdo CSV de um log específico pelo ID."""
        query = "SELECT raw_csv FROM sensors_log WHERE id = %s"
        result = self.db.execute_search(query, (log_id,))
        
        if result and len(result) > 0:
            return result[0]['raw_csv'] if isinstance(result[0], dict) else result[0][0]
        return None