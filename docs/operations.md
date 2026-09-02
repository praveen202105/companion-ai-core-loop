# Production operations and recovery runbook

This runbook deploys the Google-authenticated companion demo. Every verified Google subject owns
one persistent Mira conversation; logout never deletes data and “New chat” deletes only that user's
session tree. Promote only a commit that passed CI and staging smoke tests.

## Release topology

| Component | Platform | Production responsibility |
| --- | --- | --- |
| `companion-ai-web` | Vercel, root `apps/web` | Auth.js, UI, server-side BFF |
| `companion-ai-api` | Vercel, root `apps/api` | FastAPI/SSE, identity scope, memory loop, controls |
| `companion-ai-db` | Neon Singapore | users, PostgreSQL/pgvector chat persistence |
| `companion-ai-cache` | Upstash Singapore | distributed locks and rate limits |
| Google OAuth client | Google Cloud | verified OpenID identity |

Vercel settings live in `apps/web/vercel.json` and `apps/api/vercel.json`. The API uses deterministic
384-dimensional hash embeddings in the serverless free-tier build to keep its bundle small.
`.railway/railway.ts` remains a container-hosted alternative.

There is no cleanup service in the three-service/free topology. Authenticated sessions have
`expires_at=NULL` and are intentionally permanent until reset. The manual cleanup command removes
only expired legacy anonymous sessions.

## Google OAuth configuration

In Google Cloud, configure the OAuth consent screen for an External application and create an
OAuth 2.0 Client ID of type **Web application**. Request only the basic `openid`, `email`, and
`profile` scopes. During Google testing mode add the intended test accounts; publish the consent
screen when any verified Google account should be allowed.

Authorized JavaScript origins:

```text
http://localhost:3000
https://companion-ai-web-two.vercel.app
```

Authorized redirect URIs must match exactly:

```text
http://localhost:3000/api/auth/callback/google
https://companion-ai-web-two.vercel.app/api/auth/callback/google
```

Copy the client ID and client secret directly into Vercel encrypted environment variables. Never
place either value in Git, screenshots, logs, or command history. Auth.js accepts only
`email_verified=true`; the Google `sub`, not the mutable email address, becomes the backend subject.
No database adapter or persisted Google access/refresh token is used.

## Required configuration

Vercel `companion-ai-api` server-side variables:

```text
APP_ENV=staging|production
DATABASE_URL=<Neon PostgreSQL URL>
REDIS_URL=<Upstash Redis URL>
GROQ_API_KEY=<sealed secret>
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_CHAT_MODEL=openai/gpt-oss-120b
GROQ_EXTRACTION_MODEL=openai/gpt-oss-20b
GROQ_JUDGE_MODEL=openai/gpt-oss-20b
LLM_PROVIDER=groq
EMBEDDING_PROVIDER=hash
INTERNAL_API_KEY=<at least 32 random characters>
CORS_ORIGINS=["https://companion-ai-web-two.vercel.app"]
ENABLE_ANONYMOUS_API=false
SESSION_RETENTION_DAYS=30
CHAT_RATE_LIMIT_PER_MINUTE=10
CHAT_RATE_LIMIT_PER_DAY=100
```

Vercel `companion-ai-web` server-side variables:

```text
API_BASE_URL=https://companion-ai-api-ten.vercel.app
INTERNAL_API_KEY=<same value as the API project>
AUTH_SECRET=<at least 32 random bytes>
AUTH_GOOGLE_ID=<Google OAuth web client ID>
AUTH_GOOGLE_SECRET=<Google OAuth web client secret>
```

Generate `AUTH_SECRET` locally with `openssl rand -base64 32` and enter it directly in Vercel.
`E2E_AUTH_BYPASS` must never be configured in production; the code also refuses the bypass when
`NODE_ENV=production`. The retired `DEMO_PASSCODE`, `DEMO_PASSCODE_HASH`, and
`COOKIE_SIGNING_SECRET` variables are not used by the application.

Use separate internal keys, Auth.js secrets, OAuth clients, databases, and Redis instances for
staging and production. A stable production hostname is important because the OAuth redirect URI is
exact.

## Backward-compatible rollout

1. Verify locally:

   ```bash
   nvm use
   make setup
   make lint
   make test
   make test-e2e
   pnpm typecheck:infra
   ```

2. Confirm GitHub Actions is green. The backend job runs migrations and the repository contract
   suite against ephemeral PostgreSQL/pgvector and Redis services.

3. Apply migration `0004_authenticated_users` before switching the frontend. For the first API
   rollout only, leave `ENABLE_ANONYMOUS_API=true` so the currently deployed passcode frontend keeps
   working. Verify pgvector once in Neon:

   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   SELECT extversion FROM pg_extension WHERE extname = 'vector';
   ```

   Pulling a Vercel environment locally writes secrets to an ignored file, so remove it immediately
   after the migration:

   ```bash
   vercel env pull .env.production.local --environment=production --cwd apps/api
   PYTHONPATH=apps/api/src uv run --env-file apps/api/.env.production.local \
     --package companion-ai-api alembic -c apps/api/alembic.ini upgrade head
   PYTHONPATH=apps/api/src uv run --env-file apps/api/.env.production.local \
     --package companion-ai-api alembic -c apps/api/alembic.ini check
   ```

4. Deploy `companion-ai-api`, verify `/health/live` and `/health/ready`, and directly verify the
   authenticated bootstrap endpoint returns 401 without internal identity headers.

5. Configure the Google OAuth client and all Auth.js variables in `companion-ai-web`. Deploy the
   frontend only after its exact production callback URI is authorized.

6. Smoke test with two real Google accounts:

   - Signed-out requests show the Google screen and BFF calls return 401.
   - Account A sends a fact and receives streamed deltas; reload and logout/login preserve it.
   - Account B cannot see A's messages, memories, traces, or reset result.
   - A correction supersedes the old fact without stale retrieval leakage.
   - Retrying a completed `request_id` returns the original result.
   - New chat removes only the current account's messages and memories.
   - Logs contain hashed user/session IDs but no email, Google subject, or message body.

7. Set API `ENABLE_ANONYMOUS_API=false`, redeploy, and verify legacy session-ID endpoints are 404.
   Then remove the retired passcode/cookie variables from Vercel.

The supported release order is:

```text
CI green → additive migration → backward-compatible API → Google OAuth configuration
→ authenticated web → two-account smoke test → disable anonymous API → remove passcode secrets
```

## Routine operations

- Check `/health/live` for process health and `/health/ready` for database, Redis, configuration,
  and pgvector readiness. Readiness intentionally does not call Groq.
- Alert on repeated `chat_failed`, readiness failures, HTTP 5xx, elevated latency, Redis lock
  conflicts, and migration failures.
- Review Vercel function errors/latency and Neon/Upstash usage after each release.
- Periodically run `companion cleanup` only for expired anonymous rows; confirm authenticated rows
  with NULL expiry remain untouched.
- Enable and periodically test the database provider's restore workflow before accepting important
  production data.
- Rotate `INTERNAL_API_KEY` in both Vercel projects as one coordinated change. Rotating
  `AUTH_SECRET` signs every browser out but does not delete backend chat data.
- To revoke OAuth access, use Google Cloud and rotate the OAuth client secret; do not delete user
  data unless that deletion is explicitly intended.

## Failure and recovery playbooks

### Migration fails

Keep the last healthy deployment serving traffic. Fix the forward migration and retest it in
staging; never edit an already-applied migration. Restore from backup only when a forward repair
cannot preserve data.

### Google returns redirect or configuration errors

Compare the browser callback URL character-for-character with the authorized Google redirect URI.
Check the Vercel production hostname and `AUTH_GOOGLE_ID` environment target. Do not weaken the
verified-email or server-side session checks.

### API is unhealthy after deploy

Inspect `/health/ready` and bounded Vercel logs for configuration, database, Redis, or provider
errors. Roll back the API deployment if the fix is not immediate. Do not roll back a migrated
database schema without a tested restore plan.

### Groq is unavailable or rate-limited

The provider retries transient failures at most twice. A partial assistant message is never
committed, and the UI offers an idempotent retry using the same `request_id`. Retrieval and
readiness remain available. Never run `eval-live` with production credentials or from CI.

### Redis is unavailable

Readiness fails and production traffic must not fall back to process-local locking. Restore Redis,
verify readiness, then resume promotion.

### Suspected identity or secret exposure

Disable the public deployment, rotate the affected Google client secret, Auth.js secret, internal
API key, and provider key. Preserve only redacted logs and deployment metadata. Rotating
`AUTH_SECRET` invalidates login cookies; it does not erase conversations. Use the user-scoped reset
or a separately approved database deletion only when data removal is intended.
