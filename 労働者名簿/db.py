import sqlite3

# 現スキーマ（列定義）＝ここが正
COLUMNS = [
    ("name", "TEXT"),
    ("name_kana", "TEXT"),
    ("sex", "TEXT"),

    ("birth_date", "TEXT"),
    ("address", "TEXT"),
    ("phone", "TEXT"),

    ("job_type", "TEXT"),
    ("hire_date", "TEXT"),
    ("hire_story", "TEXT"),

    ("history", "TEXT"),
    ("license", "TEXT"),

    ("my_number", "TEXT"),
    ("health_ins", "TEXT"),
    ("pension_base", "TEXT"),
    ("welfare_pension", "TEXT"),
    ("employment_ins", "TEXT"),

    ("leave_date", "TEXT"),
    ("leave_reason", "TEXT"),
    ("remarks", "TEXT"),
]
COL_NAMES = [c for c, _ in COLUMNS]


def _connect(db_path: str):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    return con


def init_db(db_path: str):
    """
    1) テーブルが無ければ作る
    2) 既存DBなら不足列を自動追加（ALTER TABLE）
    """
    con = _connect(db_path)
    cur = con.cursor()

    cols_sql = ",\n        ".join([f"{name} {typ}" for name, typ in COLUMNS])
    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        {cols_sql}
    )
    """)
    con.commit()
    con.close()

    ensure_columns(db_path)


def ensure_columns(db_path: str):
    con = _connect(db_path)
    cur = con.cursor()

    cur.execute("PRAGMA table_info(employees)")
    existing = {r["name"] for r in cur.fetchall()}

    for name, typ in COLUMNS:
        if name not in existing:
            cur.execute(f"ALTER TABLE employees ADD COLUMN {name} {typ}")

    con.commit()
    con.close()


def upsert_employee(db_path: str, e: dict) -> int:
    """
    e["id"] がある → UPDATE
    e["id"] がない → INSERT（自動採番）
    """
    con = _connect(db_path)
    cur = con.cursor()

    values = [e.get(c, "") for c in COL_NAMES]

    if e.get("id"):
        sets = ",".join(f"{c}=?" for c in COL_NAMES)
        cur.execute(f"UPDATE employees SET {sets} WHERE id=?", values + [e["id"]])
        emp_id = int(e["id"])
    else:
        qs = ",".join("?" for _ in COL_NAMES)
        cur.execute(f"INSERT INTO employees ({','.join(COL_NAMES)}) VALUES ({qs})", values)
        emp_id = cur.lastrowid

    con.commit()
    con.close()
    return emp_id


def insert_employee_with_id(db_path: str, emp_id: int, e: dict) -> int:
    """
    IDを指定して新規作成（ID重複なら例外）
    """
    con = _connect(db_path)
    cur = con.cursor()

    cur.execute("SELECT 1 FROM employees WHERE id=?", (emp_id,))
    if cur.fetchone():
        con.close()
        raise ValueError(f"そのIDは既に使われています: {emp_id}")

    values = [e.get(c, "") for c in COL_NAMES]
    qs = ",".join("?" for _ in COL_NAMES)

    cur.execute(
        f"INSERT INTO employees (id, {','.join(COL_NAMES)}) VALUES (?, {qs})",
        [emp_id] + values
    )

    con.commit()
    con.close()
    return emp_id


def change_employee_id(db_path: str, old_id: int, new_id: int):
    """
    既存レコードのIDを変更（new_idが既に存在したら例外）
    """
    if old_id == new_id:
        return

    con = _connect(db_path)
    cur = con.cursor()

    cur.execute("SELECT 1 FROM employees WHERE id=?", (old_id,))
    if not cur.fetchone():
        con.close()
        raise ValueError(f"旧IDが見つかりません: {old_id}")

    cur.execute("SELECT 1 FROM employees WHERE id=?", (new_id,))
    if cur.fetchone():
        con.close()
        raise ValueError(f"新IDは既に使われています: {new_id}")

    cur.execute("UPDATE employees SET id=? WHERE id=?", (new_id, old_id))
    con.commit()
    con.close()


def list_employees(
    db_path: str,
    q: str,
    sort_key: str = "id",
    sort_dir: str = "ASC",
    columns: list[str] | None = None,
):
    """
    一覧（検索＋ソート＋必要列だけSELECT）
    - sort_key: "id" / "job_type"
    - sort_dir: "ASC" / "DESC"
    - columns: 例 ["id","name"] や ["id","name","phone"] など
    """
    allowed_cols = {"id"} | set(COL_NAMES)
    if not columns:
        columns = ["id", "name"]
    for c in columns:
        if c not in allowed_cols:
            raise ValueError(f"invalid column: {c}")

    sort_key = (sort_key or "id").strip()
    sort_dir = (sort_dir or "ASC").strip().upper()

    if sort_key not in {"id", "job_type"}:
        sort_key = "id"
    if sort_dir not in {"ASC", "DESC"}:
        sort_dir = "ASC"

    # 業務種類ソートは安定化のため第二キーにidを入れる
    if sort_key == "job_type":
        order_sql = f"job_type {sort_dir}, id ASC"
    else:
        order_sql = f"id {sort_dir}"

    select_sql = ", ".join(columns)

    con = _connect(db_path)
    cur = con.cursor()

    q = (q or "").strip()
    if q:
        like = f"%{q}%"
        cur.execute(f"""
        SELECT {select_sql}
        FROM employees
        WHERE CAST(id AS TEXT) LIKE ?
           OR name LIKE ?
           OR phone LIKE ?
        ORDER BY {order_sql}
        """, (like, like, like))
    else:
        cur.execute(f"""
        SELECT {select_sql}
        FROM employees
        ORDER BY {order_sql}
        """)

    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return rows


def get_employee(db_path: str, emp_id: int):
    con = _connect(db_path)
    cur = con.cursor()
    cur.execute("SELECT * FROM employees WHERE id=?", (emp_id,))
    r0 = cur.fetchone()
    con.close()
    return dict(r0) if r0 else None


def delete_employee(db_path: str, emp_id: int):
    con = _connect(db_path)
    cur = con.cursor()
    cur.execute("DELETE FROM employees WHERE id=?", (emp_id,))
    con.commit()
    con.close()