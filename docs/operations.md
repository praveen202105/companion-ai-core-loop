# Production operations and recovery runbook

This runbook deploys the passcode-protected anonymous demo. It does not claim account-level auth or
billion-user capacity. Promote the exact commit that passed CI and staging smoke tests.

## Release topology

| Component | Platform | Production responsibility |
| --- | --- | --- |
| `companion-ai-web` | Vercel, root `apps/web` | UI, passcode gate, signed session cookie, BFF |
| `companion-ai-api` | Vercel, root `apps/api` | FastAPI/SSE, memory loop, rate limits, telemetry |
| `companion-ai-db` | Neon Singapore | PostgreSQL/pgvector persistence and retrieval |
| `companion-ai-cache` | Upstash Singapore | distributed locks and rate limits |

Vercel settings live in `apps/web/vercel.json` and `apps/api/vercel.json`. The API uses the
deterministic 384-dimensional hash embedding provider in this serverless free-tier deployment to
keep the function bundle small. `.railway/railway.ts` remains available as the container-hosted
alternative when a Railway workspace is unrestricted.

The free-tier topology intentionally omits the scheduled cleanup service. Run the cleanup command
manually until a cron service is restored; chat, persistence, retrieval, and rate limiting are
otherwise unchanged.

## Required configuration

Never paste secret values into source files, command arguments, CI output, or issue trackers.

Vercel `companion-ai-api` server-side variables:

```text
APP_ENV=staging|production
DATABASE_URL=<reference to Postgres.DATABASE_URL>
REDIS_URL=<reference to Redis.REDIS_URL>
GROQ_API_KEY=<sealed secret>
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_CHAT_MODEL=openai/gpt-oss-120b
GROQ_EXTRACTION_MODEL=openai/gpt-oss-20b
GROQ_JUDGE_MODEL=openai/gpt-oss-20b
LLM_PROVIDER=groq
EMBEDDING_PROVIDER=hash
INTERNAL_API_KEY=<at least 32 random characters>
CORS_ORIGINS=["https://the-exact-web-host"]
SESSION_RETENTION_DAYS=30
CHAT_RATE_LIMIT_PER_MINUTE=10
CHAT_RATE_LIMIT_PER_DAY=100
```

Vercel server-side variables:

```text
API_BASE_URL=https://the-environment-api-host
INTERNAL_API_KEY=<same value as the API project>
DEMO_PASSCODE_HASH=<scrypt hash>
COOKIE_SIGNING_SECRET=<at least 32 random characters>
```

Generate the passcode hash locally without committing it:

```bash
pnpm --filter @companion/web hash-passcode 'replace-with-a-long-demo-passcode'
```

Use separate internal keys, cookie secrets, passcodes, databases, and Redis instances for staging
and production.

## Staging release

1. Verify the release locally:

   ```bash
   nvm use
   make setup
   make lint
   make test
   make test-e2e
   pnpm typecheck:infra
   ```

2. Confirm GitHub Actions is green on the candidate commit. The backend job runs migrations and the
   repository contract suite against ephemeral pgvector/PostgreSQL and Redis services.

3. Link both Vercel projects to the same GitHub repository. Set their monorepo roots to `apps/api`
   and `apps/web`, and select Singapore (`sin1`) in both committed Vercel configurations.

   ```bash
   vercel link --project companion-ai-api --cwd apps/api
   vercel link --project companion-ai-web --cwd apps/web
   ```

4. Provision a Neon Free database and Upstash Redis Free resource through the Vercel Marketplace,
   connect them only to the API project, and disable Upstash automatic paid-plan upgrades.

5. Populate production secrets through Vercel encrypted environment variables. Do not deploy a
   source commit containing secrets. Keep the API key and database/cache URLs server-side.

6. Enable pgvector once in Neon, verify it, and run the migrations before deployment:

   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

   ```sql
   SELECT extversion FROM pg_extension WHERE extname = 'vector';
   ```

   ```bash
   vercel env run -e production --cwd apps/api -- env PYTHONPATH=src uv run alembic upgrade head
   vercel env run -e production --cwd apps/api -- env PYTHONPATH=src uv run alembic check
   ```

7. Deploy the API and wait for `/health/ready` to return HTTP 200.

8. Configure the web project's `API_BASE_URL` and matching internal key, then deploy `apps/web`.

9. Run the full smoke path:

   - `/health/live` and `/health/ready` are 200.
   - Unlock with the staging passcode.
   - Send a stable fact and receive a streamed Groq response.
   - Reload and confirm message history persists.
   - Correct the fact and confirm the inspector shows an update/supersession without stale leakage.
   - Retry a completed `request_id` and confirm the original result is returned.
   - Reset the chat and confirm messages and memories are gone.
   - Inspect Vercel logs: request IDs and hashed session IDs are present; raw messages are absent.

## Production promotion

Repeat the pgvector read-only verification in the production database, run Alembic, deploy the API,
and wait for readiness. Point the web Production variables at the production API, deploy from
`main`, and repeat every smoke test above. Only then create and push `product-v1.0.0`.

The supported release order is:

```text
CI green → production data prerequisites → migration → API deploy/readiness
→ web deploy → production smoke → tag
```

## Routine operations

- Inspect `/health/live` for process health and `/health/ready` for database, Redis, configuration,
  and pgvector readiness. Readiness intentionally does not call the model provider.
- Alert on repeated `chat_failed`, readiness failures, HTTP 5xx, elevated latency, Redis lock
  conflicts, and cleanup failures.
- Review Vercel function errors/latency and Neon/Upstash usage after each release.
- Until a cron service is restored, periodically run `companion cleanup` locally with production
  environment variables and confirm the deleted-session count.
- Enable and periodically test the database provider's supported restore workflow before accepting
  important production data.
- Rotate the demo passcode and cookie signing secret together when access should be revoked. Rotate
  `INTERNAL_API_KEY` in both Vercel projects as one coordinated change.

## Failure and recovery playbooks

### Migration fails

Do not bypass the pre-deploy gate. Read bounded build/deploy logs, fix the forward migration, run it
against staging, and redeploy. Prefer an expand/migrate/contract sequence; never edit a migration
already applied to production. Restore a database backup only when forward repair cannot preserve
data.

### API is unhealthy after deploy

Keep the previous healthy deployment serving traffic. Check `/health/ready`, then Vercel runtime
logs for configuration, database, Redis, or provider errors. Roll back to the last known-good Vercel
deployment if the fix is not immediate. Do not roll back the database schema unless a tested restore
plan exists.

### pgvector is missing

Readiness reports `vector_extension=missing`, and migrations using `vector(384)` cannot complete.
Enable the extension in Neon, verify `pg_extension` read-only, and redeploy. Never replace an
existing database without a backup and restore rehearsal.

### Groq is unavailable or rate-limited

The provider client retries only transient API failures, at most twice. The application never commits a partial assistant
message. The UI presents a retryable error; do not loosen database consistency or replay without the
same `request_id`. Retrieval and readiness remain available because readiness does not call Groq.
Normal small talk uses one provider call and memory-bearing turns normally use two; investigate any
sustained increase before raising limits. Never run `eval-live` against production credentials or as
part of CI.

### Redis is unavailable

Readiness fails and new production traffic should not be promoted. Existing instances must not fall
back to process-local locking in production. Restore Redis or its reference variable, verify ready,
then resume traffic.

### Suspected data or secret exposure

Disable the public demo, rotate the passcode, cookie secret, internal API key, and Groq key, then
invalidate affected sessions by deleting them or applying the retention cleanup. Preserve redacted
logs and deployment metadata for investigation; do not copy raw messages into incident channels.

### Cleanup fails

Run `companion cleanup` once against staging to reproduce and inspect the database error before
retrying. Deletion is transactional and uses foreign-key cascades; do not manually delete child
tables out of order.
