# Cloud Database Setup Guide

This document explains how to configure and use cloud databases (PostgreSQL, MySQL, etc.) with the Greenland project.

## Overview

The Greenland project now supports both **SQLite** (for local development) and **cloud databases** (PostgreSQL, MySQL, MariaDB, etc.) for production deployments. The system automatically detects which database to use based on environment variables.

## Supported Databases

- **SQLite** - Default for local development
- **PostgreSQL** - Recommended for cloud deployments
- **MySQL / MariaDB** - Full support
- Any database supported by SQLAlchemy

## Configuration

### Environment Variables

The system uses the following environment variables to configure database connections:

#### Main Linguistics Database

- **`DATABASE_URL`** - Primary environment variable for cloud databases
  - Format: `postgresql://username:password@host:port/database`
  - Takes precedence over file-based paths
  - Used by all wordfreq modules and agents

- **`WORDFREQ_DATABASE_URL`** - Alternative/legacy name for the same purpose

- **`BARSUKAS_DB_PATH`** - SQLite file path (used when DATABASE_URL is not set)
  - Default: `src/wordfreq/data/linguistics.sqlite`

#### Benchmarks Database

- **`BENCHMARKS_DATABASE_URL`** - Database URL for benchmarks
  - Format: Same as DATABASE_URL
  - Default: Uses SQLite at `src/benchmarks/schema/benchmarks.db`

### Database URL Format

Database URLs follow the standard SQLAlchemy format:

```
dialect+driver://username:password@host:port/database
```

**Examples:**

```bash
# PostgreSQL
export DATABASE_URL="postgresql://myuser:mypass@localhost:5432/greenland"

# PostgreSQL with explicit driver
export DATABASE_URL="postgresql+psycopg2://myuser:mypass@localhost:5432/greenland"

# MySQL
export DATABASE_URL="mysql://myuser:mypass@localhost:3306/greenland"

# MySQL with explicit driver
export DATABASE_URL="mysql+pymysql://myuser:mypass@localhost:3306/greenland"

# SQLite (file path)
export DATABASE_URL="sqlite:///path/to/database.sqlite"

# SQLite (relative path)
export DATABASE_URL="sqlite:///./data/linguistics.sqlite"
```

## Setup Instructions

### 1. Local Development (SQLite)

**No configuration needed!** The system uses SQLite by default.

```bash
# Just run the application
cd src/barsukas
./launch.sh
```

### 2. PostgreSQL on Cloud (Recommended)

#### Step 1: Install PostgreSQL Driver

```bash
pip install psycopg2-binary
# OR for source install:
pip install psycopg2
```

#### Step 2: Create Database

```bash
# Connect to PostgreSQL
psql -U postgres

# Create database
CREATE DATABASE greenland;

# Create user (optional)
CREATE USER greenland_user WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE greenland TO greenland_user;
```

#### Step 3: Set Environment Variable

```bash
export DATABASE_URL="postgresql://greenland_user:your_secure_password@localhost:5432/greenland"
```

#### Step 4: Initialize Database

```bash
# The application will automatically create tables on first run
cd src/barsukas
./launch.sh
```

### 3. MySQL / MariaDB

#### Step 1: Install MySQL Driver

```bash
pip install pymysql
# OR
pip install mysqlclient
```

#### Step 2: Create Database

```bash
# Connect to MySQL
mysql -u root -p

# Create database
CREATE DATABASE greenland CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

# Create user (optional)
CREATE USER 'greenland_user'@'localhost' IDENTIFIED BY 'your_secure_password';
GRANT ALL PRIVILEGES ON greenland.* TO 'greenland_user'@'localhost';
FLUSH PRIVILEGES;
```

#### Step 3: Set Environment Variable

```bash
export DATABASE_URL="mysql+pymysql://greenland_user:your_secure_password@localhost:3306/greenland"
```

#### Step 4: Initialize Database

```bash
cd src/barsukas
./launch.sh
```

### 4. Cloud-Hosted Databases

#### DigitalOcean Managed Database

```bash
# Get connection string from DigitalOcean console
# Example format:
export DATABASE_URL="postgresql://doadmin:password@db-postgresql-nyc3-12345.db.ondigitalocean.com:25060/greenland?sslmode=require"
```

#### AWS RDS

```bash
# Get endpoint from AWS console
export DATABASE_URL="postgresql://admin:password@mydb.abc123.us-east-1.rds.amazonaws.com:5432/greenland"
```

#### Google Cloud SQL

```bash
# Use Cloud SQL Proxy or public IP
export DATABASE_URL="postgresql://user:password@/greenland?host=/cloudsql/project:region:instance"
```

#### Heroku Postgres

```bash
# Heroku automatically sets DATABASE_URL
# No manual configuration needed!
```

## Migrating from SQLite to Cloud Database

### Option 1: Export and Import (Recommended for Small Databases)

```bash
# Export from SQLite
sqlite3 src/wordfreq/data/linguistics.sqlite .dump > backup.sql

# Import to PostgreSQL
psql -U greenland_user -d greenland -f backup.sql
```

### Option 2: Use pgloader (Recommended for Large Databases)

```bash
# Install pgloader
apt-get install pgloader  # Ubuntu/Debian
brew install pgloader      # macOS

# Create migration config
cat > migrate.load <<EOF
LOAD DATABASE
     FROM sqlite://src/wordfreq/data/linguistics.sqlite
     INTO postgresql://greenland_user:password@localhost/greenland
EOF

# Run migration
pgloader migrate.load
```

### Option 3: Python Script Migration

```python
#!/usr/bin/env python3
"""Migrate data from SQLite to cloud database."""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from wordfreq.storage.models.schema import Base

# Source: SQLite
sqlite_engine = create_engine('sqlite:///src/wordfreq/data/linguistics.sqlite')

# Destination: Cloud database (set DATABASE_URL first)
cloud_url = os.environ['DATABASE_URL']
cloud_engine = create_engine(cloud_url)

# Create tables in cloud database
Base.metadata.create_all(cloud_engine)

# TODO: Copy data table by table
# This is a template - you'll need to implement the actual data copying logic
```

## Testing Cloud Database Connection

### Test Script

Save this as `test_db_connection.py`:

```python
#!/usr/bin/env python3
"""Test cloud database connection."""

import os
import sys
from sqlalchemy import create_engine, text
from wordfreq.storage.utils.database_url import (
    get_database_url,
    parse_database_url,
    is_sqlite,
    is_cloud_database
)

def test_connection():
    """Test database connection and print information."""

    # Get database URL
    db_url = get_database_url()
    print(f"Database URL: {db_url}")

    # Parse URL
    db_info = parse_database_url(db_url)
    print(f"\nDatabase Info:")
    print(f"  Type: {db_info['scheme']}")
    print(f"  Is SQLite: {db_info['is_sqlite']}")
    print(f"  Is PostgreSQL: {db_info['is_postgres']}")
    print(f"  Is MySQL: {db_info['is_mysql']}")

    if not db_info['is_sqlite']:
        print(f"  Host: {db_info['hostname']}")
        print(f"  Port: {db_info['port']}")
        print(f"  Database: {db_info['database']}")
        print(f"  Username: {db_info['username']}")

    # Test connection
    print("\nTesting connection...")
    try:
        engine = create_engine(db_url)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            print("✓ Connection successful!")

            # Try to get version
            if db_info['is_postgres']:
                result = conn.execute(text("SELECT version()"))
                print(f"PostgreSQL Version: {result.fetchone()[0]}")
            elif db_info['is_mysql']:
                result = conn.execute(text("SELECT VERSION()"))
                print(f"MySQL Version: {result.fetchone()[0]}")

    except Exception as e:
        print(f"✗ Connection failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_connection()
```

Run the test:

```bash
python test_db_connection.py
```

## Production Best Practices

### 1. Security

- **Never commit DATABASE_URL to version control**
- Use environment variables or secret management systems
- Enable SSL/TLS for cloud connections
- Use strong passwords
- Restrict database access by IP address

### 2. Connection Pooling

The system automatically handles connection pooling. For high-traffic scenarios, consider:

```python
# Adjust pool size in connection_pool.py if needed
engine = create_engine(
    url,
    echo=echo,
    connect_args=connect_args,
    pool_size=10,        # Default: 5
    max_overflow=20,     # Default: 10
    pool_pre_ping=True,  # Verify connections before using
)
```

### 3. Backups

```bash
# PostgreSQL backup
pg_dump -U greenland_user greenland > backup_$(date +%Y%m%d).sql

# MySQL backup
mysqldump -u greenland_user -p greenland > backup_$(date +%Y%m%d).sql

# Automated backups (add to crontab)
0 2 * * * pg_dump -U greenland_user greenland | gzip > /backups/greenland_$(date +\%Y\%m\%d).sql.gz
```

### 4. Monitoring

Monitor these metrics:

- Connection pool utilization
- Query performance
- Database size
- Lock contention
- Replication lag (if using replicas)

## Troubleshooting

### Connection Refused

```
Could not connect to server: Connection refused
```

**Solutions:**
- Check if database server is running
- Verify host and port are correct
- Check firewall rules
- Ensure database accepts remote connections

### Authentication Failed

```
FATAL: password authentication failed
```

**Solutions:**
- Verify username and password
- Check `pg_hba.conf` (PostgreSQL)
- Ensure user has correct permissions

### SSL Required

```
FATAL: no pg_hba.conf entry for host, SSL off
```

**Solution:**
```bash
# Add sslmode to connection string
export DATABASE_URL="postgresql://user:pass@host/db?sslmode=require"
```

### Driver Not Found

```
No module named 'psycopg2'
```

**Solution:**
```bash
pip install psycopg2-binary  # PostgreSQL
pip install pymysql          # MySQL
```

### Table Already Exists

If you see errors about tables already existing, it means the database has stale schema. Options:

1. **Drop and recreate** (WARNING: destroys data):
   ```bash
   # PostgreSQL
   psql -U greenland_user -d greenland -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

   # MySQL
   mysql -u greenland_user -p greenland -e "DROP DATABASE greenland; CREATE DATABASE greenland;"
   ```

2. **Use migrations** (recommended for production)

## Environment Variable Precedence

The system checks environment variables in this order:

1. **`DATABASE_URL`** - Primary, checked first
2. **`WORDFREQ_DATABASE_URL`** - Alternative/legacy name
3. **`BARSUKAS_DB_PATH`** - SQLite file path
4. **Default** - `src/wordfreq/data/linguistics.sqlite`

For benchmarks:

1. **`BENCHMARKS_DATABASE_URL`**
2. **Default** - `src/benchmarks/schema/benchmarks.db`

## Code Examples

### Using in Python Scripts

```python
#!/usr/bin/env python3
"""Example: Query database regardless of type."""

from wordfreq.storage.connection_pool import get_session
from wordfreq.storage.models.schema import Lemma

# Works with both SQLite and cloud databases
with get_session() as session:
    lemmas = session.query(Lemma).filter_by(
        part_of_speech='noun'
    ).limit(10).all()

    for lemma in lemmas:
        print(f"{lemma.word}: {lemma.definition}")
```

### Checking Database Type

```python
from wordfreq.storage.utils.database_url import is_sqlite, is_cloud_database

if is_sqlite():
    print("Using SQLite - development mode")
else:
    print("Using cloud database - production mode")
```

## References

- [SQLAlchemy Database URLs](https://docs.sqlalchemy.org/en/20/core/engines.html#database-urls)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [MySQL Documentation](https://dev.mysql.com/doc/)
- [Environment Variables Best Practices](https://12factor.net/config)

## Support

If you encounter issues not covered in this guide:

1. Check the application logs
2. Test connection with the test script above
3. Verify environment variables are set correctly
4. Check database server logs
5. Review SQLAlchemy documentation for your specific database

---

**Last Updated:** 2025-12-04
**Version:** 1.0
