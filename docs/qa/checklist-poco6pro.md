# Checklist de campo — Chrome no Poco 6 Pro

Roteiro manual da Missão 03 (T9) para a Agatinha conferir o POV no aparelho de campo.

| Campo | Valor |
|---|---|
| Aparelho | Xiaomi Poco 6 Pro |
| Navegador | Chrome estável, atualizado, em português (Brasil) |
| Site | https://pov-unimar.com/ |
| API | https://api.pov-unimar.com |
| Página do visitante | https://pov-unimar.com/ ou https://pov-unimar.com/index.html |
| Executor | Agatinha |

A câmera, o Wake Lock e a leitura em voz alta exigem HTTPS. Use o endereço acima, não um espelho em HTTP.

## Como marcar

Cada item tem passos, resultado esperado e caixas. Marque uma só.

- **Aprovado** — o resultado esperado apareceu.
- **Reprovado** — divergiu. Preencha a observação e abra um relato (seção final).
- **Não executado** — a pré-condição não existia no campo (por exemplo, a API respondeu 200 e o caso 503 não pôde ser provocado). Escreva o motivo. Isso não reprova o app.

Antes de começar, anote na observação de cada falha a hora local, a URL completa (com o hash) e a versão do Chrome (`Configurações → Sobre o Chrome`).

Pré-condição geral: existe ao menos um checkpoint publicado no prédio, com slug e QR v1, e outro checkpoint alcançável a partir dele. A senha de homologação do editor fica com o time; este roteiro não a repete.

---

## E0 — Inicial

### E0-01 — Mapa inicial do visitante

**Passos**

1. Feche outras abas do POV.
2. No Chrome, abra https://pov-unimar.com/ .
3. Espere o mapa aparecer.
4. Olhe o atributo de estado no shell da página (depuração remota, se estiver ligada): `#visitor-shell` com `data-state="E0"`.

**Resultado esperado**

- A página abre em HTTPS, sem pedido de instalação obrigatório.
- O convite diz **Leia um QR para saber onde você está**.
- Há o botão **Ler QR** (rótulo acessível `Ler QR`) e o botão **Acessibilidade**.
- O campo de baixo diz **Para onde você quer ir?** e ainda não abre o teclado sozinho.
- O seletor **Visitante | Admin** aparece com **Visitante** marcado, e o selo **HOMOLOGAÇÃO** está visível.
- O mapa do prédio ocupa a tela. Se a planta já estiver publicada, ela aparece. Se o servidor não tiver planta, o status diz **A planta aparece quando o mapa estiver disponível.**

**Resultado**

- [ ] Aprovado
- [ ] Reprovado
- [ ] Não executado

**Observação:**

---

## E1 — Câmera

### E1-01 — Permissão da câmera concedida

**Passos**

1. A partir do E0, toque em **Ler QR** (ou no convite **Leia um QR para saber onde você está**).
2. Quando o Chrome pedir acesso à câmera, toque em **Permitir**.
3. Aponte para um ambiente iluminado, sem QR ainda.

**Resultado esperado**

- A câmera traseira abre em tela cheia, com o título **Aponte para o QR code do ponto**.
- O estado passa a E1 (`data-state="E1"`).
- Aparecem **Lanterna** (ligada só se o aparelho expuser o flash), **Digitar código** e **Fechar**.
- **Fechar**, o botão voltar do Android ou a tecla Escape de um teclado externo devolve ao E0 e a imagem da câmera para.

**Resultado**

- [ ] Aprovado
- [ ] Reprovado
- [ ] Não executado

**Observação:**

### E1-02 — Permissão da câmera negada

**Passos**

1. Nas configurações do Android, bloqueie a câmera para o Chrome (ou negue de novo o pedido, se o Chrome perguntar).
2. Volte ao POV e toque em **Ler QR**.
3. Toque em **Digitar código**, escreva o slug de um ponto real e confirme em **Usar este código**.
4. No fim, devolva a permissão da câmera ao Chrome para os itens seguintes.

**Resultado esperado**

- A câmera não abre.
- A mensagem é **A permissão da câmera foi negada. Libere o acesso nas configurações do navegador ou digite o código do ponto.**
- Há **Voltar** e **Tentar de novo**.
- O código digitado de um ponto real define a origem, como se o QR tivesse sido lido: a barra mostra **Origem:** com o nome do ponto e o sufixo `(QR)`.

**Resultado**

- [ ] Aprovado
- [ ] Reprovado
- [ ] Não executado

**Observação:**

### E1-03 — Leitura com BarcodeDetector

**Passos**

1. Com a câmera permitida, conecte a depuração remota (`chrome://inspect` em um computador) ou use o console remoto do Chrome.
2. Na página do POV, avalie se `window.BarcodeDetector` existe. Se existir, chame `BarcodeDetector.getSupportedFormats()` e veja se a lista inclui `qr_code`.
3. Abra **Ler QR** e aponte para um QR v1 impresso.
4. No painel de rede, observe os pedidos feitos durante a leitura.

**Resultado esperado**

- No Chrome atual do Poco 6 Pro o `BarcodeDetector` existe e aceita `qr_code`. Nesse caso o POV usa esse leitor nativo.
- O QR é reconhecido sem baixar script de CDN.
- Enquanto o `BarcodeDetector` funciona, a leitura **não** pede `frontend/vendor/qr-scanner/qr-scanner-worker.min.js`.
- O ponto lido vira a origem (veja E1-05).

Se o console mostrar que `BarcodeDetector` não existe ou não lista `qr_code`, marque **Não executado** e siga para E1-04: o fallback é o caminho certo nesse Chrome.

**Resultado**

- [ ] Aprovado
- [ ] Reprovado
- [ ] Não executado

**Observação:**

### E1-04 — Fallback qr-scanner

**Passos**

1. Este item vale quando o E1-03 não teve `BarcodeDetector` com `qr_code`, ou quando o detector nativo falha ao ser criado.
2. Abra **Ler QR** e aponte para o mesmo QR v1.
3. No painel de rede, confira a origem dos scripts do leitor.

**Resultado esperado**

- A câmera continua na tela e o QR ainda é lido.
- O leitor reserva é o `qr-scanner` local, servido pelo próprio site (`vendor/qr-scanner/qr-scanner.min.js` e o worker `qr-scanner-worker.min.js`). Nenhum script de QR vem de CDN.
- A origem fica definida do mesmo jeito que com o `BarcodeDetector`.

**Resultado**

- [ ] Aprovado
- [ ] Reprovado
- [ ] Não executado

**Observação:**

### E1-05 — QR v1 válido

**Passos**

1. Use um QR impresso em **Gerar QR codes**, ou abra no Chrome a URL do ponto, trocando os dois valores reais do prédio:

   `https://pov-unimar.com/#/scan?cp=<slug>&b=<building_id>&v=1`

   O `cp` é o slug do checkpoint. O `b` é o id numérico do prédio. O `v` é `1`. A query fica **dentro do hash**, depois de `#/scan?`.
2. Se abrir pela câmera, aponte até a leitura. Se abrir pela URL, a página trata o hash sozinha.

**Resultado esperado**

- O app reconhece o formato v1 e consulta o checkpoint.
- A origem passa a ser esse ponto: **Origem:** mostra o nome e `(QR)`.
- A faixa anuncia **Você está em** seguido do nome do ponto.
- A câmera fecha depois da leitura. O mapa permanece no visitante.

**Resultado**

- [ ] Aprovado
- [ ] Reprovado
- [ ] Não executado

**Observação:**

### E1-06 — QR inválido

**Passos**

1. Abra **Ler QR**.
2. Aponte para um QR que não seja de ponto (um QR de rede Wi-Fi, um texto qualquer ou uma URL sem `cp` nem `origem`).
3. Se não houver um QR assim impresso, toque em **Digitar código**, escreva `https://exemplo.com/nao-e-ponto` e confirme em **Usar este código**.
4. Repita com a versão errada, abrindo:

   `https://pov-unimar.com/#/scan?cp=<slug>&b=<building_id>&v=2`

   Use um slug que exista. Só a versão muda.

**Resultado esperado**

- QR que não é de ponto: a câmera (ou a faixa no topo, se a URL foi aberta direto) diz **Este QR não é de um ponto.** A origem não muda.
- Versão diferente de 1: a mensagem é **Versão do QR não suportada.** A origem não muda.
- Dá para fechar a câmera e voltar ao mapa.

**Resultado**

- [ ] Aprovado
- [ ] Reprovado
- [ ] Não executado

**Observação:**

### E1-07 — QR desconhecido

**Passos**

1. Com a rede ligada, abra:

   `https://pov-unimar.com/#/scan?cp=ponto-que-nao-existe&b=1&v=1`

2. Ou leia / digite um slug que não esteja cadastrado no prédio.

**Resultado esperado**

- A mensagem é **QR não reconhecido neste prédio**.
- Nenhum ponto falso vira origem.
- O visitante continua no mapa e pode tentar outro código.

**Resultado**

- [ ] Aprovado
- [ ] Reprovado
- [ ] Não executado

**Observação:**

---

## E2 — Busca

### E2-01 — Folha inferior

**Passos**

1. No E0, ou já com a origem definida, toque o campo **Para onde você quer ir?**.
2. Observe a folha que sobe e o teclado.
3. Feche pela alça (**Arrastar para fechar a busca**), pelo botão **Fechar**, pelo fundo escuro ou pelo voltar do Android.

**Resultado esperado**

- Abre uma folha de baixo para cima, título **Para onde você quer ir?**, com o campo já focado e o teclado do Chrome visível.
- O estado fica E2 enquanto a folha está aberta.
- A lista mostra destinos do prédio, com nome e categoria. O contador diz `N destinos` (ou **1 destino**).
- Há o filtro **Todos** e um chip por categoria publicada.
- Fechar devolve ao estado anterior (E0 sem destino, ou a prévia se a origem e o destino já existiam) e o foco volta ao campo de baixo.

**Resultado**

- [ ] Aprovado
- [ ] Reprovado
- [ ] Não executado

**Observação:**

### E2-02 — Filtro

**Passos**

1. Abra a folha de novo.
2. Digite um pedaço do nome de um destino que você vê na lista.
3. Apague o texto e toque um chip de categoria. Volte em **Todos**.
4. Digite uma sequência que não existe, por exemplo `zzzz-sem-destino`.

**Resultado esperado**

- O texto reduz a lista a destinos cujo nome ou categoria contém o que foi digitado. O contador acompanha a quantidade.
- O chip de categoria mostra só os itens daquela categoria. **Todos** restaura a lista inteira.
- Sem resultado, a folha diz **Nenhum destino encontrado** e oferece **Limpar busca**. **Limpar busca** zera o texto e os chips.
- Toque um destino real: a folha fecha e o nome aparece em **Destino**.

**Resultado**

- [ ] Aprovado
- [ ] Reprovado
- [ ] Não executado

**Observação:**

---

## E3 — Prévia

### E3-01 — Rota (menor caminho)

**Passos**

1. Defina a origem com um QR v1 de um ponto real (E1-05).
2. Abra a busca e escolha um destino diferente, ligado a esse ponto no mapa.
3. Olhe o traço no mapa, a distância e a lista **Passos da rota**.
4. Não inicie a caminhada ainda.

**Resultado esperado**

- O estado fica E3 (`data-state="E3"`).
- O app calcula no próprio celular o menor caminho entre os checkpoints (Dijkstra no grafo do prédio) e desenha a polilinha no mapa, da origem ao destino, seguindo os trechos cadastrados.
- A barra mostra distância e tempo no formato `~N m · ~M min`.
- **Passos da rota** lista cada trecho como **Siga até {nome} (~N m)**.
- **Iniciar rota** fica habilitado.
- **Voltar** desfaz a prévia e volta ao mapa inicial, sem começar a andar.

**Resultado**

- [ ] Aprovado
- [ ] Reprovado
- [ ] Não executado

**Observação:**

### E3-02 — Sem caminho entre os pontos

**Passos**

1. Se no prédio houver dois checkpoints sem ligação (pontos isolados), escolha essa origem e esse destino.
2. Se todos os pontos publicados se alcançam, marque **Não executado** e anote isso.

**Resultado esperado**

- A mensagem é **Não encontramos um caminho entre esses pontos**.
- O botão principal é **Trocar destino**, que reabre a busca.
- **Iniciar rota** não fica disponível para esse par.

**Resultado**

- [ ] Aprovado
- [ ] Reprovado
- [ ] Não executado

**Observação:**

---

## E4 — Navegando

Faça esta seção andando alguns metros no prédio, com a tela desbloqueada e o Chrome em primeiro plano. No Android, deixe o tempo de bloqueio da tela em 15 segundos (Configurações do sistema) para o teste do Wake Lock.

### E4-01 — Passos e heading

**Passos**

1. Na prévia de uma rota curta e conhecida, toque em **Iniciar rota**.
2. Se o Chrome pedir movimento ou orientação, permita.
3. Caminhe na direção do corredor e, no meio do trecho, gire o corpo devagar.
4. Observe a faixa de instrução e o ponto azul no mapa.

**Resultado esperado**

- O estado fica E4. Aparecem **Cheguei** e **Encerrar**.
- A faixa descreve o próximo movimento, em metros:
  - reta, ou curva de até 30°: **Siga em frente por N m**;
  - curva maior: **Siga N m e vire à esquerda em {lugar}** ou **Siga N m e vire à direita em {lugar}**.
- Cada passo reconhecido avança o ponto azul ao longo da polilinha, não em linha reta fora do traço.
- Girar o aparelho atualiza o heading usado para acompanhar a rota. A frase da faixa só muda quando a instrução muda; não repete a cada passo.
- Se o movimento ou a orientação forem negados, a navegação continua e a faixa avisa **Sem sensores: siga a rota no mapa e leia os QR codes pelo caminho**.

**Resultado**

- [ ] Aprovado
- [ ] Reprovado
- [ ] Não executado

**Observação:**

### E4-02 — Wake Lock

**Passos**

1. Com o bloqueio automático da tela em 15 segundos, inicie a rota e permaneça no E4, sem tocar na tela.
2. Espere pelo menos 20 segundos.
3. Toque em **Encerrar** e espere de novo, sem tocar na tela.

**Resultado esperado**

- Durante o E4 o Chrome pede o Wake Lock de tela. A tela permanece acesa além do tempo de bloqueio do Android.
- **Encerrar** (ou chegar ao destino) solta o lock: a tela volta a poder apagar no tempo do sistema.
- Se este Chrome não oferecer Wake Lock, a caminhada segue mesmo assim. Anote isso na observação; a ausência da API, com a rota ainda utilizável, não é falha da instrução.

**Resultado**

- [ ] Aprovado
- [ ] Reprovado
- [ ] Não executado

**Observação:**

### E4-03 — speechSynthesis

**Passos**

1. Antes de iniciar, abra **Acessibilidade** e ligue **Ler instruções em voz alta**. Feche o painel.
2. Inicie a rota (ou continue uma já iniciada) e caminhe até a frase da faixa mudar (uma curva, ou a chegada).
3. Desligue **Ler instruções em voz alta** e provoque outra mudança de instrução.

**Resultado esperado**

- Com o interruptor ligado, o Chrome fala em português (pt-BR) o texto novo da faixa. A mesma frase não é repetida a cada passo.
- Com o interruptor desligado, a faixa continua visível e a voz para.
- No Chrome do Poco 6 Pro a opção aparece habilitada. Se `speechSynthesis` não existir, o interruptor fica desabilitado e o painel diz **Este aparelho não lê em voz alta.** Nesse caso marque **Não executado** e copie a frase.

**Resultado**

- [ ] Aprovado
- [ ] Reprovado
- [ ] Não executado

**Observação:**

---

## E5 — Chegada

### E5-01 — Cartão de chegada

**Passos**

1. Siga a rota até o destino, ou, se o trecho for longo demais para o campo, toque em **Cheguei** no E4.
2. Leia o cartão.
3. Toque em **Novo destino**. Escolha outro ponto e volte à prévia. Desfaça ou conclua.
4. Repita a chegada e toque em **Fim**.

**Resultado esperado**

- O estado fica E5.
- O cartão diz **Você chegou a {nome do destino}**.
- **Novo destino** abre a busca (E2) para escolher outro ponto, mantendo a possibilidade de nova prévia.
- **Fim** encerra a navegação e volta ao E0, com o convite para ler um QR.

**Resultado**

- [ ] Aprovado
- [ ] Reprovado
- [ ] Não executado

**Observação:**

---

## Erros

### ERR-01 — Offline

**Passos**

1. Com https://pov-unimar.com/ já aberto e a planta visível, ative o modo avião.
2. Toque **Para onde você quer ir?**.
3. Feche a folha, abra **Ler QR** e leia (ou digite) um QR v1 de ponto real. A câmera do aparelho funciona sem rede; a consulta ao servidor, não.
4. Desative o modo avião no fim.

**Resultado esperado**

- A busca diz **Não foi possível carregar os destinos.** e mostra **Tentar de novo**.
- A leitura do QR não define a origem. A câmera (ou a faixa, se a URL foi aberta direto) mostra **Tentar de novo**.
- Recarregar sem rede: se a casca estiver em cache, o mapa avisa **A planta aparece quando o mapa estiver disponível.** Se o Chrome mostrar a página offline do próprio navegador, anote isso; o HTML não chegou a abrir.
- Na administração, com a página já carregada, o ponto de status anuncia **Backend offline**.

**Resultado**

- [ ] Aprovado
- [ ] Reprovado
- [ ] Não executado

**Observação:**

### ERR-02 — API 503

**Passos**

1. Com a rede ligada, abra numa aba https://api.pov-unimar.com/api/map e leia o status HTTP.
2. Abra também https://api.pov-unimar.com/api/auth/check sem enviar senha.
3. Se `/api/map` responder **503**, volte a https://pov-unimar.com/ , recarregue e abra a busca.
4. Se `/api/auth/check` responder **503**, no visitante toque **Admin**, digite qualquer senha e confirme **Entrar**.
5. Se as duas respostas forem outras (200 no mapa, 401 na checagem de senha), o 503 não está ativo neste servidor. Marque **Não executado** e registre os dois status. Não reprove o app por isso.

**Resultado esperado**

- Mapa em 503: o visitante não recebe os checkpoints. Sem planta utilizável, o status diz **A planta aparece quando o mapa estiver disponível.** A busca entra no mesmo aviso de falha do item offline (**Não foi possível carregar os destinos.**), mesmo com o site https://pov-unimar.com/ abrindo.
- Auth em 503: o modo não muda para Admin. O aviso é **A senha do editor não está configurada no servidor.** O selo **HOMOLOGAÇÃO** continua na tela. O detalhe do servidor cita `EDITOR_PASSWORD`.
- 503 não é o mesmo que offline: o site abre, e a aba da API mostra o status 503.

**Resultado**

- [ ] Aprovado
- [ ] Reprovado
- [ ] Não executado

**Observação:**

---

## Visitante / Admin e o selo HOMOLOGAÇÃO

O seletor é o grupo **Modo de acesso**, com **Visitante** e **Admin**. O selo ao lado é o texto exato **HOMOLOGAÇÃO**, no visitante e na administração.

A entrada em Admin chama `GET /api/auth/check` com o header `X-Editor-Password`. Confira o status na depuração remota quando ela estiver ligada. O resultado visível abaixo é o que vale para a caixa.

### ROLE-01 — Selo e troca de volta

**Passos**

1. No visitante, confirme o selo e que **Visitante** está marcado.
2. Entre em Admin com a senha certa (ROLE-02) e olhe o selo de novo.
3. Toque **Visitante**.

**Resultado esperado**

- O selo **HOMOLOGAÇÃO** aparece nos dois modos, junto do seletor.
- **Visitante** volta para https://pov-unimar.com/index.html sem pedir senha.
- O hash da rota, se havia origem ou destino, é preservado na troca.

**Resultado**

- [ ] Aprovado
- [ ] Reprovado
- [ ] Não executado

**Observação:**

### ROLE-02 — Senha correta (204)

**Passos**

1. Na aba do visitante, sem senha guardada nesta aba (feche a aba e abra de novo se já tiver entrado antes).
2. Toque **Admin**.
3. No diálogo **Senha do editor**, digite a senha de homologação e toque **Entrar**.
4. Se a depuração estiver ativa, leia o status de `GET /api/auth/check`.

**Resultado esperado**

- O servidor responde **204** e o app entra em https://pov-unimar.com/admin/index.html .
- O título é **Administração**. **Admin** fica marcado e o selo **HOMOLOGAÇÃO** continua.
- O menu mostra **Editar mapa e pontos**, **Gravar trajeto**, **Configurar planta** e **Gerar QR codes**.
- Na mesma aba, abrir de novo uma página `/admin/` não pede a senha outra vez.

**Resultado**

- [ ] Aprovado
- [ ] Reprovado
- [ ] Não executado

**Observação:**

### ROLE-03 — Senha errada (401)

**Passos**

1. Feche a aba para esquecer a senha e abra de novo o visitante.
2. Toque **Admin**, digite uma senha errada e confirme.
3. No segundo diálogo, digite outra senha errada e confirme.
4. Comece de novo, abra o diálogo e toque **Cancelar**.

**Resultado esperado**

- A primeira senha errada recebe **401**. O diálogo reabre com **Senha incorreta. Digite de novo.**
- A segunda senha errada também recebe **401**. O app permanece em **Visitante** e mostra o mesmo aviso. Não entra na administração.
- **Cancelar** fecha o diálogo e fica no visitante, sem aviso de erro.
- O selo **HOMOLOGAÇÃO** não some.

**Resultado**

- [ ] Aprovado
- [ ] Reprovado
- [ ] Não executado

**Observação:**

### ROLE-04 — Servidor sem senha (503)

**Passos**

1. Use o status já lido em ERR-02 para `GET /api/auth/check`.
2. Se for **503**, no visitante toque **Admin**, digite qualquer texto e confirme **Entrar**.
3. Se for **401** (senha configurada), marque **Não executado**. O caso 503 só vale num servidor sem `EDITOR_PASSWORD`.

**Resultado esperado**

- A resposta **503** não entra em Admin.
- O aviso é **A senha do editor não está configurada no servidor.**
- **Visitante** continua marcado e o selo **HOMOLOGAÇÃO** segue visível.

**Resultado**

- [ ] Aprovado
- [ ] Reprovado
- [ ] Não executado

**Observação:**

---

## Impressão dos QR em A4

Página: https://pov-unimar.com/admin/qrcodes.html (pela carta **Gerar QR codes** depois do ROLE-02).

Selecione pelo menos quatro checkpoints que tenham slug. O padrão de **Por página** é **2**. Cada cartão leva o nome, a categoria, a frase **Aponte a câmera do celular para saber onde você está**, o slug e um QR cujo texto é:

`https://pov-unimar.com/#/scan?cp=<slug>&b=<building_id>&v=1`

No Chrome, **Imprimir / Salvar PDF** abre a impressão do sistema. Salve como PDF. Se o diálogo oferecer tamanho de papel, escolha **A4** retrato. Conte páginas e cartões. A barra **Visitante | Admin**, o selo, o título **Gerar QR codes**, o filtro e os botões **PNG** / **SVG** não saem no PDF.

### QR-01 — 1 por página

**Passos**

1. Em **Por página**, marque **1**.
2. Deixe quatro ou mais checkpoints marcados.
3. Toque **Imprimir / Salvar PDF** e salve o PDF.

**Resultado esperado**

- Sai um cartão por página A4.
- Quatro checkpoints geram quatro páginas. A prévia na tela acompanha a escolha **1** antes de imprimir.

**Resultado**

- [ ] Aprovado
- [ ] Reprovado
- [ ] Não executado

**Observação:**

### QR-02 — 2 por página

**Passos**

1. Marque **2** em **Por página**.
2. Imprima ou salve o PDF dos mesmos quatro checkpoints.

**Resultado esperado**

- Dois cartões por página A4, um sobre o outro.
- Quatro checkpoints geram duas páginas. A quebra ocorre depois de cada par.

**Resultado**

- [ ] Aprovado
- [ ] Reprovado
- [ ] Não executado

**Observação:**

### QR-03 — 4 por página

**Passos**

1. Marque **4** em **Por página**.
2. Imprima ou salve o PDF dos mesmos quatro checkpoints.
3. Se houver cinco ou mais, imprima também esse conjunto e confira a segunda página.

**Resultado esperado**

- Quatro cartões por página A4, em duas colunas.
- Quatro checkpoints cabem numa página. O quinto começa a página seguinte.
- O QR continua legível e o texto do cartão não é cortado fora da folha.

**Resultado**

- [ ] Aprovado
- [ ] Reprovado
- [ ] Não executado

**Observação:**

---

## Painel de acessibilidade

O botão **Acessibilidade** fica no topo do visitante. O painel tem os interruptores **Alto contraste**, **Fonte grande** e **Ler instruções em voz alta**, e o botão **Fechar**. As duas primeiras opções ficam gravadas neste aparelho e voltam depois de recarregar. A leitura em voz alta durante a rota está no E4-03; aqui o foco é o painel.

### A11Y-01 — Alto contraste

**Passos**

1. No E0, toque **Acessibilidade**.
2. Ligue **Alto contraste**. Feche o painel tocando fora dele.
3. Recarregue https://pov-unimar.com/ .
4. Abra o painel de novo e desligue **Alto contraste**.

**Resultado esperado**

- O painel abre como diálogo com o título **Acessibilidade**. O fundo do mapa fica inerte enquanto ele está aberto.
- Com **Alto contraste** ligado, o tema muda na hora (bordas e texto mais fortes) e permanece depois do recarregamento.
- Desligar volta ao tema padrão, também depois de recarregar.
- **Fechar** ou Escape devolve o foco ao botão **Acessibilidade**.

**Resultado**

- [ ] Aprovado
- [ ] Reprovado
- [ ] Não executado

**Observação:**

### A11Y-02 — Texto grande

**Passos**

1. Abra **Acessibilidade** e ligue **Fonte grande**.
2. Feche o painel e olhe o convite do QR, o campo de busca e, se a prévia estiver aberta, os passos da rota.
3. Recarregue a página.
4. Desligue **Fonte grande**.

**Resultado esperado**

- O texto do visitante aumenta assim que o interruptor liga, sem sair da página.
- A preferência continua depois do recarregamento.
- Desligar restaura o tamanho anterior.
- **Alto contraste** e **Fonte grande** podem ficar ligados juntos, e cada um guarda o próprio estado.

**Resultado**

- [ ] Aprovado
- [ ] Reprovado
- [ ] Não executado

**Observação:**

### A11Y-03 — Instruções lidas em voz alta

**Passos**

1. Abra **Acessibilidade** e leia o interruptor **Ler instruções em voz alta**.
2. Ligue e desligue, fechando o painel entre as duas tentativas.
3. Confirme no E4-03 que a voz acompanha a faixa só enquanto o interruptor está ligado.

**Resultado esperado**

- No Chrome do Poco 6 Pro o interruptor pode ser ligado. Não aparece a frase **Este aparelho não lê em voz alta.**
- Ligado, as instruções novas da navegação são faladas (E4-03). Desligado, a voz não continua.
- A preferência permanece neste aparelho depois de fechar e abrir o painel.
- Se a API de voz não existir, o interruptor fica desabilitado e a frase **Este aparelho não lê em voz alta.** aparece. A navegação visual segue normal.

**Resultado**

- [ ] Aprovado
- [ ] Reprovado
- [ ] Não executado

**Observação:**

---

## Como reportar um bug

Quando um item ficar **Reprovado**, a Agatinha registra um relato com estes três dados, nesta ordem:

1. **Captura de tela** do Chrome no Poco 6 Pro, com a mensagem ou o mapa visível. Se a falha for só sonora, grave também o texto que a faixa mostrava.
2. **URL completa** da barra de endereço, incluindo o hash (`#/scan?...` ou `#origem=...&destino=...`).
3. **Hora** local do aparelho, com a data (dia, mês, ano e hora:minuto).

No mesmo relato, acrescente o id do item (por exemplo `E1-06`), a versão do Chrome, o que foi feito e o que apareceu no lugar do resultado esperado. Não apague a observação do item.
