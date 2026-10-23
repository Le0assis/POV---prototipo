# AGENTS.md

Notas para quem altera o POV. O README continua sendo o passo a passo de instalação.

## Backend

- A senha do editor é uma só, em `EDITOR_PASSWORD_HASH` (argon2id). Gere com `Backend/scripts/hash_password.py`. Não commite senha nem hash. O limite de tentativas é atômico. `TRUSTED_PROXIES` é a lista explícita de pares que podem informar o cliente; `*` não vale. O uvicorn usa `--forwarded-allow-ips` com endereços concretos, nunca `*`.
- `GET /api/health` responde `{"status":"ok"}` e não abre MySQL.
- `/api/localize`, `/api/current_location` e `/api/reset` só existem com `POV_ENABLE_TEST_ROUTES` (padrão desligado). O nó `Recepcao` é fallback dessas rotas de teste.
- Em `POV_ENV=production` o CORS aceita só `https://pov-unimar.com` e `https://www.pov-unimar.com`. Sem a variável, o padrão é desenvolvimento e o localhost continua. `CORS_ORIGINS` substitui a lista. Sem `allow_credentials`.
- O túnel publica só `api.pov-unimar.com` em `127.0.0.1:8000`. O site é o GitHub Pages (ver `docs/dns.md`).
- MySQL continua o do XAMPP. Host, porta, base, usuário e senha saem de `DB_*`, com padrão `localhost` / `3306` / `POV` / `root` / vazio.

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
