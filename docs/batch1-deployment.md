# Batch 1 tracker deployment (D03–D05)

## What is deployed to GitHub

- `data/domains/D03.json`, `D04.json`, `D05.json`: approved Annual/Quarterly strategy and KPI definitions. Monthly/Weekly plans intentionally remain empty until approval.
- `data/routines/D05/*.json`: AM skincare, PM skincare, oral/grooming and hair/scalp step definitions. Products remain `null` pending confirmation; conditional steps are inactive by default.
- `batch1_tracker.py`: extra Streamlit tab, three-layer tracking UI, numeric body records, outcomes, and private persistent habit counters.
- `requirements.txt`: PostgreSQL driver.

## Launch

Existing Streamlit main file remains `streamlit_app.py`. In Streamlit Cloud, point the app at the same GitHub repository and main file. A GitHub commit updates source files; whether the hosted app redeploys depends on its connected Streamlit Cloud setup.

### Private persistence (required for saving check-ins)

Configure **Streamlit app secrets**, never commit these secrets to GitHub:

```toml
DATABASE_URL = "postgresql://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require"
APP_PASSWORD = "a-long-unique-private-access-password"
```

Use a private PostgreSQL database provisioned separately. The app lazily creates a `batch1_records` table when private tracking is unlocked. A single private password protects the tracking UI: this is a **single-user personal setup**, not a multi-user account/auth system. Restrict access to the Streamlit app where possible. Rotate the password if exposed, and protect database backups.

Without either secret, the new tab is read-only. It deliberately does not imply that records persist.

### Data separation

- GitHub: **plan definitions only**; no actual weight, skincare compliance, photos, study logs, or personal notes.
- PostgreSQL: actual records, keyed by stable IDs and dates.
- D04 morning weight and waist counts derive from the same numeric records; do not enter duplicate habit checkmarks.
- D04 Q1/Q2/Q3 weight outcomes derive only from complete consecutive seven-day weigh-in windows, not manual KPI verification.
- D05 product names/details must be reviewed before enabling optional/conditional steps.

### Scope and limitations

The existing D01/D02 application remains present, including its **session-only** legacy records and backup feature. The new PostgreSQL store currently protects **only the Batch 1 Tracker tab**; it does not yet migrate D01/D02 legacy session data. This is intentional to minimize regression risk and requires a separate migration before a genuinely unified all-domain private database can be claimed.

No domain-specific Monthly or Weekly action lists were generated. The new tab can record repeatable habits and verified outcomes before detailed schedules exist.

A GitHub commit is not proof that the hosted Streamlit application is running or that database connectivity works. Verify the deployment and secret configuration in Streamlit Cloud before relying on persistent records.
