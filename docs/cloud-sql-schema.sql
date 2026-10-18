-- Jagran Orbit: MySQL schema for Cloud SQL (MySQL 8.0+; also valid on MariaDB 10.4+).
--
-- Generated from the project's Alembic migration 0001 (backend/migrations/versions/0001_baseline_schema.py),
-- so it matches `flask db upgrade` exactly. Part 1 is required. Part 2 is the newsroom source table the pipeline
-- reads from; skip it if you only load a CSV (`flask orbit pipeline run --source csv --csv file.csv`).
--
-- Usage:   mysql -h <cloud-sql-ip> -u <user> -p < cloud-sql-schema.sql
-- Then:    set MYSQL_* in backend/.env, run `flask --app wsgi orbit seed` to load the bundled 15-sector snapshot.
-- If you apply this file, `flask db upgrade` is a no-op (the alembic_version row at the end marks it current).

CREATE DATABASE IF NOT EXISTS jagran_orbit CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE jagran_orbit;

-- ===================== Part 1: application tables (required) =====================
CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001

CREATE TABLE orbit_pipeline_runs (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    source VARCHAR(40) NOT NULL, 
    source_detail VARCHAR(255) NOT NULL DEFAULT '', 
    status VARCHAR(12) NOT NULL, 
    is_active BOOL NOT NULL DEFAULT false, 
    started_at DATETIME NOT NULL, 
    finished_at DATETIME, 
    reports_in INTEGER NOT NULL DEFAULT 0, 
    considered INTEGER NOT NULL DEFAULT 0, 
    classified INTEGER NOT NULL DEFAULT 0, 
    events_out INTEGER NOT NULL DEFAULT 0, 
    skipped INTEGER NOT NULL DEFAULT 0, 
    meta JSON, 
    error TEXT, 
    CONSTRAINT pk_orbit_pipeline_runs PRIMARY KEY (id)
)CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_unicode_ci;

CREATE INDEX ix_orbit_pipeline_runs_is_active ON orbit_pipeline_runs (is_active);

CREATE INDEX ix_orbit_pipeline_runs_status ON orbit_pipeline_runs (status);

CREATE TABLE orbit_translations (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    biz_id INTEGER NOT NULL, 
    headline_en TEXT NOT NULL, 
    summary_en TEXT NOT NULL, 
    model VARCHAR(80) NOT NULL, 
    translated_at DATETIME NOT NULL, 
    CONSTRAINT pk_orbit_translations PRIMARY KEY (id), 
    CONSTRAINT uq_orbit_translations_biz_id UNIQUE (biz_id)
)CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_unicode_ci;

CREATE TABLE orbit_workspaces (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    token VARCHAR(64) NOT NULL, 
    sector VARCHAR(20) NOT NULL DEFAULT 'Automotive', 
    created_at DATETIME NOT NULL, 
    updated_at DATETIME NOT NULL, 
    CONSTRAINT pk_orbit_workspaces PRIMARY KEY (id), 
    CONSTRAINT uq_orbit_workspaces_token UNIQUE (token)
)CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_unicode_ci;

CREATE TABLE orbit_business_profiles (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    workspace_id INTEGER NOT NULL, 
    sector VARCHAR(20) NOT NULL, 
    data JSON NOT NULL, 
    updated_at DATETIME NOT NULL, 
    CONSTRAINT pk_orbit_business_profiles PRIMARY KEY (id), 
    CONSTRAINT fk_orbit_business_profiles_workspace_id_orbit_workspaces FOREIGN KEY(workspace_id) REFERENCES orbit_workspaces (id), 
    CONSTRAINT uq_orbit_profile UNIQUE (workspace_id, sector)
)CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_unicode_ci;

CREATE TABLE orbit_events (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    run_id INTEGER NOT NULL, 
    code VARCHAR(12) NOT NULL, 
    var VARCHAR(40) NOT NULL, 
    topic VARCHAR(40) NOT NULL DEFAULT '', 
    is_index BOOL NOT NULL DEFAULT false, 
    label VARCHAR(120) NOT NULL, 
    unit VARCHAR(8) NOT NULL, 
    hit DOUBLE NOT NULL, 
    direction SMALLINT NOT NULL, 
    mag DOUBLE NOT NULL, 
    extracted BOOL NOT NULL DEFAULT false, 
    n_extracted INTEGER NOT NULL DEFAULT 0, 
    n_facts INTEGER NOT NULL DEFAULT 0, 
    report_count INTEGER NOT NULL DEFAULT 0, 
    first_at DATETIME NOT NULL, 
    last_at DATETIME NOT NULL, 
    rep TEXT NOT NULL, 
    rep_summary TEXT NOT NULL, 
    level VARCHAR(60), 
    CONSTRAINT pk_orbit_events PRIMARY KEY (id), 
    CONSTRAINT fk_orbit_events_run_id_orbit_pipeline_runs FOREIGN KEY(run_id) REFERENCES orbit_pipeline_runs (id)
)CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_unicode_ci;

CREATE INDEX ix_orbit_events_run_code ON orbit_events (run_id, code);

CREATE INDEX ix_orbit_events_run_last ON orbit_events (run_id, last_at);

CREATE INDEX ix_orbit_events_run_var ON orbit_events (run_id, var);

CREATE TABLE orbit_tasks (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    workspace_id INTEGER NOT NULL, 
    sector VARCHAR(20) NOT NULL, 
    client_id VARCHAR(64) NOT NULL, 
    position INTEGER NOT NULL DEFAULT 0, 
    title VARCHAR(300) NOT NULL, 
    owner VARCHAR(120) NOT NULL DEFAULT '', 
    due VARCHAR(60) NOT NULL DEFAULT '', 
    `signal` VARCHAR(64) NOT NULL DEFAULT '', 
    done BOOL NOT NULL DEFAULT false, 
    updated_at DATETIME NOT NULL, 
    CONSTRAINT pk_orbit_tasks PRIMARY KEY (id), 
    CONSTRAINT fk_orbit_tasks_workspace_id_orbit_workspaces FOREIGN KEY(workspace_id) REFERENCES orbit_workspaces (id), 
    CONSTRAINT uq_orbit_task UNIQUE (workspace_id, sector, client_id)
)CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_unicode_ci;

CREATE INDEX ix_orbit_tasks_workspace_id ON orbit_tasks (workspace_id);

CREATE TABLE orbit_event_reports (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    event_id INTEGER NOT NULL, 
    sl INTEGER NOT NULL, 
    reported_at DATETIME NOT NULL, 
    section VARCHAR(80) NOT NULL DEFAULT '', 
    headline TEXT NOT NULL, 
    summary TEXT NOT NULL, 
    mag DOUBLE, 
    direction SMALLINT NOT NULL DEFAULT 0, 
    outlook BOOL NOT NULL DEFAULT false, 
    level VARCHAR(60), 
    machine BOOL NOT NULL DEFAULT false, 
    CONSTRAINT pk_orbit_event_reports PRIMARY KEY (id), 
    CONSTRAINT fk_orbit_event_reports_event_id_orbit_events FOREIGN KEY(event_id) REFERENCES orbit_events (id)
)CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_unicode_ci;

CREATE INDEX ix_orbit_event_reports_event_id ON orbit_event_reports (event_id);

CREATE INDEX ix_orbit_event_reports_sl ON orbit_event_reports (sl);

CREATE TABLE orbit_event_tags (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    event_id INTEGER NOT NULL, 
    kind VARCHAR(12) NOT NULL, 
    value VARCHAR(40) NOT NULL, 
    position SMALLINT NOT NULL DEFAULT 0, 
    CONSTRAINT pk_orbit_event_tags PRIMARY KEY (id), 
    CONSTRAINT fk_orbit_event_tags_event_id_orbit_events FOREIGN KEY(event_id) REFERENCES orbit_events (id)
)CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_unicode_ci;

CREATE INDEX ix_orbit_event_tags_event_id ON orbit_event_tags (event_id);

CREATE INDEX ix_orbit_event_tags_kind_value ON orbit_event_tags (kind, value);

INSERT INTO alembic_version (version_num) VALUES ('0001');


-- ===================== Part 2: newsroom source table (optional) =====================
-- The pipeline's default source (ORBIT_SOURCE_TABLE=jagran_biz). Migrations never create or alter it.
-- headline/summary are the original Hindi; headline_en/summary_en are English where available.
CREATE TABLE IF NOT EXISTS jagran_biz (
    id INT NOT NULL AUTO_INCREMENT,
    source_no INT DEFAULT NULL,
    section VARCHAR(80) NOT NULL DEFAULT '',
    headline TEXT,
    summary TEXT,
    published_at VARCHAR(32) NOT NULL DEFAULT '',
    article_type VARCHAR(40) NOT NULL DEFAULT '',
    url TEXT,
    headline_en TEXT,
    summary_en TEXT,
    PRIMARY KEY (id),
    KEY ix_jagran_biz_section (section),
    KEY ix_jagran_biz_published_at (published_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
