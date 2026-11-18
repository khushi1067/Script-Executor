# Script Executor

Script Executor is a Streamlit workspace for checking CSVs, resolving duplicates, and running approved Python workflows. FastAPI records script executions and logs in Neon PostgreSQL.

## Run locally

Use Python 3.12 or later. Install the dependencies and create a local environment file.

```sh
python -m pip install -r requirements.txt
cp .env.example .env
```

Set `DATABASE_URL` in `.env` to your Neon connection string. Apply the schema and register the approved scripts once for a new database.

```sh
python -c "from deploy.start import initialize_database; initialize_database()"
```

Start FastAPI and Streamlit in separate terminals.

```sh
python -m uvicorn backend.main:app --reload
python -m streamlit run app.py
```

Run the test suite with `python -m pytest -q`.

## Deploy on Render

The repository includes a Docker-based [Render Blueprint](https://render.com/docs/infrastructure-as-code). In the Render dashboard, create a Blueprint from the GitHub repository and choose the branch containing `render.yaml`. Provide `DATABASE_URL` in Render's environment settings. A separate Neon database or branch lets you start with a clean execution history.

The container initializes the schema and registers the scripts on startup. Render generates `APP_PASSWORD`. Find it under the service's environment settings and sign in to the HTTPS service URL with username `workspace` and that password. FastAPI and Streamlit listen on loopback behind the authenticated proxy. Render checks the public `/healthz` endpoint.

After deployment, open the Dashboard through the HTTPS URL, run a workflow with the bundled sample, then check its entry in Execution History. The Blueprint uses a [free Render web service](https://render.com/docs/free), which can take time to wake after inactivity.
