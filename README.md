# Admin Dorsha Agent

Panel de administración + landing pública del agente Dorsha.

## Arquitectura

```
admin-dorsha-agent/
├── landing/          → Vercel (dorsha.devcristobalvc.com)
│   ├── index.html    → landing producto (armonía Praktil, EN/ES)
│   ├── api/panel.py  → 302 al panel admin (lee URL actual del gist)
│   ├── api/ticket.mjs→ verifica sesión Privy + emite ticket HMAC si email autorizado
│   ├── api/config.mjs→ expone config pública (email autorizado)
│   └── static/privy-sdk.js → bundle del SDK de Privy (npm run build:privy)
└── admin_panel/      → Flask local (127.0.0.1:5057, systemd)
    ├── app.py        → /setup /login /dashboard /auth/ticket /history …
    ├── db.py         → SQLite (usuarios, sesiones, acciones, historial)
    ├── notify_url_change.py → publica URL del túnel Serveo en gist + Telegram
    └── request_approval.py  → bloquea acciones sensibles esperando aprobación
```

## Flujo de login (Privy, email + código OTP)

1. Landing → usuario pone email → `privy.auth.email.sendCode(email)`
2. Llega OTP por email → `loginWithCode` → sesión Privy (JWT)
3. `GET /api/ticket?token=<jwt>` → Vercel verifica con `@privy-io/server-auth` y valida que el email == `PRIVY_ALLOWED_EMAIL`
4. Devuelve `{ticket, exp, panel}` → redirect a `panel + /auth/ticket?t&e&m`
5. El panel valida HMAC + expiración + email → crea cookie de sesión → `/dashboard`

## Env vars requeridas

| Variable | Dónde | Descripción |
|---|---|---|
| `PRIVY_APP_ID` | Vercel + `~/.hermes/.env` | App de Privy |
| `PRIVY_APP_SECRET` | Vercel + `~/.hermes/.env` | Secreto de Privy |
| `PRIVY_TICKET_SECRET` | Vercel + `~/.hermes/.env` | HMAC compartido landing↔panel |
| `PRIVY_ALLOWED_EMAIL` | Vercel + `~/.hermes/.env` | Único email autorizado |
| `ADMIN_CHAT_ID` | `~/.hermes/.env` | Chat ID del super admin (Telegram) |

## Notas

- La URL del panel (túnel Serveo) cambia; `notify_url_change.py` la publica en un gist (ID en el código) y avisa por Telegram.
- El deploy de la landing: `vercel deploy --prod --yes --scope <team>` desde `landing/`.
- Los allowed origins de la app Privy se actualizan vía `POST /api/v1/apps/{id}` (Basic auth appId:secret + header `privy-app-id`).
