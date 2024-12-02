

CREATE TABLE model (
  codename TEXT PRIMARY KEY,
  displayname TEXT NOT NULL,
  launch_date TEXT,
  filesize_mb INTEGER,
  license_name TEXT
);

CREATE TABLE benchmark (
  codename TEXT NOT NULL,
  metric TEXT NOT NULL,
  displayname TEXT NOT NULL,
  description TEXT,
  license_name TEXT,
  PRIMARY KEY (codename, metric)
);

CREATE TABLE question (
  question_id TEXT PRIMARY KEY,
  benchmark_name TEXT,
  question_info_json TEXT,
  FOREIGN KEY (benchmark_name) REFERENCES benchmark (codename)
);

CREATE TABLE run (
  run_id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  model_name TEXT,
  benchmark_name TEXT,
  benchmark_metric TEXT,
  normed_score INTEGER,
  FOREIGN KEY (model_name) REFERENCES model (codename),
  FOREIGN KEY (benchmark_name, benchmark_metric) REFERENCES benchmark (codename, metric)
);

CREATE TABLE run_detail (
  run_id INTEGER NOT NULL,
  question_id TEXT NOT NULL,
  benchmark_name TEXT,
  benchmark_metric TEXT,
  score INTEGER,
  eval_msec INTEGER,
  PRIMARY KEY (run_id, question_id),
  FOREIGN KEY (run_id) REFERENCES run (run_id),
  FOREIGN KEY (question_id) REFERENCES question (question_id)
  FOREIGN KEY (benchmark_name, benchmark_metric) REFERENCES benchmark (codename, metric)
);

