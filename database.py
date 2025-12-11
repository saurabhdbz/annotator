import sqlite3
import os
from config import DATA_DIR

DB_PATH = os.path.join(DATA_DIR, "annotator.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Enable WAL mode for concurrency
    cursor.execute("PRAGMA journal_mode=WAL;")

    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT NOT NULL,
            password TEXT NOT NULL,
            language TEXT NOT NULL,
            role TEXT NOT NULL,
            is_approved INTEGER NOT NULL DEFAULT 0
        )
    """)

    # Source sentences table
    # We use a composite primary key (language, id) or just an auto-incrementing ID and index language/original_id
    # To keep it simple and close to CSV structure where ID was per-file:
    # We will store (language, sentence_id) as unique.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS source_sentences (
            language TEXT NOT NULL,
            sentence_id TEXT NOT NULL,
            text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'unassigned',
            assigned_to TEXT DEFAULT '',
            PRIMARY KEY (language, sentence_id)
        )
    """)

    # Translations table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS translations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            language TEXT NOT NULL,
            sentence_id TEXT NOT NULL,
            source_text TEXT NOT NULL,
            translated_text TEXT NOT NULL,
            username TEXT NOT NULL,
            submitted_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()
