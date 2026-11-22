"""GET /api/schema — initialize and describe the seeded benchmark database."""
from http.server import BaseHTTPRequestHandler
import json
from _db import connect, schema_snapshot

PRESETS = [
 {"id":"merchant-ledger","name":"Unindexed Merchant Ledger Lookup","severity":"critical",
  "description":"Filters a merchant ledger by merchant and date, then sorts newest-first.",
  "sql":"SELECT transaction_id, merchant_id, amount, status, transaction_date FROM mpesa_transactions WHERE merchant_id = 42 AND transaction_date >= '2025-06-01T00:00:00' ORDER BY transaction_date DESC LIMIT 100;"},
 {"id":"status-date","name":"Full-Scan Status + Date Range Filter","severity":"high",
  "description":"Combines a low-selectivity status filter with a date range.",
  "sql":"SELECT transaction_id, amount, transaction_date FROM mpesa_transactions WHERE status = 'FAILED' AND transaction_date >= '2025-08-01T00:00:00' AND transaction_date < '2025-10-01T00:00:00' ORDER BY transaction_date DESC;"},
 {"id":"n-plus-one","name":"N+1 Subquery Aggregation","severity":"medium",
  "description":"Correlated per-merchant aggregation repeatedly probes the transaction table.",
  "sql":"SELECT m.merchant_id, m.merchant_name, (SELECT COUNT(*) FROM mpesa_transactions t WHERE t.merchant_id = m.merchant_id) AS tx_count FROM merchant_accounts m WHERE m.account_status = 'active' ORDER BY tx_count DESC LIMIT 25;"}
]

class handler(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.split("?")[0] != "/api/schema":
            return self._send(404, {"error":"Not found"})
        db = connect()
        tables = schema_snapshot(db)
        total = sum(t["rowCount"] for t in tables)
        indexes = sum(len(t["indexes"]) for t in tables)
        db.close()
        self._send(200, {"engine":"SQLite 3","seededRows":total,"activeIndexCount":indexes,
                         "tables":tables,"presets":PRESETS})
