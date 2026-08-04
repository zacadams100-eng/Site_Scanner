-- Baseline: the schema as it stood before tiling.
--
-- Written from the inline DDL that `ingest/run.py` used to execute at startup.
-- It is reproduced here verbatim, IF NOT EXISTS throughout, so this migration
-- is a no-op against a database that already ran the old code and a full
-- create against an empty one. Both must reach the same place, because both
-- exist: the benchmark database was built by the old path.
--
-- {res} is substituted per H3 resolution by ingest/migrate.py.

CREATE TABLE IF NOT EXISTS cell_stats_r{res} (
  dataset_id     text     NOT NULL,
  h3             bigint   NOT NULL,
  t              text     NOT NULL,
  mean           real,
  min            real,
  max            real,
  stddev         real,
  valid_fraction real     NOT NULL,
  PRIMARY KEY (dataset_id, h3, t)
);

-- Which (dataset, timestep, resolution) triples are already done. This is what
-- makes a resumed backfill skip work rather than redo it.
CREATE TABLE IF NOT EXISTS ingest_progress (
  dataset_id text NOT NULL,
  t          text NOT NULL,
  h3_res     int  NOT NULL,
  n_cells    int  NOT NULL,
  done_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (dataset_id, t, h3_res)
);
