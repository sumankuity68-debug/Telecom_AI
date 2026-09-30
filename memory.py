import sqlite3
from pathlib import Path
from datetime import datetime


# ============================================================
# DATABASE LOCATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DB_PATH = (
    BASE_DIR
    / "database"
    / "telecom.db"
)


# ============================================================
# INITIALIZE MEMORY TABLE
# ============================================================

def initialize_memory():

    DB_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )


    connection = sqlite3.connect(
        DB_PATH
    )

    cursor = connection.cursor()


    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation_memory (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            customer_id TEXT NOT NULL,

            role TEXT NOT NULL,

            content TEXT NOT NULL,

            source TEXT DEFAULT 'text',

            created_at TEXT NOT NULL

        )
        """
    )


    connection.commit()

    connection.close()


# ============================================================
# SAVE MESSAGE
# ============================================================

def save_message(
    customer_id,
    role,
    content,
    source="text"
):

    if not customer_id:
        return


    if not content:
        return


    initialize_memory()


    connection = sqlite3.connect(
        DB_PATH
    )

    cursor = connection.cursor()


    cursor.execute(
        """
        INSERT INTO conversation_memory
        (
            customer_id,
            role,
            content,
            source,
            created_at
        )

        VALUES (?, ?, ?, ?, ?)
        """,

        (
            customer_id,
            role,
            content,
            source,
            datetime.now().isoformat()
        )
    )


    connection.commit()

    connection.close()


# ============================================================
# GET RECENT MEMORY
# ============================================================

def get_recent_memory(
    customer_id,
    limit=10
):

    if not customer_id:

        return []


    initialize_memory()


    connection = sqlite3.connect(
        DB_PATH
    )

    cursor = connection.cursor()


    cursor.execute(
        """
        SELECT
            role,
            content,
            source,
            created_at

        FROM conversation_memory

        WHERE customer_id = ?

        ORDER BY id DESC

        LIMIT ?
        """,

        (
            customer_id,
            limit
        )
    )


    rows = cursor.fetchall()

    connection.close()


    rows.reverse()


    memory = []


    for row in rows:

        memory.append(
            {
                "role": row[0],
                "content": row[1],
                "source": row[2],
                "created_at": row[3]
            }
        )


    return memory


# ============================================================
# CLEAR MEMORY
# ============================================================

def clear_memory(customer_id):

    if not customer_id:
        return


    initialize_memory()


    connection = sqlite3.connect(
        DB_PATH
    )

    cursor = connection.cursor()


    cursor.execute(
        """
        DELETE FROM conversation_memory
        WHERE customer_id = ?
        """,
        (customer_id,)
    )


    connection.commit()

    connection.close()