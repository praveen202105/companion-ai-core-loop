import {
  database,
  defineRailway,
  github,
  group,
  preserve,
  project,
  redis,
  service,
} from "railway/iac";

const region = "asia-southeast1-eqsg3a";
const source = github("praveen202105/companion-ai-core-loop", { branch: "main" });
const build = {
  builder: "DOCKERFILE" as const,
  dockerfilePath: "apps/api/Dockerfile",
  watchPatterns: ["apps/api/**", "pyproject.toml", "uv.lock"],
};

export default defineRailway((ctx) => {
  const postgres = database("Postgres", "postgres", {
    image: "pgvector/pgvector:0.8.6-pg18-bookworm",
    output: "DATABASE_URL",
    defaultMountPath: "/var/lib/postgresql/data",
    region,
  });
  const cache = redis("Redis", { region });
  const environment = ctx.isEnvironment("production") ? "production" : "staging";

  const api = service("companion-api", {
    source,
    build,
    start:
      "uv run --no-sync --package companion-ai-api uvicorn companion.api:app " +
      "--host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*'",
    preDeploy: "uv run --no-sync --directory apps/api alembic upgrade head",
    healthcheck: "/health/ready",
    healthcheckTimeout: 300,
    regions: { [region]: 1 },
    deploy: {
      restartPolicyType: "ON_FAILURE",
      restartPolicyMaxRetries: 3,
      overlapSeconds: 20,
      drainingSeconds: 30,
    },
    env: {
      APP_ENV: environment,
      DATABASE_URL: postgres.env.DATABASE_URL,
      REDIS_URL: cache.env.REDIS_URL,
      GROQ_API_KEY: preserve(),
      GROQ_BASE_URL: "https://api.groq.com/openai/v1",
      GROQ_CHAT_MODEL: "openai/gpt-oss-120b",
      GROQ_EXTRACTION_MODEL: "openai/gpt-oss-20b",
      GROQ_JUDGE_MODEL: "openai/gpt-oss-20b",
      LLM_PROVIDER: "groq",
      EMBEDDING_PROVIDER: "multilingual-e5",
      INTERNAL_API_KEY: preserve(),
      CORS_ORIGINS: preserve(),
      SESSION_RETENTION_DAYS: "30",
      CHAT_RATE_LIMIT_PER_MINUTE: "10",
      CHAT_RATE_LIMIT_PER_DAY: "100",
    },
  });

  const applications = group("Applications", [api]);
  const data = group("Data", [postgres, cache]);

  return project("companion-ai", { resources: [applications, data] });
});
