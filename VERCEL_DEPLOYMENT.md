# Deploy QueimAlerta to Vercel

The repository includes a Vercel WSGI entry point (`app.py`), Python 3.12 pin, function configuration, bundle exclusions, PostgreSQL URL normalization, serverless-safe connection handling, and an authenticated ingestion endpoint.

## 1. Create the Vercel project

Push this repository to GitHub, GitLab, or Bitbucket and import it at <https://vercel.com/new>. Keep the repository root as the Vercel project root. Vercel detects `app.py` as a Flask WSGI entry point and installs dependencies from `pyproject.toml`.

A credentials-free preview can start with an empty temporary SQLite database. That mode only proves the web deployment; its data is ephemeral and can differ between function instances. Configure PostgreSQL before using the dashboard for monitoring.

## 2. Add persistent PostgreSQL

In the Vercel project:

1. Open **Storage** or **Marketplace**.
2. Add Neon Postgres, Supabase, or another PostgreSQL provider.
3. Connect it to the Production, Preview, and Development environments you need.
4. Confirm that the integration supplies `DATABASE_URL`, or create `QUEIMALERTA_DATABASE_URL` manually.

Accepted URL forms are normalized automatically:

```text
postgres://...
postgresql://...
postgresql+psycopg://...
```

Use the provider's pooled connection URL with TLS when available. `QUEIMALERTA_DATABASE_URL` takes precedence over `DATABASE_URL`.

The first application cold start creates missing tables. For a stricter production setup, initialize once with `queimalerta init-db`, then replace the dashboard credential with a read-only database user.

## 3. Configure environment variables

Add these in **Project → Settings → Environment Variables**:

```text
QUEIMALERTA_REFRESH_SECONDS=120
QUEIMALERTA_STALE_AFTER_MINUTES=30
QUEIMALERTA_MAX_MAP_POINTS=2000
QUEIMALERTA_DEBUG=false
QUEIMALERTA_LOG_LEVEL=INFO
```

For HTTP-triggered ingestion, also add a random value of at least 16 characters:

```text
CRON_SECRET=<random-secret>
QUEIMALERTA_INGEST_DAYS=1
```

Do not configure `QUEIMALERTA_HOST` or `QUEIMALERTA_PORT`; Vercel owns the listener.

## 4. Deploy

Redeploy after connecting PostgreSQL and setting the variables. A Git integration deploys automatically on push. With Vercel CLI 48.2.10 or newer, use:

```powershell
vercel
vercel --prod
```

## 5. Schedule ingestion

The protected route is:

```text
GET /api/cron/ingest
Authorization: Bearer <CRON_SECRET>
```

It refuses to run without `CRON_SECRET` or when the deployment uses ephemeral SQLite. It is idempotent because INPE source IDs are unique.

### Vercel Pro

To run every 10 minutes, add this top-level property to `vercel.json` and redeploy:

```json
{
  "crons": [
    {
      "path": "/api/cron/ingest",
      "schedule": "*/10 * * * *"
    }
  ]
}
```

Do not add that schedule on Vercel Hobby: Hobby cron jobs are limited to once per day and the deployment will be rejected. Vercel automatically sends `CRON_SECRET` as a bearer token for configured cron invocations.

### Vercel Hobby or AWS-based ingestion

Keep `vercel.json` as committed and invoke the protected endpoint from AWS EventBridge Scheduler, GitHub Actions, or another trusted scheduler. Send the bearer token from a secret store. For production audit/replay requirements, prefer the existing container ingestion job with S3 archival rather than the Vercel route, which stores the official source URL but does not archive the CSV.

## 6. Verify the deployment

Open these URLs after deployment:

```text
https://<project>.vercel.app/
https://<project>.vercel.app/health/live
https://<project>.vercel.app/health/ready
https://<project>.vercel.app/health/data
```

Expected results with PostgreSQL and a successful ingestion:

- `/`: HTTP 200 and the Dash interface.
- `/health/live`: HTTP 200.
- `/health/ready`: HTTP 200.
- `/health/data`: HTTP 200 with `status: fresh`.

Before the first ingestion, `/health/data` intentionally returns HTTP 503 with `status: stale`; this does not mean the web deployment failed.

Trigger the first ingestion manually:

```powershell
$headers = @{ Authorization = "Bearer $env:CRON_SECRET" }
Invoke-RestMethod -Uri "https://<project>.vercel.app/api/cron/ingest" -Headers $headers
```

Then check `/health/data` again.

## Deployment files

- `app.py`: exports the Flask WSGI application and protected ingestion route.
- `vercel.json`: configures a 300-second Python function and bundle exclusions.
- `.vercelignore`: excludes local environments, databases, raw data, and prototype remnants.
- `.python-version`: selects Python 3.12.
- `pyproject.toml`: runtime dependencies, including Flask directly.

## Operational limits

- Each Dash callback is a Vercel Function invocation.
- The committed defaults reduce Vercel map payloads to 2,000 points when the recommended environment variable is set.
- Use a pooled PostgreSQL URL. The app disables SQLAlchemy's process-local pool on Vercel.
- Vercel functions may overlap. The database upsert is idempotent, but a production scheduler should still avoid concurrent ingestion runs.
- A serverless ingestion request does not retain a raw CSV archive. Use the AWS/S3 worker when archival is required.

## Sources

- [Vercel Python runtime](https://vercel.com/docs/functions/runtimes/python)
- [Flask on Vercel](https://vercel.com/docs/frameworks/backend/flask)
- [Vercel Function limits](https://vercel.com/docs/functions/limitations)
- [Vercel Cron management](https://vercel.com/docs/cron-jobs/manage-cron-jobs)
- [Vercel Cron pricing and plan limits](https://vercel.com/docs/cron-jobs/usage-and-pricing)
- [Vercel storage integrations](https://vercel.com/docs/marketplace-storage)

Content based on web documentation was rephrased for compliance with licensing restrictions.
