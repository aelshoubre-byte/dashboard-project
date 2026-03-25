import sqlite3
import os
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "database.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn

def init_db():
    conn = get_db()
    cur  = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT    NOT NULL,
            last_name  TEXT    NOT NULL,
            email      TEXT    UNIQUE NOT NULL,
            password   TEXT    NOT NULL,
            avatar_url TEXT    DEFAULT NULL,
            role       TEXT    DEFAULT 'user',
            created_at TEXT    DEFAULT (datetime('now'))
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            name       TEXT    NOT NULL,
            category   TEXT    NOT NULL
                           CHECK(category IN
                               ('vegetables','meat','dairy','frozen','canned','others')),
            qty        REAL    NOT NULL DEFAULT 1,
            unit       TEXT    NOT NULL DEFAULT 'pcs',
            exp_date   TEXT    NOT NULL,
            barcode    TEXT    DEFAULT NULL,
            notes      TEXT    DEFAULT NULL,
            image_url  TEXT    DEFAULT NULL,
            added_date TEXT    DEFAULT (date('now')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS removed_products (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL,
            name         TEXT    NOT NULL,
            category     TEXT    NOT NULL,
            qty          REAL,
            unit         TEXT,
            exp_date     TEXT,
            reason       TEXT    DEFAULT 'removed'
                                 CHECK(reason IN ('expired','consumed','removed','donated')),
            removed_date TEXT    DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sensor_readings (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            temperature REAL,
            humidity    REAL,
            recorded_at TEXT DEFAULT (datetime('now'))
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sensor_state (
            id          INTEGER PRIMARY KEY DEFAULT 1,
            temperature REAL    DEFAULT NULL,
            humidity    REAL    DEFAULT NULL,
            connected   INTEGER DEFAULT 0,
            mode        TEXT    DEFAULT 'disconnected',
            updated_at  TEXT    DEFAULT (datetime('now'))
        )
    """)
    cur.execute("INSERT OR IGNORE INTO sensor_state (id) VALUES (1)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            title       TEXT    NOT NULL,
            body        TEXT    NOT NULL,
            type        TEXT    DEFAULT 'info',
            priority    TEXT    DEFAULT 'normal',
            is_read     INTEGER DEFAULT 0,
            product_id  INTEGER DEFAULT NULL,
            device_id   INTEGER DEFAULT NULL,
            created_at  TEXT    DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id             INTEGER UNIQUE NOT NULL,
            expiry_warning_days INTEGER DEFAULT 3,
            temp_min            REAL    DEFAULT 0.0,
            temp_max            REAL    DEFAULT 8.0,
            humidity_min        REAL    DEFAULT 30.0,
            humidity_max        REAL    DEFAULT 80.0,
            push_notifications  INTEGER DEFAULT 1,
            email_notifications INTEGER DEFAULT 0,
            language            TEXT    DEFAULT 'en',
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS fcm_tokens (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            token       TEXT    NOT NULL,
            device_type TEXT    DEFAULT 'mobile',
            created_at  TEXT    DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    conn.commit()
    conn.close()
    print("Database ready —", DB_PATH)
