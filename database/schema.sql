-- Each primary key is an automatically generated, unique row identifier.
CREATE TABLE IF NOT EXISTS scripts (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- NOT NULL requires a value; UNIQUE prevents duplicate script names.
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS script_runs (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- This foreign key connects each run to an existing script.
    script_id INTEGER NOT NULL REFERENCES scripts(id),
    -- CHECK constraints restrict values to the allowed statuses and durations.
    status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP WITH TIME ZONE,
    duration_ms INTEGER CHECK (duration_ms >= 0),
    result_summary TEXT
);

CREATE TABLE IF NOT EXISTS execution_logs (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- This foreign key connects each log entry to an existing run.
    run_id INTEGER NOT NULL REFERENCES script_runs(id),
    -- Only these three log levels are allowed.
    level TEXT NOT NULL CHECK (level IN ('INFO', 'WARNING', 'ERROR')),
    message TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- This index helps queries retrieve the most recent runs first.
CREATE INDEX IF NOT EXISTS idx_script_runs_started_at
    ON script_runs (started_at DESC);

-- This index helps queries retrieve one run's logs in timestamp order.
CREATE INDEX IF NOT EXISTS idx_execution_logs_run_id_created_at
    ON execution_logs (run_id, created_at);
