# Fase 1a — salvamento no frontend

- `loadFloorModel` dispara mapa, planta e conexões juntos. `includePath` continua verdadeiro na carga do mapa, porque o traço é a geometria desenhada.
- Criar checkpoint, gravar conexão e salvar posição atualizam `editor-model.js` com a resposta. Não há segundo `GET` nem recarga da planta.
- Arraste com erro devolve o nó à posição anterior e redesenha só nesse caso.
- O gravador guarda a amostra na hora e pinta contadores e o gráfico uma vez por quadro.
