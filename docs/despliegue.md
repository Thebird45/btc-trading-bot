# Despliegue en Oracle Cloud (Always Free)

Objetivo: el bot corriendo 24/7 en una VM gratuita, con la web en `https://tu-dominio` y los avisos en Telegram.

```
Internet ──HTTPS──▶ Caddy (certificado automático) ──▶ web (solo lectura)
                                                         │
                         bot (paper trading) ──▶ data/paper.db ◀┘
                          │
                          └──▶ Telegram (avisos y comandos)
```

## 1. Cuenta de Oracle Cloud

1. Regístrate en <https://www.oracle.com/cloud/free/>. Pide tarjeta solo para verificar identidad; los recursos *Always Free* no cobran.
2. **Región principal (home region): Bogotá (`sa-bogota-1`)** o São Paulo. Los recursos gratis solo existen en la región principal y **no se puede cambiar después**. Evita regiones de EE. UU.: Binance bloquea IPs de EE. UU., y eso importaría cuando se opere con dinero real.

## 2. Crear la máquina virtual

En la consola: **Compute → Instances → Create instance**.

| Campo | Valor |
|---|---|
| Name | `btc-bot` |
| Image | **Canonical Ubuntu 24.04** |
| Shape | **Ampere `VM.Standard.A1.Flex`**, 1 OCPU y 6 GB (gratis). Si dice "Out of capacity", usa **`VM.Standard.E2.1.Micro`** (AMD, 1 GB; también gratis y alcanza) |
| Networking | Crear una VCN nueva con subred pública y **asignar IP pública** |
| SSH keys | **Paste public key** → el contenido de `~/.ssh/id_ed25519.pub` de tu PC |

Anota la **IP pública** cuando la VM esté en verde (*Running*).

## 3. Abrir los puertos 80 y 443

**Networking → Virtual Cloud Networks →** tu VCN **→** la subred pública **→ Security List → Add Ingress Rules**, dos reglas:

| Source CIDR | IP Protocol | Destination Port |
|---|---|---|
| `0.0.0.0/0` | TCP | `80` |
| `0.0.0.0/0` | TCP | `443` |

(El firewall interno de la VM lo abre el script del paso 5).

## 4. Dominio gratis con DuckDNS

1. Entra a <https://www.duckdns.org> con tu cuenta de GitHub o Google.
2. Crea un subdominio (p. ej. `mibtcbot`) y en **current ip** pon la IP pública de la VM → **update ip**.
3. Tu dominio queda como `mibtcbot.duckdns.org`.

## 5. Preparar la VM

Desde tu PC:

```bash
ssh ubuntu@IP_DE_LA_VM
git clone https://github.com/Thebird45/btc-trading-bot.git
cd btc-trading-bot
bash deploy/setup-vm.sh      # Docker, firewall, swap, actualizaciones de seguridad y respaldos
exit                         # salir y volver a entrar para usar docker sin sudo
```

## 6. Configuración (`.env`)

En **tu PC**, dentro del proyecto:

```bash
uv run btcbot web set-password        # contraseña de la web (guarda solo el hash)
echo "DOMAIN=mibtcbot.duckdns.org" >> .env
scp .env ubuntu@IP_DE_LA_VM:~/btc-trading-bot/.env
```

Así el token de Telegram, el hash de la contraseña y el dominio pasan directo de tu PC a la VM, sin copiarlos a mano.

## 7. Arrancar

```bash
ssh ubuntu@IP_DE_LA_VM
cd btc-trading-bot
bash deploy/update.sh
```

En uno o dos minutos:

- Telegram: llega **"🚀 Paper trading iniciado"**.
- Web: `https://mibtcbot.duckdns.org` con candado HTTPS. En el celular, menú del navegador → **Agregar a pantalla de inicio**.

## Operación diaria

| Qué | Cómo |
|---|---|
| Ver estado | Telegram `/estado`, `/resumen`, o la web |
| Pausar (emergencia) | Telegram `/pausar` |
| Ver logs | `docker compose logs -f bot` (o `web`, `caddy`) |
| Actualizar a la última versión de `main` | `bash deploy/update.sh` |
| Reiniciar | `docker compose restart` |
| Respaldos | Automáticos a las 03:30 en `data/backups/` (14 días) y **por Telegram** tras cada resumen diario (`paper-AAAA-MM-DD.db.gz`) |
| Bajar un respaldo a tu PC | `scp ubuntu@IP:~/btc-trading-bot/data/backups/paper-AAAAMMDD.db .` |

El bot se reinicia solo si se cae, y también al reiniciar la VM (`restart: unless-stopped`). Si estuvo apagado, al volver procesa las velas que se perdió.

## Restaurar un respaldo de Telegram

Si se pierde la VM (o se migra a otra), descarga el último `paper-AAAA-MM-DD.db.gz` del chat del bot y:

```bash
gunzip paper-AAAA-MM-DD.db.gz
scp paper-AAAA-MM-DD.db ubuntu@IP_NUEVA:~/btc-trading-bot/data/paper.db
ssh ubuntu@IP_NUEVA 'cd btc-trading-bot && sudo chown 1000:1000 data/paper.db && docker compose restart bot web'
```

El bot sigue desde donde quedó el respaldo y recupera solo las velas que faltan.

## Problemas comunes

- **La web no carga / no hay HTTPS**: revisa las reglas del paso 3 y que DuckDNS apunte a la IP correcta. `docker compose logs caddy` muestra el error del certificado.
- **"Out of capacity" al crear la VM Ampere**: usa la AMD Micro o intenta más tarde.
- **No llegan avisos**: `docker compose logs bot | grep -i telegram`.
