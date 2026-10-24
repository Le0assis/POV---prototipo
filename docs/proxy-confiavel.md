# IP do cliente atrás do túnel (TRUSTED_PROXIES)

## O problema

O `cloudflared` roda no mesmo computador da API e abre a conexão em `127.0.0.1:8000`. Para o FastAPI, todo visitante chega com o mesmo IP: `127.0.0.1`. O limite de **8 sessões de caminhada por IP** (`Backend/api/walk_session.py`) e o limite de senhas erradas do editor passam a valer para o túnel inteiro. O 9º usuário recebe **429**.

## A correção

Defina no `.env` da raiz:

```env
TRUSTED_PROXIES=127.0.0.1,::1
```

Com isso, quando o par do socket for o `cloudflared` local, a API lê o IP real do visitante em `CF-Connecting-IP` (ou, sem ele, em `X-Forwarded-For`, pegando o endereço mais à direita que não é proxy de confiança).

Regras (`Backend/api/editor_auth.py`, função `client_key`):

- Os headers **só** valem se o par do socket estiver em `TRUSTED_PROXIES`. Um cliente direto não consegue forjar o IP mandando o header.
- A lista aceita IP solto ou CIDR, separados por vírgula: `127.0.0.1,::1,10.0.0.0/8`. `::ffff:127.0.0.1` conta como `127.0.0.1`.
- `*`, `0.0.0.0/0`, `::/0` e itens inválidos são ignorados.
- Valor de header que não é IP é descartado e o cliente volta a ser o par do socket.
- Sem a variável (padrão), nada muda: os headers são ignorados.

O uvicorn continua com `--no-proxy-headers`. Sem isso, o padrão dele reescreve o par do socket a partir do header antes da nossa checagem.

## Conferir

Com a API e o túnel no ar, abra a API por dois celulares em redes diferentes: cada um conta o próprio limite. Nos testes: `test_cloudflared_on_loopback_gives_each_visitor_their_own_limit` e `test_trusted_proxies_*`.

Só ponha em `TRUSTED_PROXIES` o endereço de onde o proxy conecta. Se a API ficar exposta direto na rede, não inclua o IP da rede local inteira.
