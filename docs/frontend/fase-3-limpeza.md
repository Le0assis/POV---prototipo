# Fase 3 — limpeza do frontend

Saiu o que não tinha página viva: `dashboard.js`, `home.js`, `dashboard.css`, `routes.html`, `routes.js`, o simulador, a sessão de navegação salva, a bússola, `compass.css`, `routes.css`, `editor.html` e `recorder.html` da raiz (o admin continua em `admin/`).

`js/ui/toast.js` era só reexportação. `js/config.js` entrou em `js/core/config.js`. `css/home.css` ficou, porque o menu do admin ainda usa.

Comentários longos de mapeamento de sensor e do cliente HTTP foram reduzidos a uma linha. A tabela `saved_routes` não é removida aqui: isso é migração de banco, com backup e aprovação.
