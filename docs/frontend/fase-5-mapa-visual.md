# Fase 5 — mapa 2D, parte visual

Os nomes dos checkpoints aparecem como rótulo permanente só a partir do zoom 1. Abaixo disso ficam no hover. Origem e destino continuam visíveis em qualquer zoom. Se dois rótulos comuns se cruzam, fica o primeiro; origem e destino não são escondidos por sobreposição.

A caixa "Camadas" liga planta, trajetos gravados, conexões manuais, rótulos e rota. O estado vai para `localStorage` na chave `pov.map.layers`. Gravado continua linha cheia e manual tracejado. A espessura sobe com o zoom (no zoom 0, 4 e 3, como antes). O destino usa o token `--path-destination`, maior que os outros pontos.

O painel de acessibilidade ganhou "Modo escuro" (`html.dark`), gravado em `pov.a11y`. O script do `<head>` aplica a classe antes da folha de estilo. Alto contraste (`html.hc`) continua e, se os dois estiverem ligados, o contraste prevalece. O canvas relê a cor do token quando a classe do documento muda.

A revisão visual no Poco 6 Pro continua com o Léo. O zoom mínimo dos rótulos é 1.
