import unittest
from map.topological_map import TopologicalMap
from map.router import TopologicalRouter

class TestTopologicalRouterRobust(unittest.TestCase):

    def setUp(self) -> None:
        """Configura um mapa complexo de múltiplos cômodos e andares antes de cada teste.
        
        Cenário Mapeado:
        - O 'Corredor Central' liga a 'Recepcao' à 'Escada'.
        - Da 'Recepcao', há dois caminhos para a 'Sala de TI':
            1. Caminho Curto: Direto (distância 4.0)
            2. Caminho Longo: Passando por 'Almoxarifado' e 'Laboratorio' (distância total 10.0)
        - A 'Escada' leva ao Segundo Andar ('Diretoria').
        - Existe uma 'Area Isolada' (um checkpoint que não se conecta a ninguém).
        """
        self.map = TopologicalMap()
        
        # 1. Adiciona os Checkpoints (Nós)
        nodes = [
            "Recepcao", "Corredor Central", "Escada", 
            "Almoxarifado", "Laboratorio", "Sala de TI", 
            "Diretoria", "Area Isolada"
        ]
        for node in nodes:
            self.map.add_checkpoint(node)
            
        # 2. Conecta a Espinha Dorsal (Recepção <-> Corredor <-> Escada)
        self.map.connect_checkpoints("Recepcao", "Corredor Central", distance=5.0, angle_deg=90)
        self.map.connect_checkpoints("Corredor Central", "Escada", distance=6.0, angle_deg=90)
        
        # 3. Conecta o Caminho CURTO (Recepção <-> Sala de TI)
        self.map.connect_checkpoints("Recepcao", "Sala de TI", distance=4.0, angle_deg=180)
        
        # 4. Conecta o Caminho LONGO alternativo (Recepção <-> Almoxarifado <-> Laboratório <-> Sala de TI)
        self.map.connect_checkpoints("Recepcao", "Almoxarifado", distance=3.0, angle_deg=0)
        self.map.connect_checkpoints("Almoxarifado", "Laboratorio", distance=4.0, angle_deg=90)
        self.map.connect_checkpoints("Laboratorio", "Sala de TI", distance=3.0, angle_deg=180)
        
        # 5. Conecta a Escada ao Segundo Andar
        self.map.connect_checkpoints("Escada", "Diretoria", distance=10.0, angle_deg=0) # Subida/Rampa simulada
        
        # Instancia o Roteador testado
        self.router = TopologicalRouter(self.map)

    def test_caminho_direto_simples(self) -> None:
        """Garante que ele acha caminhos simples na espinha dorsal."""
        route = self.router.calculate_route("Recepcao", "Escada")
        expected = ["Recepcao", "Corredor Central", "Escada"]
        self.assertEqual(route, expected)

    def test_escolha_do_caminho_mais_curto(self) -> None:
        """CRUCIAL: O Dijkstra DEVE escolher o caminho de distância 4.0 em vez do de 10.0

        para ir da Recepção à Sala de TI.
        """
        route = self.router.calculate_route("Recepcao", "Sala de TI")
        expected = ["Recepcao", "Sala de TI"]
        self.assertEqual(route, expected)

    def test_caminho_longo_com_multiplos_nos(self) -> None:
        """Garante que ele consegue cruzar vários nós até o segundo andar."""
        route = self.router.calculate_route("Almoxarifado", "Diretoria")
        # Caminho ideal: Almoxarifado -> Recepcao -> Corredor Central -> Escada -> Diretoria
        expected = ["Almoxarifado", "Recepcao", "Corredor Central", "Escada", "Diretoria"]
        self.assertEqual(route, expected)

    def test_nós_inexistentes(self) -> None:
        """Testa a validação contra digitação errada de nós."""
        route_invalid_start = self.router.calculate_route("BanheiroQueNaoExiste", "Recepcao")
        route_invalid_end = self.router.calculate_route("Recepcao", "GaragemFake")
        
        self.assertEqual(route_invalid_start, [])
        self.assertEqual(route_invalid_end, [])

    def test_no_isolado_sem_saida(self) -> None:
        """Testa se o algoritmo falha graciosamente retornando [] se o destino for inalcançável."""
        route = self.router.calculate_route("Recepcao", "Area Isolada")
        self.assertEqual(route, [])

    def test_mesmo_ponto_origem_e_destino(self) -> None:
        """Se o usuário pedir rota de onde ele já está, deve retornar apenas o próprio nó."""
        route = self.router.calculate_route("Recepcao", "Recepcao")
        self.assertEqual(route, ["Recepcao"])

if __name__ == "__main__":
    unittest.main()