"""POST /api/explain — safe read-only query plan and benchmark endpoint."""
from http.server import BaseHTTPRequestHandler
import json
import re
import time
from _db import connect

MAX_SQL = 12000
FORBIDDEN = re.compile(r"\b(INSERT|UPDATE|DELETE|REPLACE|CREATE|DROP|ALTER|ATTACH|DETACH|VACUUM|PRAGMA|REINDEX|TRIGGER)\b", re.I)
TABLE_COLUMNS = {
 "mpesa_transactions":{"merchant_id","status","transaction_date","amount","transaction_id"},
 "merchant_accounts":{"merchant_id","account_status","region","created_at"},
 "api_request_logs":{"merchant_id","response_code","created_at","endpoint","duration_ms"}
}

def validate_sql(sql):
    if not isinstance(sql, str) or not sql.strip() or len(sql) > MAX_SQL:
        raise ValueError("Provide a SQL statement between 1 and 12,000 characters.")
    clean = re.sub(r"/\*[\s\S]*?\*/|--[^\n]*", " ", sql).strip()
    if not re.match(r"^(SELECT|WITH)\b", clean, re.I):
        raise ValueError("Only read-only SELECT or WITH queries are allowed.")
    if ";" in clean.rstrip(";"):
        raise ValueError("Only one SQL statement is allowed.")
    if FORBIDDEN.search(clean):
        raise ValueError("This statement contains a prohibited SQL operation.")
    if re.search(r"\b(load_extension|writefile|readfile)\s*\(", clean, re.I):
        raise ValueError("File and extension functions are not allowed.")
    return clean.rstrip(";")

def recommendations(sql):
    found = []
    for table, cols in TABLE_COLUMNS.items():
        pattern = re.compile(r"\b" + table + r"\b", re.I)
        if not pattern.search(sql): continue
        candidates = []
        for clause in re.findall(r"\b(?:WHERE|JOIN|ON|ORDER BY|GROUP BY)\b([\s\S]*?)(?=\b(?:WHERE|JOIN|ON|ORDER BY|GROUP BY|LIMIT|HAVING)\b|$)", sql, re.I):
            for col in cols:
                if re.search(r"\b" + col + r"\b", clause, re.I) and col not in candidates:
                    candidates.append(col)
        if candidates:
            name = "idx_" + table + "_" + "_".join(candidates[:2])
            found.append({"table":table,"columns":candidates[:2],
                          "sql":f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({', '.join(candidates[:2])});",
                          "reason":"Supports filtering, joining, or ordering on the referenced columns."})
    return found

def run(db, sql):
    plan = [dict(id=r[0], parent=r[1], detail=r[3]) for r in db.execute("EXPLAIN QUERY PLAN " + sql)]
    started = time.perf_counter()
    cursor = db.execute(sql)
    rows = cursor.fetchall()
    elapsed = (time.perf_counter() - started) * 1000
    returned = len(rows)
    scan_count = sum(1 for p in plan if "SCAN " in p["detail"].upper())
    search_count = sum(1 for p in plan if "SEARCH " in p["detail"].upper() and "INDEX" in p["detail"].upper())
    temp_sort = any("TEMP B-TREE" in p["detail"].upper() for p in plan)
    nodes = []
    for p in plan:
        detail = p["detail"]
        kind = "fast" if "SEARCH " in detail.upper() and "INDEX" in detail.upper() else ("warning" if "TEMP B-TREE" in detail.upper() else ("slow" if "SCAN " in detail.upper() else "neutral"))
        nodes.append({**p,"kind":kind,"explanation":
          "Indexed lookup narrows the rows SQLite visits." if kind=="fast" else
          "SQLite scans rows; a selective index may reduce work." if kind=="slow" else
          "SQLite uses a temporary structure for sorting or grouping." if kind=="warning" else
          "SQLite performs this plan operation."})
    return {"executionMs":round(elapsed,3),"rowsReturned":returned,"truncated":returned>500,
            "rowsScanned":"not exposed by SQLite EXPLAIN QUERY PLAN",
            "scanNodes":scan_count,"indexedSearchNodes":search_count,"tempBtree":temp_sort,
            "plan":nodes,"sampleRows":[dict(r) for r in rows[:20]]}

class handler(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        body=json.dumps(payload, default=str).encode()
        self.send_response(code); self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","no-store"); self.send_header("Content-Length",str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def do_POST(self):
        if self.path.split("?")[0] != "/api/explain": return self._send(404,{"error":"Not found"})
        try:
            length=int(self.headers.get("Content-Length","0"))
            if length > 20000: return self._send(413,{"error":"Request body too large."})
            payload=json.loads(self.rfile.read(length) or b"{}")
            sql=validate_sql(payload.get("sql"))
            db=connect()
            before=run(db,sql)
            advice=recommendations(sql)
            applied=[]
            custom=payload.get("customIndexSql","")
            statements=[]
            if payload.get("applySuggestedIndexes"): statements.extend(x["sql"] for x in advice)
            if custom:
                if not isinstance(custom,str) or len(custom)>3000: raise ValueError("Custom index SQL is too long.")
                statements.append(custom.strip())
            for statement in statements:
                if not re.match(r"^CREATE\s+INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?[A-Za-z_][A-Za-z0-9_]*\s+ON\s+[A-Za-z_][A-Za-z0-9_]*\s*\([A-Za-z0-9_,\s]+\)\s*;?$",statement,re.I):
                    raise ValueError("Only a single CREATE INDEX statement on benchmark tables is accepted.")
                match=re.search(r"\bON\s+(\w+)\s*\(([^)]+)\)",statement,re.I)
                table=match.group(1).lower(); cols=[c.strip().lower() for c in match.group(2).split(",")]
                if table not in TABLE_COLUMNS or any(c not in TABLE_COLUMNS[table] for c in cols):
                    raise ValueError("Index references an unknown benchmark table or column.")
                db.execute(statement); applied.append(statement)
            after=run(db,sql) if applied else None
            indexes=[]
            for table in TABLE_COLUMNS:
                for index_row in db.execute(f"PRAGMA index_list({table})"):
                    index_name = index_row[1]
                    index_columns = [column[2] for column in db.execute(f"PRAGMA index_info({index_name})")]
                    indexes.append(dict(table=table, name=index_name, columns=index_columns))
            db.close()
            speedup=round(before["executionMs"]/max(after["executionMs"],0.001),2) if after else None
            self._send(200,{"before":before,"after":after,"recommendations":advice,
                            "appliedIndexes":applied,"indexes":indexes,"speedup":speedup})
        except ValueError as exc: self._send(400,{"error":str(exc)})
        except json.JSONDecodeError: self._send(400,{"error":"Request body must be valid JSON."})
        except Exception as exc: self._send(500,{"error":"Query execution failed: "+str(exc)})
