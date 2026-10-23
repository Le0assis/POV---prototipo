# AGENTS.md

Notas para quem altera o POV. O README continua sendo o passo a passo de instalação.

## Backend

- A senha do editor é uma só, em `EDITOR_PASSWORD_HASH` (argon2id). Gere com `Backend/scripts/hash_password.py`. Não commite senha nem hash.

## Frontend

- A interface mora em `frontend/`. Leaflet fica no mapa (`L.CRS.Simple` e a planta em `imageOverlay`).
- Não chamar `reload()` do editor depois de um salvamento pontual: atualizar só o item devolvido pela API.
- Não pintar `devicemotion`, `deviceorientation` ou o marcador do visitante fora de um quadro (`requestAnimationFrame`).
- `/api/localize`, `/api/current_location` e `/api/reset` não entram no aplicativo de produção. Ficam em teste, atrás de flag desligada no build.
- A URL da API sai de uma config só. Em produção o padrão é `https://api.pov-unimar.com`.

## Fases

O plano de refatoração está no canvas aprovado. Cada fase do frontend é um commit em `feat/pov-refatoracao`. O diagnóstico das travadas está em `docs/frontend/fase-0-travadas.md`.
