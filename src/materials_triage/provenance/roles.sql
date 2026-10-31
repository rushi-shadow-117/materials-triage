-- Three Postgres roles. Idempotent; applied by Compose on first start, by CI before tests,
-- and manually with: docker compose exec -T postgres psql -U triage -d triage < this file.
-- Dev passwords equal the role names. Deployments set real ones through secrets.
--
--   triage_migrate  owns schema "triage"; the only role that runs DDL (Alembic)
--   triage_app      INSERT and SELECT on every table; no UPDATE, DELETE, or DDL
--   triage_maint    SELECT and DELETE for retention, used only by a logged admin job;
--                   INSERT on maintenance_log so every deletion leaves a row

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'triage_migrate') THEN
    CREATE ROLE triage_migrate LOGIN PASSWORD 'triage_migrate';
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'triage_app') THEN
    CREATE ROLE triage_app LOGIN PASSWORD 'triage_app';
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'triage_maint') THEN
    CREATE ROLE triage_maint LOGIN PASSWORD 'triage_maint';
  END IF;
END
$$;

GRANT CONNECT ON DATABASE triage TO triage_migrate, triage_app, triage_maint;
CREATE SCHEMA IF NOT EXISTS triage AUTHORIZATION triage_migrate;
GRANT USAGE ON SCHEMA triage TO triage_app, triage_maint;

ALTER ROLE triage_migrate SET search_path = triage, public;
ALTER ROLE triage_app SET search_path = triage, public;
ALTER ROLE triage_maint SET search_path = triage, public;

-- Tables created by triage_migrate get these privileges automatically.
ALTER DEFAULT PRIVILEGES FOR ROLE triage_migrate IN SCHEMA triage
  GRANT SELECT, INSERT ON TABLES TO triage_app;
ALTER DEFAULT PRIVILEGES FOR ROLE triage_migrate IN SCHEMA triage
  GRANT SELECT, DELETE ON TABLES TO triage_maint;
ALTER DEFAULT PRIVILEGES FOR ROLE triage_migrate IN SCHEMA triage
  GRANT USAGE, SELECT ON SEQUENCES TO triage_app, triage_maint;
