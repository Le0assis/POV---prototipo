# Fase 4 — TypeScript, Vite e Preact

O código do visitante e do admin saiu de `frontend/js` para `frontend/src` (`.ts` / `.tsx`). Os imports internos continuam com sufixo `.js`; o Vite resolve para o fonte.

Preact entra em `frontend/src/main.tsx` e desenha só o `SessionBadge`, ligado ao signal `visitorSession`. O restante do DOM do visitante continua com `app.ts`, para o contrato de acessibilidade (estados E0–E5, busca, câmera, rota) não mudar. O Leaflet não entra nessa árvore: `MapController.mount` chama o mapa já existente.

`frontend/src/core/config.ts` lê `VITE_API_BASE_URL`. O arquivo `frontend/.env.production` define `https://api.pov-unimar.com`. Se a variável faltar num build de produção, o mesmo endereço é o padrão. Em desenvolvimento, `frontend/.env.development` aponta para `http://127.0.0.1:8000`.

`TEST_ROUTES_ENABLED` só é verdadeiro com `import.meta.env.DEV` e `VITE_ENABLE_TEST_ROUTES=1`. O build de produção deixa a flag falsa. O aplicativo não chama `/api/localize`, `/api/current_location` nem `/api/reset`.

Os testes rodam no Vitest (`npm test` faz o build e em seguida `vitest run`). O axe abre `frontend/dist`, porque o fonte TypeScript não executa no servidor estático. O mock cobre `http://127.0.0.1:8000` e `https://api.pov-unimar.com`.

O Leaflet continua num `<script>` clássico. O build copia `frontend/vendor/leaflet` para `frontend/dist/vendor/leaflet`, porque o Vite não empacota esse script.

Checagens: `npm run typecheck`, `npm run lint`, `npm test`, `npm run build`.
