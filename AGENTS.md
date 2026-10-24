# AGENTS.md

Notas para quem altera o POV. O README continua sendo o passo a passo de instalação.

## Backend

- A senha do editor é uma só, em `EDITOR_PASSWORD_HASH` (argon2id). Gere com `Backend/scripts/hash_password.py`. Não commite senha nem hash. O limite reserva a tentativa antes do argon2 (em curso + falhas). Senha certa ou 503 devolve a reserva; senha errada fica contada. Sem vaga de argon2 a resposta é 503 com `Retry-After`. O cache de 60s só aceita a mesma senha. `TRUSTED_PROXIES` é a lista explícita de pares que podem informar o cliente; `*` não vale. No `X-Forwarded-For` o cliente é o endereço mais à direita fora dessa lista. Suba o uvicorn com `--no-proxy-headers` (o padrão reescreve o par do socket a partir do header).
- `GET /api/health` responde `{"status":"ok"}` e não abre MySQL.
- `/api/localize`, `/api/current_location` e `/api/reset` só existem com `POV_ENABLE_TEST_ROUTES` (padrão desligado). O nó `Recepcao` é fallback dessas rotas de teste. O estado do matcher é por `X-Pov-Session`, não global.
- Em `POV_ENV=production` o CORS aceita só `https://pov-unimar.com` e `https://www.pov-unimar.com`. Sem a variável, o padrão é desenvolvimento e o localhost continua. `CORS_ORIGINS` substitui a lista. Sem `allow_credentials`.
- O túnel publica só `api.pov-unimar.com` em `127.0.0.1:8000`. O site é o GitHub Pages (ver `docs/dns.md`).
- MySQL continua o do XAMPP. Host, porta, base, usuário e senha saem de `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER` e `DB_PASSWORD`, com padrão `localhost` / `3306` / `POV` / `pov` / vazio. A API não lê `DB_ADMIN_*`.

## Frontend

- A interface mora em `frontend/src` e o build sai de Vite (`npm run build` → `frontend/dist`). Leaflet fica no mapa (`L.CRS.Simple` e a planta em `imageOverlay`), montado por `MapController`, fora da árvore Preact.
- O estado do visitante que o Preact observa é o signal `visitorSession`. Não renderizar de novo os contêineres que `app.ts` preenche (`#visitor-flow`, a folha de busca, o mapa).
- Cor de traço e marcador sai de `tokenColor`. Modo escuro é a classe `dark` em `html`; alto contraste é `hc` e prevalece se os dois estiverem ligados.
- Não chamar `reload()` do editor depois de um salvamento pontual: atualizar só o item devolvido pela API.
- Não pintar `devicemotion`, `deviceorientation` ou o marcador do visitante fora de um quadro (`requestAnimationFrame`).
- `/api/localize`, `/api/current_location` e `/api/reset` não entram no aplicativo de produção. Ficam em teste, atrás de flag desligada no build.
- A URL da API sai de uma config só. Em produção o padrão é `https://api.pov-unimar.com`.
- O Pages publica `frontend/dist` pelo workflow `pages.yml`, só na `main`. Não voltar a copiar a pasta `frontend` crua para `gh-pages`.

## Fases

O plano de refatoração está no canvas aprovado. Cada fase do frontend é um commit em `feat/pov-refatoracao`. O diagnóstico das travadas está em `docs/frontend/fase-0-travadas.md`.
