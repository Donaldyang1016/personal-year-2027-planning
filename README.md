# Personal Year 2027 · Streamlit starter

Initial dashboard for Personal Year 2027. The app contains Home, Annual, Quarterly, Monthly, Weekly and Tracker tabs.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Deploy using GitHub + Streamlit Community Cloud

1. Create a GitHub repo named `personal-year-2027` (prefer **private**, because this project is personal).
2. Push this folder's contents to the repo root, including `requirements.txt` and `data/goals.json`.
3. Visit https://share.streamlit.io/ and select **Create app** → **Yup, I have an app**.
4. Select your repo, branch `main`, and entrypoint `streamlit_app.py`, then deploy.
5. Future GitHub pushes to the configured branch update the hosted app automatically.

## Data and privacy

- `data/goals.json` contains **planning definitions only** and is version-controlled.
- Tracker updates are held in Streamlit session state, **not** saved permanently to GitHub or a database.
- Use **Export tracker backup** and save the downloaded JSON securely. You can restore it by uploading the backup and clicking **Import this backup**.
- **Do not assume a private GitHub repository makes a deployed web app private.** Check app access settings before adding sensitive information. For cross-device and durable storage, add authentication and a database such as Supabase in a later version.
- D02–D11 are placeholders, not invented plans. D01 targets are a draft pending final approval.

## File structure

```
streamlit_app.py        # Main app and all six tabs
requirements.txt       # Python dependencies
data/goals.json        # Goal structure and D01 draft
.streamlit/config.toml # Appearance
.gitignore
```
