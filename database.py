import os
import sqlite3
from pathlib import Path
import pandas as pd
from sqlalchemy import text

from config import DATABASE_PATH, DATA_DIR
from backend.database import engine, init_db, DATABASE_URL

# ------------------------------------------------------------
# DATABASE ABSTRACTION LAYER (PostgreSQL & SQLite)
# ------------------------------------------------------------
IS_POSTGRES = DATABASE_URL.startswith("postgresql")


def get_connection():
    """
    Create a raw connection to the active database (PostgreSQL or SQLite).
    """
    if IS_POSTGRES:
        return engine.raw_connection()

    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(
        DATABASE_PATH,
        check_same_thread=False
    )
    return connection


def import_csv_to_sqlite():
    """
    Import/seed all data into the database (supports PostgreSQL and SQLite).
    """
    # Trigger SQLAlchemy-based initialization and seed
    init_db()

    # Also sync CSVs directly to tables if needed
    csv_files = {
        "customers": DATA_DIR / "customers.csv",
        "plans": DATA_DIR / "plans.csv",
        "subscriptions": DATA_DIR / "subscriptions.csv",
        "usage": DATA_DIR / "usage.csv",
        "bills": DATA_DIR / "bills.csv",
        "network": DATA_DIR / "network.csv",
        "tickets": DATA_DIR / "tickets.csv",
        "outages": DATA_DIR / "outages.csv",
    }

    conn = get_connection()
    try:
        for table_name, csv_path in csv_files.items():
            if not csv_path.exists():
                continue
            df = pd.read_csv(csv_path)
            # Use SQLAlchemy engine for writing if PostgreSQL
            target_bind = engine if IS_POSTGRES else conn
            df.to_sql(
                table_name,
                target_bind,
                if_exists="replace" if not IS_POSTGRES else "append",
                index=False,
            )
            print(f"Imported {table_name}: {len(df)} records")
        if hasattr(conn, "commit"):
            conn.commit()
    finally:
        conn.close()


def query_database(query: str, params=()):
    """
    Execute SELECT query and return a pandas DataFrame.
    Automatically handles parameter style differences between SQLite (?) and PostgreSQL (%s).
    """
    if IS_POSTGRES:
        # PostgreSQL psycopg2 uses %s instead of ?
        pg_query = query.replace("?", "%s")
        # Handle SQLite-specific date functions if present
        pg_query = pg_query.replace("date('now', '-7 day')", "(CURRENT_DATE - INTERVAL '7 days')")
        with engine.connect() as conn:
            df = pd.read_sql_query(text(pg_query), conn, params=dict(enumerate(params)) if isinstance(params, (list, tuple)) else params)
            return df

    connection = get_connection()
    try:
        df = pd.read_sql_query(query, connection, params=params)
        return df
    finally:
        connection.close()


def execute_database(query: str, params=()):
    """
    Execute INSERT / UPDATE / DELETE command.
    Automatically handles parameter style differences between SQLite (?) and PostgreSQL (%s).
    """
    if IS_POSTGRES:
        pg_query = query.replace("?", "%s")
        with engine.begin() as conn:
            result = conn.execute(text(pg_query), params)
            return getattr(result, "lastrowid", None)

    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(query, params)
        connection.commit()
        return cursor.lastrowid
    finally:
        connection.close()