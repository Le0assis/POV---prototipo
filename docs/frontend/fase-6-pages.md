# Fase 6 — GitHub Pages

O site publicado é o build do Vite (`frontend/dist`), não a pasta `frontend` crua. O workflow `.github/workflows/pages.yml` usa `actions/upload-pages-artifact` e `actions/deploy-pages`. Ele roda no push da `main` e em `workflow_dispatch`. A branch `feat/pov-refatoracao` não publica.

`vite.config.ts` usa `base: '/'`, o adequado a um domínio próprio. `frontend/public/CNAME` contém `pov-unimar.com` e entra no artefato. O build de produção lê `VITE_API_BASE_URL`; o workflow define `https://api.pov-unimar.com`, o mesmo padrão de `frontend/.env.production` e de `frontend/src/core/config.ts` quando a variável falta.

O job antigo que copiava `./frontend` para a branch `gh-pages` (peaceiris) saiu. Este repositório não teve alteração de Settings, DNS ou da configuração do Pages: isso fica com o dono.

## O que o dono faz na mão

1. No GitHub, em Settings → Pages → Build and deployment, a origem passa a ser **GitHub Actions** (não a branch `gh-pages`).
2. Custom domain: `pov-unimar.com`. Ligar **Enforce HTTPS** depois que o certificado aparecer. O proxy da Cloudflare desse nome fica desligado, para o certificado ser o do GitHub.
3. DNS, se ainda não estiver assim (detalhe em `docs/dns.md`):
   - A `pov-unimar.com` → `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153` (proxy desligado)
   - AAAA `pov-unimar.com` → `2606:50c0:8000::153`, `2606:50c0:8001::153`, `2606:50c0:8002::153`, `2606:50c0:8003::153` (proxy desligado)
   - CNAME `www` → `le0assis.github.io` (proxy desligado)
   - CNAME `api` → `5fcab4d8-67b9-495e-b2d9-548f69246fc6.cfargotunnel.com` (proxy ligado)
4. O primeiro deploy acontece no próximo push da `main`, ou com "Run workflow" em Actions → GitHub Pages, depois que a origem estiver em GitHub Actions.
