-- Private audit schema, separate from Supabase public REST schemas.
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions;
CREATE SCHEMA trading;
REVOKE ALL ON SCHEMA trading FROM PUBLIC;
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='stock_app') THEN
    CREATE ROLE stock_app NOLOGIN;
  END IF;
END $$;
GRANT USAGE ON SCHEMA trading TO stock_app;
GRANT USAGE ON SCHEMA extensions TO stock_app;

CREATE TABLE trading.artifacts (
  sha256 text PRIMARY KEY CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  media_type text NOT NULL,
  content bytea NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (encode(extensions.digest(content,'sha256'),'hex')=sha256)
);
CREATE TABLE trading.snapshots (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  manifest_hash text UNIQUE NOT NULL REFERENCES trading.artifacts(sha256),
  label text NOT NULL,
  metadata jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE trading.snapshot_files (
  snapshot_id uuid NOT NULL REFERENCES trading.snapshots(id),
  path text NOT NULL,
  artifact_hash text NOT NULL REFERENCES trading.artifacts(sha256),
  PRIMARY KEY(snapshot_id,path)
);
CREATE TABLE trading.market_bars (
  snapshot_id uuid NOT NULL REFERENCES trading.snapshots(id),
  symbol text NOT NULL,
  session_date date NOT NULL,
  source_hash text NOT NULL REFERENCES trading.artifacts(sha256),
  open numeric NOT NULL CHECK(open>0),
  high numeric NOT NULL CHECK(high>0),
  low numeric NOT NULL CHECK(low>0),
  close numeric NOT NULL CHECK(close>0),
  adjusted_close numeric NOT NULL CHECK(adjusted_close>0),
  volume numeric NOT NULL CHECK(volume>=0),
  dividends numeric NOT NULL,
  stock_splits numeric NOT NULL,
  provider_fields jsonb NOT NULL,
  PRIMARY KEY(snapshot_id,symbol,session_date)
);
CREATE TABLE trading.research_trials (
  snapshot_id uuid NOT NULL REFERENCES trading.snapshots(id),
  context text NOT NULL,
  candidate text NOT NULL,
  stage text NOT NULL,
  specification jsonb NOT NULL,
  result jsonb NOT NULL,
  original_created_at timestamptz NOT NULL,
  PRIMARY KEY(snapshot_id,context,candidate,stage)
);
-- Store a signal/order intent, acknowledgement, fill, reconciliation or position
-- snapshot as a new event. Corrections append; previous records never disappear.
CREATE TABLE trading.audit_events (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_key text UNIQUE NOT NULL,
  kind text NOT NULL,
  occurred_at timestamptz NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  actor text NOT NULL,
  payload jsonb NOT NULL,
  previous_hash text NOT NULL,
  event_hash text NOT NULL,
  envelope jsonb NOT NULL
);
CREATE INDEX ON trading.audit_events(kind,occurred_at);
CREATE INDEX ON trading.market_bars(symbol,session_date);

CREATE FUNCTION trading.immutable_row() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Audit records are immutable; append a correction'; END $$;
DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['artifacts','snapshots','snapshot_files','market_bars','research_trials','audit_events'] LOOP
    EXECUTE format('ALTER TABLE trading.%I ENABLE ROW LEVEL SECURITY',t);
    EXECUTE format('CREATE POLICY app_read ON trading.%I FOR SELECT TO stock_app USING (true)',t);
    EXECUTE format('CREATE TRIGGER immutable_rows BEFORE UPDATE OR DELETE ON trading.%I FOR EACH ROW EXECUTE FUNCTION trading.immutable_row()',t);
    EXECUTE format('CREATE TRIGGER immutable_truncate BEFORE TRUNCATE ON trading.%I FOR EACH STATEMENT EXECUTE FUNCTION trading.immutable_row()',t);
    IF t <> 'audit_events' THEN
      EXECUTE format('CREATE POLICY app_insert ON trading.%I FOR INSERT TO stock_app WITH CHECK (true)',t);
      EXECUTE format('GRANT INSERT ON trading.%I TO stock_app',t);
    END IF;
    EXECUTE format('GRANT SELECT ON trading.%I TO stock_app',t);
  END LOOP;
END $$;

CREATE FUNCTION trading.append_event(p_key text,p_kind text,p_payload jsonb,p_occurred timestamptz,p_actor text)
RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,trading AS $$
DECLARE old trading.audit_events; prev text; body jsonb; result_id bigint;
BEGIN
  IF length(p_key)=0 OR length(p_kind)=0 OR p_payload IS NULL OR p_actor IS NULL OR p_occurred IS NULL THEN
    RAISE EXCEPTION 'Invalid audit event';
  END IF;
  -- A transaction-scoped lock serializes the hash chain and duplicate checks.
  PERFORM pg_advisory_xact_lock(20260929,100000);
  SELECT * INTO old FROM trading.audit_events WHERE event_key=p_key;
  IF FOUND THEN
    IF old.kind<>p_kind OR old.payload<>p_payload OR old.actor<>p_actor THEN
      RAISE EXCEPTION 'Idempotency key reused with different content';
    END IF;
    RETURN old.id;
  END IF;
  SELECT event_hash INTO prev FROM trading.audit_events ORDER BY id DESC LIMIT 1;
  prev:=coalesce(prev,repeat('0',64));
  body:=jsonb_build_object('key',p_key,'kind',p_kind,'occurred_at',p_occurred,'actor',p_actor,'payload',p_payload);
  INSERT INTO trading.audit_events(event_key,kind,occurred_at,actor,payload,previous_hash,event_hash,envelope)
    VALUES(p_key,p_kind,p_occurred,p_actor,p_payload,prev,
      encode(extensions.digest(convert_to(prev||body::text,'UTF8'),'sha256'),'hex'),body)
    RETURNING id INTO result_id;
  RETURN result_id;
END $$;
REVOKE ALL ON FUNCTION trading.append_event(text,text,jsonb,timestamptz,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION trading.append_event(text,text,jsonb,timestamptz,text) TO stock_app;
REVOKE ALL ON FUNCTION trading.immutable_row() FROM PUBLIC;

CREATE VIEW trading.audit_chain_health AS
SELECT id,
  previous_hash=coalesce(lag(event_hash) OVER (ORDER BY id),repeat('0',64)) AS linked,
  event_hash=encode(extensions.digest(convert_to(previous_hash||envelope::text,'UTF8'),'sha256'),'hex')
    AND envelope->>'key'=event_key AND envelope->>'kind'=kind
    AND envelope->>'actor'=actor AND envelope->'payload'=payload
    AND (envelope->>'occurred_at')::timestamptz=occurred_at AS valid_hash
FROM trading.audit_events;
GRANT SELECT ON trading.audit_chain_health TO stock_app;
COMMENT ON SCHEMA trading IS 'Stock research and execution audit; append-only for application role. Database owner can still alter schema; external backups are required.';
