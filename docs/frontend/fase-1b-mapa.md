# Fase 1b — mapa 2D, desempenho

- `L.map` usa `preferCanvas` e um `L.canvas({ padding: 0.5 })` compartilhado.
- Checkpoints viram `circleMarker`. O tooltip permanente saiu; o nome aparece no hover. O popup da conexão só é montado no clique.
- As camadas ficam indexadas. Um salvamento move ou acrescenta o item, sem apagar o resto.
- Trajetos passam por Douglas-Peucker (`simplify.js`), com tolerância de 0,25 m em pixels (`px_per_m`).
- `setPlan` não recarrega a mesma URL e não chama `fitBounds`. O enquadramento continua na primeira carga.
- O marcador do visitante interpola posição e seta uma vez por quadro e só dá `panTo` quando sai da margem central.
- `deviceorientation` e o passo agendam um quadro. A rota só é recriada quando a assinatura muda; o progresso troca o trecho andado.
- `?perf=1` mostra FPS e tempo de render. Sem o parâmetro o contador não roda. O número no Poco continua no checklist de campo.
