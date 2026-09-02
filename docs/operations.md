# Production operations and recovery runbook

This runbook deploys the passcode-protected anonymous demo. It does not claim account-level auth or
billion-user capacity. Promote the exact commit that passed CI and staging smoke tests.

## Release topology

| Component | Platform | Production responsibility |
| --- | --- | --- |
| `companion-web` | Railway Singapore | UI, passcode gate, signed session cookie, BFF |
| `companion-api` | Railway Singapore | FastAPI/SSE, memory loop, rate limits, telemetry |
| `Postgres` | Railway Singapore | PostgreSQL 18 with pinned pgvector image |
| `Redis` | Railway Singapore | distributed locks and rate limits |
| `companion-cleanup` | Railway Singapore | daily expired-session deletion at 02:00 UTC |

Railway state is declared in `.railway/railway.ts`. The Docker image preloads
`intfloat/multilingual-e5-small`, runs as an unprivileged user, and listens on Railway's injected
`PORT`. A Vercel configuration remains available in `apps/web/vercel.json`, but the declared
production topology keeps the complete demo in one Railway project.

## Required configuration

Never paste secret values into source files, command arguments, CI output, or issue trackers.

Railway `companion-api` variables:

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
EMBEDDING_PROVIDER=multilingual-e5
INTERNAL_API_KEY=<at least 32 random characters>
CORS_ORIGINS=["https://the-exact-web-host"]
SESSION_RETENTION_DAYS=30
CHAT_RATE_LIMIT_PER_MINUTE=10
CHAT_RATE_LIMIT_PER_DAY=100
```

Railway `companion-web` server-side variables:

```text
API_BASE_URL=https://the-environment-api-host
INTERNAL_API_KEY=<same value as the corresponding Railway environment>
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

3. Link the Railway project and select `staging`. Use a Railway CLI version compatible with the
   installed `railway/iac` package, then review before applying:

   ```bash
   railway link --project companion-ai
   railway environment link staging
   railway config plan
   railway config apply
   ```

   The plan must contain only the web app, API, cleanup job, Postgres, Redis, their variables, and
   intended Singapore placement. Stop if it proposes deleting an unrelated resource.

4. Populate the preserved secrets through Railway's sealed-variable UI or stdin-capable CLI flow.
   Configure the API's generated Railway domain. Do not deploy a source commit containing secrets.

5. The database image includes pgvector binaries, but the extension is database-local. The user
   must connect to the staging `Postgres` service and run exactly once:

   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

   The implementation must not automate this command. Verify it read-only before deploying:

   ```sql
   SELECT extversion FROM pg_extension WHERE extname = 'vector';
   ```

6. Deploy the API. Its pre-deploy command runs `alembic upgrade head`; a non-zero exit prevents the
   new deployment from replacing the old one. Wait for `/health/ready` to return HTTP 200.

7. Configure the Railway web variables with the staging API URL and staging secrets, generate its
   domain, and deploy `companion-web`.

8. Run the full smoke path:

   - `/health/live` and `/health/ready` are 200.
   - Unlock with the staging passcode.
   - Send a stable fact and receive a streamed Groq response.
   - Reload and confirm message history persists.
   - Correct the fact and confirm the inspector shows an update/supersession without stale leakage.
   - Retry a completed `request_id` and confirm the original result is returned.
   - Reset the chat and confirm messages and memories are gone.
   - Inspect Railway logs: request IDs and hashed session IDs are present; raw messages are absent.

## Production promotion

Repeat the pgvector one-time command and read-only verification in the production database. Apply
the production Railway plan, configure production-only secrets, deploy the API, and wait for ready.
Point the Railway web service at the production API, deploy from `main`, and repeat every smoke test
above. Only then create and push `product-v1.0.0`.

The supported release order is:

```text
CI green → staging data prerequisites → staging migration/deploy → staging smoke
→ production data prerequisites → production migration/deploy → production smoke → tag
```

## Routine operations

- Inspect `/health/live` for process health and `/health/ready` for database, Redis, configuration,
  and pgvector readiness. Readiness intentionally does not call the model provider.
- Alert on repeated `chat_failed`, readiness failures, HTTP 5xx, elevated latency, Redis lock
  conflicts, and cleanup failures.
- Review Railway CPU, memory, HTTP latency, and bounded logs after each release. The local embedding
  model makes memory usage materially higher than the hash provider used by tests.
- Confirm `companion-cleanup` exits successfully each day and logs the deleted session count.
- Enable Railway database backups before production data is accepted and periodically test restore
  into a non-production environment.
- Rotate the demo passcode and cookie signing secret together when access should be revoked. Rotate
  `INTERNAL_API_KEY` on the Railway API and web services as one coordinated change.

## Failure and recovery playbooks

### Migration fails

Do not bypass the pre-deploy gate. Read bounded build/deploy logs, fix the forward migration, run it
against staging, and redeploy. Prefer an expand/migrate/contract sequence; never edit a migration
already applied to production. Restore a database backup only when forward repair cannot preserve
data.

### API is unhealthy after deploy

Keep the previous healthy deployment serving traffic. Check `/health/ready`, then Railway runtime
logs for configuration, database, Redis, model-cache, or port errors. Roll back/redeploy the last
known-good image from Railway's deployment history if the fix is not immediate. Do not roll back the
database schema unless a tested restore plan exists.

### pgvector is missing

Readiness reports `vector_extension=missing`, and migrations using `vector(384)` cannot complete.
Confirm the service uses the pinned pgvector image, have the user execute the one-time extension
command, verify `pg_extension` read-only, and redeploy. Never replace an existing database image in
place without a backup and restore rehearsal.

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

Run `companion cleanup` once against staging to reproduce, inspect the database error, then rerun the
Railway job after repair. Deletion is transactional and uses foreign-key cascades; do not manually
delete child tables out of order.
