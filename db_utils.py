import sqlite3
import csv
import os
import glob
from datetime import datetime, timezone
from typing import List, Dict, Optional
from database import get_db_connection
from config import (
    INITIAL_ADMIN_FULL_NAME, INITIAL_ADMIN_USERNAME,
    INITIAL_ADMIN_EMAIL, INITIAL_ADMIN_PHONE,
    INITIAL_ADMIN_PASSWORD, INITIAL_ADMIN_LANGUAGE, DATA_DIR
)

# ----- Users -----

def get_user(username: str) -> Optional[Dict]:
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    if user:
        return dict(user)
    return None

def add_user(full_name: str, username: str, email: str, phone: str,
             password: str, language: str,
             role: str = "annotator", is_approved: bool = False) -> tuple[bool, str]:
    conn = get_db_connection()
    try:
        # Check for existing email
        existing_email = conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone()
        if existing_email:
            return False, "Email already registered"

        # Check for existing phone
        existing_phone = conn.execute("SELECT 1 FROM users WHERE phone = ?", (phone,)).fetchone()
        if existing_phone:
            return False, "Phone number already registered"

        conn.execute("""
            INSERT INTO users (username, full_name, email, phone, password, language, role, is_approved)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (username, full_name, email, phone, password, language, role, 1 if is_approved else 0))
        conn.commit()
        return True, ""
    except sqlite3.IntegrityError:
        return False, "Username already exists"
    finally:
        conn.close()

def approve_user(username: str) -> bool:
    conn = get_db_connection()
    cursor = conn.execute("UPDATE users SET is_approved = 1 WHERE username = ?", (username,))
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    return updated

def delete_user(username: str) -> bool:
    conn = get_db_connection()
    cursor = conn.execute("DELETE FROM users WHERE username = ?", (username,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted

def update_password(username: str, new_password: str) -> bool:
    conn = get_db_connection()
    cursor = conn.execute("UPDATE users SET password = ? WHERE username = ?", (new_password, username))
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    return updated

def get_username_by_email_phone(email: str, phone: str) -> Optional[str]:
    conn = get_db_connection()
    row = conn.execute("SELECT username FROM users WHERE email = ? AND phone = ?", (email, phone)).fetchone()
    conn.close()
    if row:
        return row["username"]
    return None

def read_users() -> List[Dict]:
    conn = get_db_connection()
    users = conn.execute("SELECT * FROM users").fetchall()
    conn.close()
    # Convert is_approved to string "1" or "0" to match legacy behavior if needed, 
    # but better to keep as int/bool. The template expects "1" for approved check in main.py logic.
    # Let's return dicts and handle type conversion if needed.
    # Actually main.py checks `if u["is_approved"] == "1"` so we should return strings or update main.py.
    # Let's return strings for compatibility for now.
    result = []
    for u in users:
        d = dict(u)
        d["is_approved"] = str(d["is_approved"])
        result.append(d)
    return result

def ensure_initial_admin():
    if not get_user(INITIAL_ADMIN_USERNAME):
        add_user(
            full_name=INITIAL_ADMIN_FULL_NAME,
            username=INITIAL_ADMIN_USERNAME,
            email=INITIAL_ADMIN_EMAIL,
            phone=INITIAL_ADMIN_PHONE,
            password=INITIAL_ADMIN_PASSWORD,
            language=INITIAL_ADMIN_LANGUAGE,
            role="admin",
            is_approved=True
        )
        print(f"Admin user created: {INITIAL_ADMIN_USERNAME} / {INITIAL_ADMIN_PASSWORD}")
    else:
        print(f"Admin user already exists: {INITIAL_ADMIN_USERNAME}")

# ----- Source Sentences -----

def import_source_sentences(upload_path: str, lang: str):
    """
    Reads uploaded CSV and replaces/inserts into source_sentences table for the given language.
    """
    # Validate CSV first
    try:
        with open(upload_path, "r", newline="", encoding="utf-8") as f:
            first_char = f.read(1)
            if not first_char:
                raise ValueError("The uploaded file is empty.")
            f.seek(0)
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                 raise ValueError("The uploaded file is not a valid CSV or has no header.")
            required_cols = ["text", "sentence", "source"]
            if not any(col in reader.fieldnames for col in required_cols):
                raise ValueError(f"CSV must contain one of the following columns: {', '.join(required_cols)}")
            rows = list(reader)
    except UnicodeDecodeError:
        raise ValueError("The uploaded file is not a valid text/CSV file.")
    except csv.Error:
        raise ValueError("The uploaded file is not a valid CSV.")

    if not rows:
        raise ValueError("The uploaded CSV file contains no data rows.")

    conn = get_db_connection()
    try:
        # 1. Get existing texts to avoid duplicates
        existing_texts = set()
        cursor = conn.execute("SELECT text FROM source_sentences WHERE language = ?", (lang,))
        for row in cursor:
            existing_texts.add(row["text"])

        # 2. Get current max ID to continue numbering
        cursor = conn.execute("SELECT MAX(CAST(sentence_id AS INTEGER)) FROM source_sentences WHERE language = ?", (lang,))
        max_id_row = cursor.fetchone()
        current_id = max_id_row[0] if max_id_row and max_id_row[0] is not None else 0

        new_sentences = []
        added_count = 0
        
        for row in rows:
            text = row.get("text") or row.get("sentence") or row.get("source") or ""
            text = text.strip()
            
            if text and text not in existing_texts:
                current_id += 1
                new_sentences.append((lang, str(current_id), text, "unassigned", ""))
                existing_texts.add(text) # Add to set to handle duplicates within the new file itself
                added_count += 1

        if new_sentences:
            conn.executemany("""
                INSERT INTO source_sentences (language, sentence_id, text, status, assigned_to)
                VALUES (?, ?, ?, ?, ?)
            """, new_sentences)
            conn.commit()
        
        return added_count

    finally:
        conn.close()

def pop_next_sentence_for_lang(lang: str, username: str) -> Optional[Dict]:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        conn.execute("BEGIN IMMEDIATE") # Lock the DB for writing

        # 1. Check if user already has an assigned sentence
        row = cursor.execute("""
            SELECT * FROM source_sentences 
            WHERE language = ? AND status = 'assigned' AND assigned_to = ?
        """, (lang, username)).fetchone()

        if row:
            conn.commit()
            d = dict(row)
            d["id"] = d["sentence_id"]
            return d

        # 2. Find first unassigned sentence
        row = cursor.execute("""
            SELECT * FROM source_sentences 
            WHERE language = ? AND status = 'unassigned'
            ORDER BY CAST(sentence_id AS INTEGER) ASC
            LIMIT 1
        """, (lang,)).fetchone()

        if row:
            # Assign it
            cursor.execute("""
                UPDATE source_sentences 
                SET status = 'assigned', assigned_to = ? 
                WHERE language = ? AND sentence_id = ?
            """, (username, lang, row["sentence_id"]))
            conn.commit()
            # Return the updated row
            updated_row = dict(row)
            updated_row["status"] = "assigned"
            updated_row["assigned_to"] = username
            updated_row["id"] = updated_row["sentence_id"]
            return updated_row
        
        conn.commit()
        return None
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def mark_sentence_completed(lang: str, sentence_id: str):
    conn = get_db_connection()
    conn.execute("""
        UPDATE source_sentences 
        SET status = 'completed' 
        WHERE language = ? AND sentence_id = ?
    """, (lang, sentence_id))
    conn.commit()
    conn.close()

def unassign_sentence(lang: str, sentence_id: str):
    conn = get_db_connection()
    conn.execute("""
        UPDATE source_sentences 
        SET status = 'unassigned', assigned_to = '' 
        WHERE language = ? AND sentence_id = ?
    """, (lang, sentence_id))
    conn.commit()
    conn.close()

def count_remaining_sentences(lang: str) -> int:
    conn = get_db_connection()
    count = conn.execute("""
        SELECT COUNT(*) FROM source_sentences 
        WHERE language = ? AND status != 'completed'
    """, (lang,)).fetchone()[0]
    conn.close()
    return count

def source_sentences_exist(lang: str) -> bool:
    conn = get_db_connection()
    exists = conn.execute("SELECT 1 FROM source_sentences WHERE language = ? LIMIT 1", (lang,)).fetchone()
    conn.close()
    return exists is not None

    conn.close()
    return exists is not None

def get_language_stats() -> List[Dict]:
    conn = get_db_connection()
    rows = conn.execute("""
        SELECT 
            language,
            COUNT(*) as total,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
            SUM(CASE WHEN status != 'completed' THEN 1 ELSE 0 END) as remaining
        FROM source_sentences
        GROUP BY language
    """).fetchall()
    conn.close()
    
    stats = []
    for r in rows:
        stats.append({
            "language": r["language"],
            "source_filename": f"to_be_translated_to_{r['language']}.csv",
            "total": r["total"],
            "completed": r["completed"],
            "remaining": r["remaining"]
        })
    return stats

# ----- Translations -----

def append_translation(sentence_id: str, source_text: str, translated_text: str, username: str, lang: str):
    submitted_at = datetime.now(timezone.utc).isoformat()
    conn = get_db_connection()
    conn.execute("""
        INSERT INTO translations (language, sentence_id, source_text, translated_text, username, submitted_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (lang, sentence_id, source_text, translated_text, username, submitted_at))
    conn.commit()
    conn.close()

def get_annotator_stats(username: str) -> Dict:
    conn = get_db_connection()
    count = conn.execute("SELECT COUNT(*) FROM translations WHERE username = ?", (username,)).fetchone()[0]
    conn.close()
    return {
        "count": count,
        "reward": count * 2
    }

def get_translation_file_details() -> List[Dict]:
    conn = get_db_connection()
    rows = conn.execute("""
        SELECT language, COUNT(*) as count 
        FROM translations 
        GROUP BY language
    """).fetchall()
    conn.close()
    
    details = []
    for r in rows:
        details.append({
            "language": r["language"],
            "filename": f"translations_{r['language']}.csv", # Virtual filename
            "count": r["count"]
        })
    return details

def get_translations_csv_for_lang(lang: str) -> str:
    """
    Generates a CSV file from the DB for the given language and returns the path.
    """
    conn = get_db_connection()
    rows = conn.execute("""
        SELECT sentence_id as id, source_text, translated_text, username, submitted_at 
        FROM translations 
        WHERE language = ?
    """, (lang,)).fetchall()
    conn.close()

    filename = f"translations_{lang}.csv"
    path = os.path.join(DATA_DIR, filename)
    
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "source_text", "translated_text", "username", "submitted_at"])
        writer.writeheader()
        for r in rows:
            writer.writerow(dict(r))
            
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "source_text", "translated_text", "username", "submitted_at"])
        writer.writeheader()
        for r in rows:
            writer.writerow(dict(r))
            
    return path

def migrate_csv_to_db():
    """
    Migrates data from existing CSV files to SQLite.
    Only runs if the users table is empty.
    """
    conn = get_db_connection()
    user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    
    if user_count > 0:
        conn.close()
        return # DB already populated

    print("Migrating CSV data to SQLite...")
    
    # 1. Migrate Users
    from config import USERS_CSV, SOURCE_DIR
    if os.path.exists(USERS_CSV):
        with open(USERS_CSV, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    conn.execute("""
                        INSERT INTO users (username, full_name, email, phone, password, language, role, is_approved)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        row["username"], row["full_name"], row["email"], row["phone"],
                        row["password"], row["language"], row["role"], 
                        1 if row["is_approved"] == "1" else 0
                    ))
                except sqlite3.IntegrityError:
                    pass # Skip duplicates

    # 2. Migrate Source Sentences
    pattern = os.path.join(SOURCE_DIR, "to_be_translated_to_*.csv")
    for path in glob.glob(pattern):
        filename = os.path.basename(path)
        lang = filename.replace("to_be_translated_to_", "").replace(".csv", "")
        
        with open(path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    conn.execute("""
                        INSERT INTO source_sentences (language, sentence_id, text, status, assigned_to)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        lang, row["id"], row["text"], 
                        row.get("status", "unassigned"), row.get("assigned_to", "")
                    ))
                except sqlite3.IntegrityError:
                    pass

    # 3. Migrate Translations
    # Read from both translations_*.csv and old TRANSLATIONS_CSV
    from config import TRANSLATIONS_CSV
    
    all_translations = []
    
    # Per-language files
    pattern = os.path.join(DATA_DIR, "translations_*.csv")
    for path in glob.glob(pattern):
        filename = os.path.basename(path)
        lang = filename.replace("translations_", "").replace(".csv", "")
        with open(path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                row["language"] = lang
                all_translations.append(row)
                
    # Old single file (if exists)
    if os.path.exists(TRANSLATIONS_CSV):
        with open(TRANSLATIONS_CSV, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Try to infer language from user? Or just skip?
                # The old format didn't have language in CSV, but we can look up user language.
                # For simplicity, let's assume we can skip or look up user.
                # Actually, we can look up the user in the DB now!
                username = row["username"]
                user = conn.execute("SELECT language FROM users WHERE username = ?", (username,)).fetchone()
                if user:
                    row["language"] = user["language"]
                    all_translations.append(row)

    for t in all_translations:
        if "language" in t:
            conn.execute("""
                INSERT INTO translations (language, sentence_id, source_text, translated_text, username, submitted_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                t["language"], t["id"], t["source_text"], t["translated_text"], 
                t["username"], t["submitted_at"]
            ))

    conn.commit()
    conn.close()
    print("Migration complete.")
