"""Deterministic SQLite benchmark database shared by API handlers."""
import sqlite3
from datetime import datetime, timedelta

ROW_TARGET = 15000

def connect():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA temp_store=MEMORY")
    db.executescript("""
    CREATE TABLE merchant_accounts (
      merchant_id INTEGER PRIMARY KEY, merchant_name TEXT NOT NULL,
      account_status TEXT NOT NULL, region TEXT NOT NULL, created_at TEXT NOT NULL
    );
    CREATE TABLE mpesa_transactions (
      transaction_id INTEGER PRIMARY KEY, merchant_id INTEGER NOT NULL,
      amount REAL NOT NULL, status TEXT NOT NULL, transaction_date TEXT NOT NULL,
      reference TEXT NOT NULL, channel TEXT NOT NULL,
      FOREIGN KEY(merchant_id) REFERENCES merchant_accounts(merchant_id)
    );
    CREATE TABLE api_request_logs (
      log_id INTEGER PRIMARY KEY, merchant_id INTEGER NOT NULL,
      endpoint TEXT NOT NULL, response_code INTEGER NOT NULL,
      duration_ms REAL NOT NULL, created_at TEXT NOT NULL
    );
    """)
    base = datetime(2025, 1, 1)
    merchants = [(i, f"Merchant {i:04d}", ("active","active","active","suspended")[i % 4],
                  ("Nairobi","Mombasa","Kisumu","Meru")[i % 4],
                  (base - timedelta(days=i % 900)).isoformat(timespec="seconds"))
                 for i in range(1, 501)]
    db.executemany("INSERT INTO merchant_accounts VALUES (?,?,?,?,?)", merchants)
    tx = []
    logs = []
    for i in range(1, 12001):
        day = base + timedelta(minutes=i * 19)
        merchant = (i % 500) + 1
        tx.append((i, merchant, round(80 + ((i * 37) % 95000) / 10, 2),
                   ("SUCCESS","SUCCESS","PENDING","FAILED")[i % 4],
                   day.isoformat(timespec="seconds"), f"QX{i:09d}",
                   ("STK_PUSH","PAYBILL","TILL")[i % 3]))
    for i in range(1, 3001):
        day = base + timedelta(minutes=i * 71)
        logs.append((i, (i % 500) + 1, ("/v1/checkout","/v1/balance","/v1/webhook")[i % 3],
                     (200,200,201,400,500)[i % 5], float(12 + (i * 13) % 1800),
                     day.isoformat(timespec="seconds")))
    db.executemany("INSERT INTO mpesa_transactions VALUES (?,?,?,?,?,?,?)", tx)
    db.executemany("INSERT INTO api_request_logs VALUES (?,?,?,?,?,?)", logs)
    db.commit()
    return db

def schema_snapshot(db):
    tables = []
    for name in ("mpesa_transactions","merchant_accounts","api_request_logs"):
        cols = [dict(cid=r["cid"], name=r["name"], type=r["type"], notnull=bool(r["notnull"]), pk=bool(r["pk"]))
                for r in db.execute(f"PRAGMA table_info({name})")]
        indexes = [dict(name=r["name"], unique=bool(r["unique"]), origin=r["origin"])
                   for r in db.execute(f"PRAGMA index_list({name})")]
        count = db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        tables.append(dict(name=name, columns=cols, rowCount=count, indexes=indexes))
    return tables
