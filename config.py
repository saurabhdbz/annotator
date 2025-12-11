# config.py
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

USERS_CSV = os.path.join(DATA_DIR, "users.csv")
SOURCE_CSV = os.path.join(DATA_DIR, "source_sentences.csv")
TRANSLATIONS_CSV = os.path.join(DATA_DIR, "translations.csv")
SOURCE_DIR = os.path.join(DATA_DIR, "sources")
os.makedirs(SOURCE_DIR, exist_ok=True)


# Session secret key (change it to something random in real use)
SESSION_SECRET_KEY = "super-secret-key-change-me"

SUPPORTED_LANG_CODES = [
    "mizo",  # Mizo
    "khasi",  # Khasi
]


# -------- Initial Admin Details -------- #
INITIAL_ADMIN_FULL_NAME = "System Administrator"
INITIAL_ADMIN_USERNAME = "admin"
INITIAL_ADMIN_EMAIL = "admin@example.com"
INITIAL_ADMIN_PHONE = "0000000000"
INITIAL_ADMIN_PASSWORD = "admin123"
INITIAL_ADMIN_LANGUAGE = "NA"   # Admin does not translate