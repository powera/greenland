#!/usr/bin/python3

import sqlite3

# Define the database file
db_file = "benchmarks.db"

# Define the schema file
schema_file = "benchmarks.sql"

# Connect to the database
with sqlite3.connect(db_file) as conn:
    # Read the schema file
    with open(schema_file, "r") as f:
        schema = f.read()
    # Execute the schema
    conn.executescript(schema)
    print("Database and schema created successfully.")
