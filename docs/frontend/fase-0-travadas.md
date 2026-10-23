# Fase 0 — causas das travadas (frontend)

Medição de parede no Poco 6 Pro não foi feita neste ambiente: não há o aparelho, nem o MySQL do XAMPP. Os números de FPS e de tempo de salvar ficam para o checklist em `docs/qa/checklist-poco6pro.md`. O que segue é a causa no código, conferida nos arquivos citados (main `33d226f`).

## Travada ao salvar

O salvamento em si espera a API. A tela trava depois, porque o editor reconstrói o mapa inteiro.

1. `frontend/js/pages/editor.js` chama `reload()` depois de criar checkpoint, gravar conexão, posicionar no clique e soltar o arraste. Se o arraste falha, chama `reload()` de novo.
2. `reload()` chama `loadFloorModel()`, que em `frontend/js/pages/floor-model.js` faz `GET /api/map`, `GET /api/map-config` e `GET /api/connections?include_path=true` **um depois do outro**. O terceiro pede o traço de cada aresta.
3. Em seguida `setPlan()` remove a planta, baixa a imagem de novo e chama `fitBounds`. O mapa pisca e perde o enquadramento.
4. `renderFloorLayers()` apaga e recria todas as polilinhas e todos os marcadores.

O gravador soma outra trava, durante a caminhada e não só no POST: `frontend/js/pages/recorder.js` trata cada `devicemotion` (cerca de 60 a 100 por segundo) com várias buscas no DOM, cinco textos e um redesenho do gráfico.

## Travada no mapa 2D

1. `createFloorMap` cria `L.map` sem `preferCanvas` e sem `L.canvas()`. Cada linha vira SVG. Pan e zoom no celular percorrem a árvore de nós.
2. Cada checkpoint é um `divIcon` com tooltip permanente: dois elementos HTML reposicionados em todo pan e zoom.
3. A polilinha usa todos os vértices do traço, sem simplificar.
4. O popup de cada linha é montado na criação, não no clique.
5. `map-view.js` `setWalker` chama `bringToFront` e `panTo` em toda atualização.
6. `app.js` `paintNavigation` roda direto no `deviceorientation` e no passo, sem `requestAnimationFrame`.
7. `route-layer.js` `show()` apaga e recria a rota sempre que `render()` do visitante roda, mesmo com a mesma geometria.

## O que esta fase não muda

Nenhum comportamento. As fases 1a e 1b atacam os itens acima no JavaScript atual. A troca para TypeScript, Vite e Preact é a fase 4 e não é pré-requisito do conserto.
