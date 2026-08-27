# Lily API bridge deployment

Lily is split deliberately. The **request-driven FastAPI bridge** serves `/health`, expiring streaming-link endpoints, and the authenticated Mini App API. The **Telegram bot**, Local Bot API process, large-file media work, and SQLite-backed durable workspaces need a persistent process and storage; they must not be deployed as a Vercel Function.

| Target | Use it for | Do not use it for |
|---|---|---|
| Render Blueprint (`render.yaml`) | FastAPI bridge with an attached persistent disk | Local Bot API server or a complete long-polling bot setup. |
| Railway (`railway.json`) | FastAPI bridge with platform-managed process restart | Durable SQLite/workspace storage unless you separately provision persistent storage. |
| Vercel (`app.py`, `vercel.json`) | Request-scoped API bridge proof-of-concept | Long polling, local media conversion, Local Bot API, or durable local files. |
| Lily Mini App Vercel project | The Vite dashboard and its serverless API relay | Hosting the Python bot. |

## Required Mini App bridge configuration

Set these values in the selected **Lily FastAPI service**, never in Git:

| Variable | Required value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | The bot token that Telegram uses to sign Mini App `initData`. |
| `LILY_ENABLE_MINIAPP_BRIDGE` | `true` |
| `LILY_MINIAPP_ALLOWED_ORIGINS` | The exact HTTPS Mini App origin, for example `https://your-miniapp.example`. |
| `LILY_STREAM_SIGNING_SECRET` | A strong, independently generated secret if streaming links are enabled. |
| AI provider variables | A configured free/private profile first, then any opted-in Gemini, OpenAI, or Groq fallback profiles. |

The Mini App’s server relay must receive `LILY_API_BASE_URL` as the public HTTPS URL of this FastAPI service. The browser never receives that value. Its `/api/lily/*` relay forwards only Telegram `initData` and the three explicitly allow-listed Mini App paths. The bridge independently validates Telegram’s HMAC on every request.

## Platform notes

Render’s configuration starts an ASGI process on the platform-assigned port and attaches its data disk under `/var/data`. Railway’s configuration starts the same factory application and requires a generated public domain before the Mini App can reach it. Vercel discovers the FastAPI `app` instance in `app.py`, but its function model makes it unsuitable for the persistent bot side of Lily.[1] [2] [3] [4]

Before opening the Mini App, set the bot’s Web App URL in BotFather to the selected HTTPS dashboard origin. Then open Lily from Telegram so the frontend has valid `initData`; browser testing outside Telegram correctly shows the authentication-required state.

## References

[1]: https://docs.railway.com/guides/fastapi "Railway: Deploy a FastAPI App"
[2]: https://vercel.com/docs/frameworks/backend/fastapi "Vercel: Deploy a FastAPI app"
[3]: https://vercel.com/docs/frameworks/frontend/vite "Vercel: Vite on Vercel"
[4]: https://render.com/articles/fastapi-deployment-options "Render: FastAPI deployment options"
