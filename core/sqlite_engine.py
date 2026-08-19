import os
import csv
import json
import time
import sqlite3
import threading
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass

@dataclass
class QueryResult:
    columns: List[str]
    rows: List[Tuple[Any, ...]]
    total_rows: int
    rowcount: int
    execution_time_ms: float
    error: Optional[str] = None
    is_select: bool = True
    lastrowid: Optional[int] = None

class SQLiteEngine:
    """Lightweight SQLite Engine supporting schema inspection, metrics, and export."""

    MAGIC_HEADER = b"SQLite format 3\x00"

    @classmethod
    def is_sqlite_file(cls, filepath: str) -> bool:
        """Determines if a file is a valid SQLite 3 database by checking its 16-byte magic header."""
        if not filepath or not os.path.isfile(filepath):
            return False
        try:
            with open(filepath, "rb") as f:
                header = f.read(16)
                return header == cls.MAGIC_HEADER
        except Exception:
            return False

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()
        if db_path:
            self.connect(db_path)

    def connect(self, db_path: str) -> bool:
        """Connects to a SQLite database file."""
        self.close()
        self.db_path = db_path
        try:
            self.conn = sqlite3.connect(db_path, check_same_thread=False, timeout=10.0)
            self.conn.row_factory = sqlite3.Row
            with self.conn:
                self.conn.execute("PRAGMA foreign_keys = ON;")
            return True
        except Exception as e:
            self.conn = None
            raise e

    def checkpoint(self):
        """Flushes and commits all pending transactions and WAL journals into the main database file."""
        if self.conn:
            with self._lock:
                try:
                    self.conn.commit()
                    self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                except Exception:
                    pass

    def close(self):
        """Closes the current database connection."""
        with self._lock:
            if self.conn:
                try:
                    self.conn.close()
                except Exception:
                    pass
                self.conn = None

    def interrupt(self):
        """Interrupts any active query execution on the connection."""
        if self.conn:
            try:
                self.conn.interrupt()
            except Exception:
                pass

    def get_schema(self) -> Dict[str, Any]:
        """Returns structured metadata of tables, views, columns, indexes, and row counts."""
        if not self.conn:
            return {"tables": {}, "views": {}}

        schema = {"tables": {}, "views": {}}

        with self._lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute("""
                    SELECT type, name, sql 
                    FROM sqlite_master 
                    WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%'
                    ORDER BY name ASC;
                """)
                objects = cursor.fetchall()

                for obj_type, name, sql_ddl in objects:
                    cursor.execute(f'PRAGMA table_info("{name}");')
                    cols_raw = cursor.fetchall()
                    columns = []
                    for col in cols_raw:
                        columns.append({
                            "cid": col[0],
                            "name": col[1],
                            "type": col[2] if col[2] else "ANY",
                            "notnull": bool(col[3]),
                            "default": col[4],
                            "pk": bool(col[5])
                        })

                    indexes = []
                    row_count = 0
                    if obj_type == "table":
                        try:
                            cursor.execute(f'PRAGMA index_list("{name}");')
                            for idx in cursor.fetchall():
                                indexes.append({
                                    "name": idx[1],
                                    "unique": bool(idx[2])
                                })
                        except Exception:
                            pass

                        try:
                            cursor.execute(f'SELECT COUNT(*) FROM "{name}";')
                            cnt = cursor.fetchone()
                            if cnt:
                                row_count = cnt[0]
                        except Exception:
                            row_count = 0

                    item_info = {
                        "name": name,
                        "ddl": sql_ddl or "",
                        "columns": columns,
                        "indexes": indexes,
                        "row_count": row_count
                    }

                    if obj_type == "table":
                        schema["tables"][name] = item_info
                    else:
                        schema["views"][name] = item_info

                return schema
            except Exception as e:
                return {"tables": {}, "views": {}, "error": str(e)}

    def execute_query(self, sql: str, params: Any = None, max_rows: int = 1000) -> QueryResult:
        """Executes a SQL query string with execution timing, optional parameter binding, and row metrics."""
        if not self.conn:
            return QueryResult([], [], 0, 0, 0.0, error="No database connected.")

        if isinstance(params, int):
            max_rows = params
            params = None

        sql_trimmed = sql.strip().rstrip(";")
        if not sql_trimmed:
            return QueryResult([], [], 0, 0, 0.0)

        first_word = sql_trimmed.split()[0].upper() if sql_trimmed.split() else ""
        is_select = first_word in ("SELECT", "PRAGMA", "EXPLAIN", "WITH")

        start_time = time.perf_counter()
        try:
            with self._lock:
                cursor = self.conn.cursor()
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)

                if is_select and cursor.description:
                    columns = [desc[0] for desc in cursor.description]
                    fetched_rows = cursor.fetchmany(max_rows)
                    rows = [tuple(r) for r in fetched_rows]
                    total_rows = len(rows)
                    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                    return QueryResult(
                        columns=columns,
                        rows=rows,
                        total_rows=total_rows,
                        rowcount=total_rows,
                        execution_time_ms=elapsed_ms,
                        is_select=True
                    )
                else:
                    self.conn.commit()
                    rowcount = cursor.rowcount
                    lastrowid = cursor.lastrowid
                    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                    return QueryResult(
                        columns=[],
                        rows=[],
                        total_rows=0,
                        rowcount=rowcount,
                        execution_time_ms=elapsed_ms,
                        is_select=False,
                        lastrowid=lastrowid
                    )
        except sqlite3.OperationalError as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return QueryResult([], [], 0, 0, elapsed_ms, error=str(e), is_select=is_select)
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return QueryResult([], [], 0, 0, elapsed_ms, error=str(e), is_select=is_select)

    def export_to_csv(self, sql_or_table: str, output_path: str) -> Tuple[bool, str]:
        """Exports query results or a table to a CSV file."""
        if not self.conn:
            return False, "No database connection."

        sql = sql_or_table if " " in sql_or_table.strip() else f'SELECT * FROM "{sql_or_table}";'
        try:
            with self._lock:
                cursor = self.conn.cursor()
                cursor.execute(sql)
                if not cursor.description:
                    return False, "Query produced no columns to export."

                headers = [d[0] for d in cursor.description]
                with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.writer(f)
                    writer.writerow(headers)
                    while True:
                        rows = cursor.fetchmany(1000)
                        if not rows:
                            break
                        writer.writerows([[str(v) if v is not None else "" for v in r] for r in rows])

            return True, f"Exported successfully to {output_path}"
        except Exception as e:
            return False, str(e)

    def export_to_json(self, sql_or_table: str, output_path: str) -> Tuple[bool, str]:
        """Exports query results or a table to a JSON file."""
        if not self.conn:
            return False, "No database connection."

        sql = sql_or_table if " " in sql_or_table.strip() else f'SELECT * FROM "{sql_or_table}";'
        try:
            with self._lock:
                cursor = self.conn.cursor()
                cursor.execute(sql)
                if not cursor.description:
                    return False, "Query produced no columns to export."

                headers = [d[0] for d in cursor.description]
                records = []
                while True:
                    rows = cursor.fetchmany(1000)
                    if not rows:
                        break
                    for r in rows:
                        records.append(dict(zip(headers, [v for v in r])))

                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(records, f, indent=2, ensure_ascii=False)

            return True, f"Exported {len(records)} records to {output_path}"
        except Exception as e:
            return False, str(e)
