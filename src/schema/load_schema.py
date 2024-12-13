#!/usr/bin/python3

import os.path

import sqlite3

import constants

def create_tables():
    # Define the database file
    db_file = os.path.join(constants.SCHEMA_DIR, "benchmarks.db")

    # Define the schema file
    schema_file = os.path.join(constants.SCHEMA_DIR, "benchmarks.sql")

    # Connect to the database
    with sqlite3.connect(db_file) as conn:
        # Read the schema file
        with open(schema_file, "r") as f:
            schema = f.read()
        # Execute the schema
        conn.executescript(schema)
        print("Database and schema created successfully.")

if __name__ == "__main__":
  create_tables()
