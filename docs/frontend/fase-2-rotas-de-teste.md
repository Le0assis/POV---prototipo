# Fase 2 — frontend

- `ping()` usa `GET /api/health`. Não consulta localização nem o banco.
- `/api/localize`, `/api/current_location` e `/api/reset` saíram das páginas. O corpo de teste ficou em `frontend/tests/fixtures/server-location.js`, com `TEST_ROUTES_ENABLED = false`.
- O editor não tem mais o formulário de reiniciar sessão. O gravador não chama reset ao começar.
- O override `pov_api_url` no localStorage saiu. A URL ainda escolhe `http://127.0.0.1:8000` em localhost e `https://api.pov-unimar.com` nos outros hosts. A leitura de `VITE_API_BASE_URL` entra com o Vite, na fase 4.

O backend precisa expor `GET /api/health` sem abrir conexão com o MySQL. As três rotas de teste só sobem com a flag do servidor.
