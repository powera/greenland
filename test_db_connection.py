#!/usr/bin/env python3
"""
Test database connection for Greenland project.

This script tests the database connection and displays information about
the configured database (SQLite or cloud database).

Usage:
    python test_db_connection.py

Environment Variables:
    DATABASE_URL - Database connection URL (optional)
    WORDFREQ_DATABASE_URL - Alternative database URL (optional)
    BARSUKAS_DB_PATH - Path to SQLite database (optional)
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from sqlalchemy import create_engine, text
from wordfreq.storage.utils.database_url import (
    get_database_url,
    parse_database_url,
    is_sqlite,
    is_cloud_database,
)


def print_section(title: str):
    """Print a section header."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def test_connection():
    """Test database connection and print information."""

    print_section("Greenland Database Connection Test")

    # Check environment variables
    print("\n📋 Environment Variables:")
    env_vars = [
        "DATABASE_URL",
        "WORDFREQ_DATABASE_URL",
        "BARSUKAS_DB_PATH",
        "BENCHMARKS_DATABASE_URL",
    ]
    for var in env_vars:
        value = os.environ.get(var)
        if value:
            # Mask password in URL
            if "://" in value and "@" in value:
                parts = value.split("@")
                if "://" in parts[0]:
                    proto_user = parts[0].split("://")
                    if ":" in proto_user[1]:
                        user = proto_user[1].split(":")[0]
                        masked = f"{proto_user[0]}://{user}:****@{parts[1]}"
                        print(f"  ✓ {var} = {masked}")
                    else:
                        print(f"  ✓ {var} = {value}")
                else:
                    print(f"  ✓ {var} = {value}")
            else:
                print(f"  ✓ {var} = {value}")
        else:
            print(f"  ✗ {var} = (not set)")

    # Get database URL
    print_section("Database Configuration")
    try:
        db_url = get_database_url()
        print(f"\n🔗 Active Database URL:")

        # Mask password
        display_url = db_url
        if "://" in db_url and "@" in db_url:
            parts = db_url.split("@")
            if "://" in parts[0]:
                proto_user = parts[0].split("://")
                if ":" in proto_user[1]:
                    user = proto_user[1].split(":")[0]
                    display_url = f"{proto_user[0]}://{user}:****@{parts[1]}"

        print(f"  {display_url}")

        # Parse URL
        db_info = parse_database_url(db_url)
        print(f"\n📊 Database Information:")
        print(f"  Type: {db_info['scheme']}")
        print(f"  Is SQLite: {db_info['is_sqlite']}")

        if db_info["is_sqlite"]:
            print(f"  Database File: {db_info['database']}")
            # Check if file exists
            if Path(db_info["database"]).exists():
                size = Path(db_info["database"]).stat().st_size
                print(f"  File Size: {size:,} bytes ({size / 1024 / 1024:.2f} MB)")
            else:
                print(f"  ⚠️  File does not exist yet (will be created on first use)")
        else:
            print(f"  Is PostgreSQL: {db_info['is_postgres']}")
            print(f"  Is MySQL: {db_info['is_mysql']}")
            print(f"  Host: {db_info['hostname']}")
            print(f"  Port: {db_info['port']}")
            print(f"  Database: {db_info['database']}")
            print(f"  Username: {db_info['username']}")

    except Exception as e:
        print(f"\n❌ Error getting database configuration: {e}")
        return False

    # Test connection
    print_section("Connection Test")
    print("\n🔌 Testing connection...")

    try:
        engine = create_engine(db_url)

        with engine.connect() as conn:
            # Test basic query
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
            print("✅ Connection successful!")

            # Get database version
            if db_info["is_postgres"]:
                result = conn.execute(text("SELECT version()"))
                version = result.fetchone()[0]
                print(f"\n📦 PostgreSQL Version:")
                print(f"  {version.split(',')[0]}")

            elif db_info["is_mysql"]:
                result = conn.execute(text("SELECT VERSION()"))
                version = result.fetchone()[0]
                print(f"\n📦 MySQL Version:")
                print(f"  {version}")

            elif db_info["is_sqlite"]:
                result = conn.execute(text("SELECT sqlite_version()"))
                version = result.fetchone()[0]
                print(f"\n📦 SQLite Version:")
                print(f"  {version}")

            # Check if tables exist
            if db_info["is_sqlite"]:
                result = conn.execute(
                    text(
                        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                    )
                )
            elif db_info["is_postgres"]:
                result = conn.execute(
                    text(
                        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
                    )
                )
            elif db_info["is_mysql"]:
                result = conn.execute(text("SHOW TABLES"))
            else:
                result = None

            if result:
                tables = [row[0] for row in result]
                if tables:
                    print(f"\n📋 Tables ({len(tables)}):")
                    for table in tables[:10]:  # Show first 10 tables
                        print(f"  - {table}")
                    if len(tables) > 10:
                        print(f"  ... and {len(tables) - 10} more")
                else:
                    print(
                        "\n⚠️  No tables found (database is empty - will be created on first use)"
                    )

        print_section("Summary")
        print("\n✅ Database connection test PASSED!")
        print("\nYou can now run the application:")
        print("  cd src/barsukas")
        print("  ./launch.sh")
        print()
        return True

    except Exception as e:
        print(f"\n❌ Connection FAILED!")
        print(f"\nError details:")
        print(f"  {type(e).__name__}: {e}")

        print(f"\n💡 Troubleshooting tips:")
        if "No module named" in str(e):
            module_name = str(e).split("'")[1]
            print(f"  1. Install database driver: pip install {module_name}")
            if "psycopg" in module_name:
                print(f"     Alternative: pip install psycopg2-binary")
            elif "pymysql" in module_name:
                print(f"     Alternative: pip install PyMySQL")

        elif "Connection refused" in str(e):
            print(f"  1. Check if database server is running")
            print(f"  2. Verify host and port are correct")
            print(f"  3. Check firewall rules")

        elif "authentication failed" in str(e):
            print(f"  1. Verify username and password")
            print(f"  2. Check user permissions")

        elif "SSL" in str(e):
            print(f"  1. Add sslmode to connection string:")
            print(f"     DATABASE_URL=postgresql://user:pass@host/db?sslmode=require")

        print(f"\n📖 For more help, see: docs/cloud_database_setup.md")
        print()
        return False


if __name__ == "__main__":
    try:
        success = test_connection()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
