Contexto do Projeto: Sistema POV (Pedestrian Dead Reckoning & Topological Mapping)Este documento serve como a Base de Conhecimento Central do projeto POV. Ele sintetiza toda a arquitetura, regras de negócio, decisões técnicas, histórico de correções e próximos passos para permitir que qualquer desenvolvedor ou inteligência artificial compreenda imediatamente o sistema e continue o desenvolvimento de forma fluida.1. Visão Geral do ProjetoNome do Projeto: POV (Ponto de Origem / Vista — Protótipo PDR)Objetivo Principal: Desenvolver um sistema de Navegação e Rastreamento de Pedestres em Ambientes Fechados (Indoor Pedestrian Dead Reckoning - PDR) utilizando apenas os sensores inerciais (IMU: acelerômetro e giroscópio) de smartphones, dispensando sinais de GPS. O sistema elimina falsos positivos de movimento (como chacoalhos manuais), detecta passos humanos reais, calcula distâncias e direções (azimute/yaw) e registra os trajetos em um mapa topológico baseado em grafos.Caso de Uso / Público-Alvo: Navegação e mapeamento em locais cobertos (hospitais, universidades, shoppings, galpões industriais) onde o GPS é inoperante ou impreciso, e auditoria de dados inerciais para calibração de algoritmos PDR.2. Stack Tecnológica e FerramentasBackend & LinguagensLinguagem: Python 3.10+Framework Web: FastAPI (ASGI framework) com suporte a threads via AnyIO e Uvicorn.Processamento Científico e Matemática:NumPy: Manipulação de vetores, matrizes e álgebra linear.SciPy: Processamento de sinais, especificamente scipy.signal.find_peaks para detecção de picos de passos e implementação do filtro Butterworth.Banco de Dados & PersistênciaSGBD: MySQL (executado via XAMPP localmente ou containerizado em produção).Gerenciador SQL: MapDatabaseManager (encapsulamento customizado via drivers MySQL/Connector Python).Estruturas de Dados: Grafo topológico composto por checkpoints (nós) e trajetos validados (arestas), além da tabela sensors_log para auditoria de sinais inerciais brutos em formato CSV.FrontendTecnologias: HTML5, CSS3 e JavaScript puro (Vanilla JS).APIs de Hardware: DeviceMotionEvent (coleta de giroscópio/acelerômetro) e PageVisibility API.Interface: Telas simples de gravação (recorder.html), teste de upload (sensors_upload.html) e renderização do mapa em 2D (mapa-2d.html).Infraestrutura, CI/CD e FerramentasTúnel HTTP/HTTPS: Cloudflare Tunnel (cloudflared) para expor a API local FastAPI para dispositivos móveis externos em conexões HTTPS seguras.Versionamento: Git com estratégia de branches (main e dev).CI/CD: GitHub Actions configurado para verificação de sintaxe e testes na branch dev e deploy automatizado na branch main.3. Arquitetura e Estrutura de PastasO projeto adota uma Arquitetura em Camadas Modulares (API, Domínio PDR, Filtros Matemáticos e Persistência DB), separando o recebimento de requisições do processamento pesado de sinais.PlaintextPOV---prototipo/
├── Backend/
│   ├── api/
│   │   └── app.py                     # Instância FastAPI, endpoints REST e servidor de arquivos CSV
│   ├── datasets/
│   │   ├── create_tables.py           # DDL SQL: Inicialização e criação de tabelas (inc. sensors_log)
│   │   ├── generate_sample_dataset.py # Gerador de massa de testes de passos
│   │   ├── ManagerDatabase.py         # Conexão base do banco de dados
│   │   └── sample_walk.csv            # Arquivo de teste estático
│   ├── filters/
│   │   ├── attitude_estimator.py      # Invólucro de orientação e altitude
│   │   ├── butterworth.py             # Filtro Passa-Baixas Butterworth (2ª ordem)
│   │   ├── madgwick.py                # Algoritmo de Fusão Sensorial de Madgwick (3D)
│   │   ├── moving_average.py          # Filtros de média móvel
│   │   ├── quaternion.py              # Álgebra de quaternions e extração da aceleração vertical
│   │   └── signal_filter.py           # Utilitários gerais de tratamento de sinal
│   ├── map/
│   │   ├── MapDatabaseManager.py      # Métodos de banco para arestas, nós e salvamento de logs CSV
│   │   ├── router.py                  # Algoritmo de busca de rotas no grafo
│   │   ├── topological_map.py         # Abstração da estrutura de dados do Grafo
│   │   └── topological_matcher.py     # Casamento de trajetos no mapa
│   ├── others/
│   │   ├── run_csv_client.py          # Cliente HTTP para simulação de caminhada via CSV
│   │   └── seed_map.py                # População inicial de checkpoints no mapa
│   ├── pdr/
│   │   ├── processor.py               # Pipeline principal de PDR (Reamostragem -> Madgwick -> Shake -> Butterworth -> Peak -> DB)
│   │   ├── steps.py                   # Detector de picos de passos e Modelo de Weinberg (`PeakStepDetector`)
│   │   ├── tracker.py                 # Rastreador de deslocamento e posição acumulada
│   │   ├── magnitude.py               # Cálculos de magnitude escalar
│   │   └── altitude.py                # Estimativa de altitude
│   ├── sensors/
│   │   ├── accelerometer.py           # Abstrações de leitura de acelerômetro
│   │   ├── gyroscope.py               # Abstrações de leitura de giroscópio
│   │   └── sensor_sample.py           # DTOs/Modelos de amostras dos sensores
│   ├── static/                        # Páginas Web HTML/JS para gravação e visualização
│   └── requirements.txt               # Dependências Python do projeto
├── frontend/                          # Estrutura frontend adicional/legada
├── cloudflared-config.yml             # Configuração do túnel Cloudflare
└── README.md
4. Principais Funcionalidades e Regras de NegócioPipeline de Processamento PDR (pdr/processor.py)A requisição enviada ao endpoint de processamento segue rigorosamente a seguinte sequência síncrona:Plaintext[Amostras Brutas] 
       │
       ▼
[1. Reamostragem Uniforme (TARGET_HZ)]
       │
       ▼
[2. Fusão Sensorial Madgwick (Instância Limpa por Requisição)]
       │
       ▼
[3. Projeção da Aceleração Vertical Real (Isolamento da Gravidade Terra)]
       │
       ▼
[4. Filtro de Shake Global (Giroscópio)] ──► (Se pico > 5.5 ou média > 2.2 rad/s) ──► Rejeita e Grava Log Inválido
       │
       ▼
[5. Filtro Passa-Baixas Butterworth (Cutoff = 2.2 Hz)]
       │
       ▼
[6. Detecção de Picos de Passos (Modelo de Weinberg)] ──► (Se 0 passos) ──► Rejeita e Grava Log Inválido
       │
       ▼
[7. Cálculo do Azimute Média (Yaw Média)]
       │
       ▼
[8. Persistência Dupla (Grava CSV em sensors_log como VÁLIDO + Salva Aresta no Grafo Topológico)]
Regras de Negócio CríticasReamostragem Uniforme: Dispositivos móveis transmitem dados inerciais com flutuação de frequência (jitter). O backend obrigatoriamente reamostra o vetor recebido para uma frequência fixa de $50\text{ Hz}$ (TARGET_HZ = 50) antes da aplicação dos filtros.Isolamento da Aceleração Vertical Real: Para evitar que o ângulo em que o usuário segura o celular afete a detecção, os quaternions gerados pelo algoritmo de Madgwick rotacionam o vetor acelerômetro do referencial do aparelho para o referencial da Terra. A aceleração vertical pura ($a_{vert}$) isola o impacto do pé no chão.Trava Anti-Chacoalho (Anti-Shake Lock):Se $max\_gyro > 5.5\text{ rad/s}$ OU $mean\_gyro > 2.2\text{ rad/s}$, a gravação é descartada imediatamente como movimento de chacoalho manual.O sistema gera uma resposta status: "warning" com valid: False e grava o log no banco informando a rejeição.Parâmetros da Detecção de Passos (pdr/steps.py):Base Acelerométrica Vertical: Em repouso, a aceleração vertical fica centrada na gravidade terrestre ($\approx 9.81\text{ m/s}^2$).Limiar de Altura Dinâmica (dynamic_height): $\max(9.95, \text{mean\_amplitude} + 0.12)\text{ m/s}^2$.Cadência Humana: Distância mínima entre picos de $0.33\text{ segundos}$ (no máximo ~3 passos por segundo).Variação de Amplitude (Weinberg): A diferença entre o pico de maior e menor aceleração na janela do passo ($\Delta a = a_{max} - a_{min}$) deve estar obrigatoriamente na faixa:$$0.55\text{ m/s}^2 \le \Delta a \le 4.5\text{ m/s}^2$$Modelo de Weinberg para Comprimento do Passo ($L$):$$L = k \cdot (\Delta a)^{0.25} \quad (\text{com } k = 0.45)$$O resultado é travado obrigatoriamente no intervalo fisiológico $[0.40\text{ m}, 0.95\text{ m}]$.Auditoria Geral e Persistência de Logs CSV (sensors_log):Toda requisição recebida gera uma conversão dos dados brutos para uma string CSV.A função save_sensor_log insere os registros na tabela sensors_log com status is_valid (True ou False), número de passos detectados, distância total e a mensagem descritiva do resultado.Exportação de CSV para Calibração:O endpoint GET /api/sensors_log/{log_id}/csv busca o conteúdo gravado em banco e devolve como arquivo text/csv para download e análise offline em scripts Python/Pandas.5. Decisões Técnicas e Histórico de Escolhas (Trade-offs)Instanciação Local do Estimador Madgwick:Problema: A reutilização de uma instância global de self.estimator no PDRProcessor fazia com que os estados dos quaternions e do giroscópio de uma requisição passada "sujassem" a orientação da caminhada seguinte.Solução: Instanciar um objeto limpo estimator = MadgwickAttitudeEstimator(gain=0.033) localmente dentro de process_samples() para cada lote recebido.Correção de Erro de Alinhamento (IndexError em Reamostragem):Problema: O Madgwick estava rodando no vetor bruto samples (ex: 218 pontos), mas a projeção da aceleração vertical tentava acessar o vetor reamostrado ax[i] (ex: 217 pontos), estourando o índice no final do loop.Solução: A fusão de Madgwick passou a ser executada após a reamostragem, iterando diretamente sobre os arrays pareados de $50\text{ Hz}$ (ax, ay, az, gx, gy, gz).Otimização de Execução Única (Single-Pass Execution):Problema: O algoritmo de Madgwick estava sendo executado duas vezes por chamada no backend (uma no início para a aceleração vertical e outra no final para extrair o Yaw).Solução: O cálculo foi consolidado no início da função, reutilizando a lista quaternions no Passo 7 para obter o azimute médio (mean_yaw_rad), reduzindo o tempo de processamento pela metade.Migração da Magnitude Total para Aceleração Vertical Isolada:Problema: Utilizar a magnitude total da aceleração ($\sqrt{x^2+y^2+z^2}$) tornava o sistema extremamente sensível a rotações bruscas do celular na mão.Solução: Mudança para a projeção da aceleração vertical real via Quaternions. Isso exigiu a re-calibração dos limiares do detector de picos (dynamic_height ajustado de $10.3$ para $9.95\text{ m/s}^2$ e $\Delta a$ mínimo reduzido de $1.2$ para $0.55\text{ m/s}^2$).Ajuste Fino na Trava Global de Giroscópio:Problema: Chacoalhos manuais ritmados conseguiam burlar a verificação quando o limiar de giroscópio médio estava em $4.0\text{ rad/s}$.Solução: Redução da exigência para mean_gyro > 2.2 rad/s ou max_gyro > 5.5 rad/s.6. Padrões de Código e ConvençõesEstilo de Código: PEP 8 com uso explícito de Type Hints em todas as funções e métodos (List, Dict, Tuple, Optional).Tratamento de Exceções: Retornos estruturados HTTP via HTTPException do FastAPI em caso de erros de payload (status 400) ou ausência de registros (status 404).Nomenclatura de Banco de Dados: Nomes de colunas e tabelas em snake_case em inglês/português (sensors_log, is_valid, steps_detected, distance_m, raw_csv).Estratégia de Branches e Git Flow:dev: Branch ativa de desenvolvimento. Commits e Pull Requests são validados via GitHub Actions (verificação de sintaxe Python).main: Branch de produção. Merges executados na main disparam o pipeline automatizado de deploy.7. Próximos Passos e PendênciasCalibração Dinâmica da Constante de Weinberg ($k$):O valor atual é fixo em $k = 0.45$. Implementar ajuste dinâmico do parâmetro $k$ com base na altura declarada pelo usuário ou histórico de calibração.Integração com o Módulo de Casamento no Mapa (topological_matcher.py):Finalizar a lógica para forçar que trajetos calculados com pequenos erros de ângulo (yaw drift) sejam suavizados e alinhados automaticamente com o vetor do corredor no grafo topológico.Visualização em Tempo Real no Frontend (mapa-2d.html):Conectar a renderização do frontend via Canvas/SVG aos retornos dos endpoints do servidor para desenhar a rota do usuário passo a passo no mapa topológico.Ferramenta/Script de Análise Gráfica Offline:Criar um script em Jupyter Notebook ou script Python auxiliar que consome o endpoint GET /api/sensors_log/{log_id}/csv e gera gráficos comparativos de forma automatizada (Sinal Bruto vs Sinal Filtrado Butterworth vs Picos Marcados).