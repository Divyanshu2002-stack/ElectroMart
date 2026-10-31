import os, re, sqlite3, secrets
from functools import wraps
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash

# --- NEW FOR SUPABASE ---
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except:
    psycopg2 = None

app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "shop.db"
UPLOAD_FOLDER = BASE_DIR / "static" / "uploads"
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
PAYMENT_FOLDER = BASE_DIR / "static" / "uploads" / "payments"
PAYMENT_FOLDER.mkdir(parents=True, exist_ok=True)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "electromart_final_secret_2024")

DATABASE_URL = os.environ.get("DATABASE_URL", "")
IS_POSTGRES = DATABASE_URL.startswith("postgres")


# --- UNIFIED DB WRAPPER ---
class DBCursorWrapper:
    def __init__(self, cursor, is_pg):
        self.cur = cursor
        self.is_pg = is_pg

    def fetchone(self):
        row = self.cur.fetchone()
        return row

    def fetchall(self):
        return self.cur.fetchall()


class DBWrapper:
    def __init__(self, conn, is_pg):
        self.conn = conn
        self.is_pg = is_pg
        self._cursor = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is None:
                self.conn.commit()
        except:
            pass
        try:
            self.conn.close()
        except:
            pass
        return False

    def _adapt(self, q):
        if not self.is_pg:
            return q
        # ? -> %s and sqlite specific -> postgres
        q = q.replace("?", "%s")
        q = q.replace("AUTOINCREMENT", "")
        q = q.replace("INTEGER PRIMARY KEY", "SERIAL PRIMARY KEY")
        q = q.replace("INSERT OR IGNORE", "INSERT")
        # handle INSERT ... will be converted to ON CONFLICT DO NOTHING in init
        return q

    def execute(self, query, params=()):
        q = self._adapt(query)
        # Handle INSERT OR IGNORE conversion
        if self.is_pg and "INSERT INTO" in q and "IGNORE" not in query and "ON CONFLICT" not in q:
            # only for settings defaults we need ON CONFLICT
            if "INTO settings" in q or "INTO users" in q or "INTO wishlist" in q:
                q = q.replace("INSERT INTO", "INSERT INTO", 1)
                # add ON CONFLICT DO NOTHING if not present
                if "ON CONFLICT" not in q and "settings (key,value)" in query or "settings (key, value)" in q.lower() or "key" in q:
                    pass  # handled separately
        if self.is_pg:
            cur = self.conn.cursor(cursor_factory=RealDictCursor)
            # For INSERT OR IGNORE -> ON CONFLICT DO NOTHING
            if "INSERT OR IGNORE" in query:
                q = query.replace("INSERT OR IGNORE", "INSERT").replace("?", "%s")
                if "settings" in q:
                    q += " ON CONFLICT (key) DO NOTHING"
                elif "users" in q and "username" in q:
                    q += " ON CONFLICT (username) DO NOTHING"
                elif "wishlist" in q:
                    q += " ON CONFLICT DO NOTHING"
                else:
                    q += " ON CONFLICT DO NOTHING"
            cur.execute(q, params)
            self._cursor = cur
            return DBCursorWrapper(cur, True)
        else:
            cur = self.conn.cursor()
            cur.execute(query, params)
            self._cursor = cur
            return DBCursorWrapper(cur, False)

    def executemany(self, query, seq):
        q = self._adapt(query)
        if self.is_pg:
            cur = self.conn.cursor()
            cur.executemany(q, seq)
        else:
            cur = self.conn.cursor()
            cur.executemany(query, seq)

    def commit(self):
        try:
            self.conn.commit()
        except:
            pass


def get_db():
    if IS_POSTGRES and psycopg2:
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        return DBWrapper(conn, True)
    else:
        db = sqlite3.connect(DATABASE, timeout=15)
        db.row_factory = sqlite3.Row
        return DBWrapper(db, False)


def init_db():
    with get_db() as db:
        # Postgres compatible tables
        if IS_POSTGRES:
            db.execute(
                """CREATE TABLE IF NOT EXISTS products (id SERIAL PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL, price REAL NOT NULL DEFAULT 0, description TEXT DEFAULT '', stock INTEGER NOT NULL DEFAULT 0, image TEXT DEFAULT '', video TEXT DEFAULT '', created_at TIMESTAMP DEFAULT NOW())""")
            db.execute(
                """CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, username TEXT NOT NULL UNIQUE, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, role TEXT NOT NULL, created_at TIMESTAMP DEFAULT NOW())""")
            db.execute(
                """CREATE TABLE IF NOT EXISTS orders (id SERIAL PRIMARY KEY, user_id INTEGER, product_id INTEGER, quantity INTEGER, total_price REAL, status TEXT DEFAULT 'Placed', created_at TIMESTAMP DEFAULT NOW())""")
            db.execute(
                """CREATE TABLE IF NOT EXISTS wishlist (id SERIAL PRIMARY KEY, user_id INTEGER, product_id INTEGER, UNIQUE(user_id, product_id))""")
            db.execute(
                """CREATE TABLE IF NOT EXISTS khata (id SERIAL PRIMARY KEY, customer_name TEXT NOT NULL, mobile TEXT DEFAULT '', address TEXT DEFAULT '', items TEXT DEFAULT '', total_amount REAL DEFAULT 0, paid_amount REAL DEFAULT 0, balance REAL DEFAULT 0, status TEXT DEFAULT 'Udhar', created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW())""")
            db.execute("""CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)""")
        else:
            db.execute(
                """CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, category TEXT NOT NULL, price REAL NOT NULL DEFAULT 0, description TEXT DEFAULT '', stock INTEGER NOT NULL DEFAULT 0, image TEXT DEFAULT '', video TEXT DEFAULT '', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            db.execute(
                """CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('owner', 'customer')), created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            db.execute(
                """CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, product_id INTEGER, quantity INTEGER, total_price REAL, status TEXT DEFAULT 'Placed', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            db.execute(
                """CREATE TABLE IF NOT EXISTS wishlist (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, product_id INTEGER, UNIQUE(user_id, product_id))""")
            db.execute(
                """CREATE TABLE IF NOT EXISTS khata (id INTEGER PRIMARY KEY AUTOINCREMENT, customer_name TEXT NOT NULL, mobile TEXT DEFAULT '', address TEXT DEFAULT '', items TEXT DEFAULT '', total_amount REAL DEFAULT 0, paid_amount REAL DEFAULT 0, balance REAL DEFAULT 0, status TEXT DEFAULT 'Udhar', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            db.execute("""CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)""")

        # add missing columns (postgres me IF NOT EXISTS se handle)
        for col in ["address TEXT DEFAULT ''", "delivery_charge REAL DEFAULT 0", "pincode TEXT DEFAULT ''",
                    "payment_method TEXT DEFAULT 'COD'", "payment_screenshot TEXT DEFAULT ''",
                    "payment_status TEXT DEFAULT 'Pending'"]:
            try:
                col_name = col.split()[0]
                if IS_POSTGRES:
                    db.execute(f"ALTER TABLE orders ADD COLUMN IF NOT EXISTS {col}")
                else:
                    db.execute(f"ALTER TABLE orders ADD COLUMN {col}")
            except:
                pass
        for col in ["cost_price REAL DEFAULT 0", "video TEXT DEFAULT ''"]:
            try:
                if IS_POSTGRES:
                    db.execute(f"ALTER TABLE products ADD COLUMN IF NOT EXISTS {col}")
                else:
                    db.execute(f"ALTER TABLE products ADD COLUMN {col}")
            except:
                pass

        count = db.execute("SELECT COUNT(*) as c FROM products").fetchone()
        cnt = count['c'] if isinstance(count, dict) else count[0] if count else 0
        if IS_POSTGRES:
            cnt = count['c'] if count else 0
        else:
            cnt = count[0] if count else 0

        if cnt == 0:
            db.executemany(
                "INSERT INTO products (name, category, price, cost_price, description, stock, image) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    ("LED Bulb 9W", "Lights & LEDs", 120, 80, "Philips Energy Saving", 50, ""),
                    ("Inverter Pipe 1 inch", "Pipes & Fittings", 45, 30, "Heavy duty pipe", 100, ""),
                    ("Lenter Pipe", "Pipes & Fittings", 65, 40, "Lenter pipe strong", 3, ""),
                    ("Copper Wire Roll", "Wires & Cables", 650, 500, "1.5mm Copper Wire", 20, ""),
                    ("Ceiling Fan", "Fans & Coolers", 1850, 1500, "High Speed Fan", 10, "")
                ])

        defaults = {
            "store_name": "ElectroMart",
            "owner_display_name": "ElectroMart Owner - 9667311958@ybl",
            "upi_id": UPI_ID,
            "upi_name": UPI_NAME,
            "free_delivery_limit": str(FREE_DELIVERY_LIMIT),
            "delivery_charge": str(DELIVERY_CHARGE),
            "allowed_pincodes": ",".join(ALLOWED_PINCODES),
            "qr_image": ""
        }
        for k, v in defaults.items():
            try:
                if IS_POSTGRES:
                    db.execute("INSERT INTO settings (key,value) VALUES (%s,%s) ON CONFLICT (key) DO NOTHING", (k, v))
                else:
                    db.execute("INSERT OR IGNORE INTO settings (key,value) VALUES (?,?)", (k, v))
            except:
                pass
        db.commit()


CATEGORIES = ["Pipes & Fittings", "Wires & Cables", "Switches & Fittings", "Lights & LEDs", "Fancy & Pencil Lights",
              "Fans & Coolers", "Home Appliances", "Tools & Materials"]
ALLOWED_PINCODES = ["248001", "248002", "248003", "248005", "248006", "248007", "248009", "248171"]
FREE_DELIVERY_LIMIT = 500
DELIVERY_CHARGE = 40
UPI_ID = "9667311958@ybl"
UPI_NAME = "ElectroMart Dehradun"