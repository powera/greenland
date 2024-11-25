

CREATE TABLE models (
  codename TEXT PRIMARY KEY,
  displayname TEXT NOT NULL,
  launch_date TEXT,
  filesize_mb INTEGER,
  license_name TEXT
);

CREATE TABLE benchmarks (
  codename TEXT PRIMARY KEY,
  displayname TEXT NOT NULL,
  description TEXT,
  license_name TEXT
);

CREATE TABLE runs (
  run_id INTEGER PRIMARY KEY AUTOINCREMENT,
  runtime TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  model_name TEXT,
  benchmark_name TEXT,
  FOREIGN KEY (model_name) REFERENCES models (codename)
  FOREIGN KEY (benchmark_name) REFERENCES benchmarks (codename)
);

CREATE TABLE run_details (
  run_id INTEGER,
  benchmark_name TEXT,
  question_id TEXT,
  score INTEGER
);

