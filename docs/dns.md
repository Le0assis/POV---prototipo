# DNS de pov-unimar.com

O site e a API não dividem o mesmo destino. `pov-unimar.com` e `www` vão para o GitHub Pages. `api.pov-unimar.com` vai para o túnel no computador que roda o FastAPI (`cloudflared-config.yml` só tem esse hostname, em `127.0.0.1:8000`).

| Tipo | Nome | Valor | Proxy Cloudflare |
| --- | --- | --- | --- |
| A | pov-unimar.com | 185.199.108.153 | Desligado (só DNS) |
| A | pov-unimar.com | 185.199.109.153 | Desligado (só DNS) |
| A | pov-unimar.com | 185.199.110.153 | Desligado (só DNS) |
| A | pov-unimar.com | 185.199.111.153 | Desligado (só DNS) |
| AAAA | pov-unimar.com | 2606:50c0:8000::153 | Desligado (só DNS) |
| AAAA | pov-unimar.com | 2606:50c0:8001::153 | Desligado (só DNS) |
| AAAA | pov-unimar.com | 2606:50c0:8002::153 | Desligado (só DNS) |
| AAAA | pov-unimar.com | 2606:50c0:8003::153 | Desligado (só DNS) |
| CNAME | www | le0assis.github.io | Desligado (só DNS) |
| CNAME | api | 5fcab4d8-67b9-495e-b2d9-548f69246fc6.cfargotunnel.com | Ligado |

O CNAME do Pages continua `pov-unimar.com`, com Enforce HTTPS. Com o proxy desligado, o certificado do site é o do GitHub. O registro do `api` também pode ser criado com `cloudflared tunnel route dns`.

CORS em produção aceita só `https://pov-unimar.com` e `https://www.pov-unimar.com`. Não há cookie de sessão (`allow_credentials` fica desligado; a senha do editor vai em `X-Editor-Password`).
