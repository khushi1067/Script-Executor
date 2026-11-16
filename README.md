# Script Executor

Script Executor is a Python Script Execution & Monitoring Hub. It will provide a simple place to run Python scripts and review their execution results.

This initial version contains only the project structure and placeholder pages. Database connections, script execution, and monitoring are planned for future work.

## Tech stack

- **Python:** application language.
- **Streamlit:** web interface and standard multipage navigation.
- **PostgreSQL (Neon):** planned storage for execution records.
- **psycopg:** planned Python connection to PostgreSQL.
- **python-dotenv:** planned loading of local environment variables.
- **pytest:** testing.
- **Render:** planned application hosting.
- **GitHub:** source code management.

## Project structure

```text
app.py                      Main Streamlit page
pages/                      Placeholder pages in sidebar order
    1_Dashboard.py
    2_Run_Script.py
    3_Execution_History.py
    4_Run_Details.py
database/__init__.py        Package for future database code
services/__init__.py        Package for future application logic
scripts/__init__.py         Package for future Python scripts
tests/__init__.py           Package for future tests
requirements.txt           Python dependencies
.env.example               Environment variable template with no credentials
.gitignore                 Files excluded from version control
```

Streamlit automatically adds the Python files in `pages/` to its sidebar navigation. The numbered filenames control their order.

## Running locally

After installing the dependencies in your Python environment, start the app with:

```sh
streamlit run app.py
```

The placeholder app does not need a database or environment variables. For future database setup, `.env.example` documents the `DATABASE_URL` variable without storing credentials.

## Planned features

- Dashboard showing execution summaries.
- Page for selecting and running Python scripts.
- Execution history stored in PostgreSQL.
- Run details showing status, timing, output, and errors.
- Deployment on Render.
