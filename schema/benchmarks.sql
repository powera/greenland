

CREATE TABLE model (
  codename TEXT PRIMARY KEY,
  displayname TEXT NOT NULL,
  launch_date TEXT,
  filesize_mb INTEGER,
  license_name TEXT
);

CREATE TABLE benchmark (
  codename TEXT PRIMARY KEY,
  displayname TEXT NOT NULL,
  description TEXT,
  license_name TEXT
);

CREATE TABLE run (
  run_id INTEGER PRIMARY KEY AUTOINCREMENT,
  runtime TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  model_name TEXT,
  benchmark_name TEXT,
  FOREIGN KEY (model_name) REFERENCES model (codename)
  FOREIGN KEY (benchmark_name) REFERENCES benchmark (codename)
);

CREATE TABLE run_details (
  run_id INTEGER,
  benchmark_name TEXT,
  question_id TEXT,
  score INTEGER
);

