"""SQLite保存層。呼び出しごとに別の接続を開きます（スレッドセーフ）。"""
import os
import secrets
import sqlite3
from datetime import datetime, timedelta

import numpy as np
from werkzeug.security import generate_password_hash

import config
import logic

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS groups(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
  start_time TEXT NOT NULL DEFAULT '09:00', grace_min INTEGER NOT NULL DEFAULT 0,
  end_time TEXT NOT NULL DEFAULT '18:00', workdays TEXT NOT NULL DEFAULT '1,2,3,4,5');
CREATE TABLE IF NOT EXISTS people(id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'student',
  group_id INTEGER REFERENCES groups(id), chat_id TEXT DEFAULT '', active INTEGER NOT NULL DEFAULT 1, created TEXT);
CREATE TABLE IF NOT EXISTS embeddings(id INTEGER PRIMARY KEY AUTOINCREMENT,
  person_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE, vec BLOB NOT NULL, created TEXT);
CREATE TABLE IF NOT EXISTS attendance(person_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
  date TEXT NOT NULL, check_in TEXT, check_out TEXT, status TEXT NOT NULL, score REAL, snapshot TEXT,
  source TEXT DEFAULT 'auto', note TEXT DEFAULT '', PRIMARY KEY(person_id, date));
CREATE TABLE IF NOT EXISTS unknown_events(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, kind TEXT, snapshot TEXT, score REAL);
CREATE TABLE IF NOT EXISTS holidays(date TEXT PRIMARY KEY, note TEXT DEFAULT '');
CREATE INDEX IF NOT EXISTS ix_att_date ON attendance(date);
"""

_fernet = None
if os.environ.get("FACEATTEND_KEY"):          # 任意: 生体データの暗号化
    from cryptography.fernet import Fernet
    _fernet = Fernet(os.environ["FACEATTEND_KEY"].encode())


def _c():
    c = sqlite3.connect(config.DB_PATH, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c


def q(sql, args=()):
    c = _c()
    try:
        return [dict(r) for r in c.execute(sql, args).fetchall()]
    finally:
        c.close()


def one(sql, args=()):
    r = q(sql, args)
    return r[0] if r else None


def x(sql, args=()):
    c = _c()
    try:
        cur = c.execute(sql, args)
        c.commit()
        return cur.lastrowid
    finally:
        c.close()


def now_s():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------- 初期化 / メタ情報 ----------
def init():
    for d in (config.DATA, config.SNAP_DIR, config.UNK_DIR):
        d.mkdir(parents=True, exist_ok=True)
    c = _c()
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript(SCHEMA)
    c.commit()
    c.close()
    if not one("SELECT id FROM groups LIMIT 1"):
        x("INSERT INTO groups(name) VALUES('標準グループ')")
    if not meta_get("admin_hash"):
        pw = os.environ.get("FACEATTEND_ADMIN_PASSWORD") or secrets.token_urlsafe(8)
        meta_set("admin_hash", generate_password_hash(pw))
        if not os.environ.get("FACEATTEND_ADMIN_PASSWORD"):
            (config.DATA / "ADMIN_PASSWORD.txt").write_text(pw + "\n", encoding="utf-8")
            print(f"\n*** 管理者パスワード（初回起動）: {pw}  (data/ADMIN_PASSWORD.txt) ***\n")


def meta_get(k, default=None):
    r = one("SELECT v FROM meta WHERE k=?", (k,))
    return r["v"] if r else default


def meta_set(k, v):
    x("INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v))


def secret_key():
    k = meta_get("secret_key")
    if not k:
        k = secrets.token_hex(32)
        meta_set("secret_key", k)
    return k


# ---------- グループ / 休日 ----------
def groups():
    return q("SELECT * FROM groups ORDER BY name")


def groups_map():
    return {g["id"]: g for g in groups()}


def save_group(gid, name, start, grace, end, wdays):
    if gid:
        x("UPDATE groups SET name=?,start_time=?,grace_min=?,end_time=?,workdays=? WHERE id=?",
          (name, start, grace, end, wdays, gid))
        return gid
    return x("INSERT INTO groups(name,start_time,grace_min,end_time,workdays) VALUES(?,?,?,?,?)",
             (name, start, grace, end, wdays))


def delete_group(gid):
    if one("SELECT id FROM people WHERE group_id=? AND active=1", (gid,)):
        return False
    x("UPDATE people SET group_id=NULL WHERE group_id=?", (gid,))
    x("DELETE FROM groups WHERE id=?", (gid,))
    return True


def holidays():
    return {r["date"]: r["note"] for r in q("SELECT * FROM holidays ORDER BY date")}


# ---------- 登録者 / 顔データ ----------
def person(pid):
    return one("SELECT * FROM people WHERE id=?", (pid,))


def people(group=None, active=True):
    sql, a = "SELECT p.*, (SELECT COUNT(*) FROM embeddings e WHERE e.person_id=p.id) AS faces FROM people p WHERE 1=1", []
    if active:
        sql += " AND active=1"
    if group:
        sql += " AND group_id=?"
        a.append(group)
    return q(sql + " ORDER BY name", a)


def upsert_person(pid, name, role, group_id, chat_id):
    x("""INSERT INTO people(id,name,role,group_id,chat_id,active,created) VALUES(?,?,?,?,?,1,?)
         ON CONFLICT(id) DO UPDATE SET name=excluded.name, role=excluded.role,
         group_id=excluded.group_id, chat_id=excluded.chat_id, active=1""",
      (pid, name, role, group_id, chat_id, now_s()))


def remove_person(pid, hard=False):
    x("DELETE FROM embeddings WHERE person_id=?", (pid,))
    if hard:
        x("DELETE FROM people WHERE id=?", (pid,))
    else:
        x("UPDATE people SET active=0 WHERE id=?", (pid,))


def _enc(vec):
    b = np.asarray(vec, np.float32).tobytes()
    return _fernet.encrypt(b) if _fernet else b


def _dec(b):
    return np.frombuffer(_fernet.decrypt(b) if _fernet else b, dtype=np.float32).copy()


def add_embedding(pid, vec):
    x("INSERT INTO embeddings(person_id,vec,created) VALUES(?,?,?)", (pid, _enc(vec), now_s()))
    extra = one("SELECT COUNT(*) n FROM embeddings WHERE person_id=?", (pid,))["n"] - config.MAX_EMB_PER_PERSON
    if extra > 0:   # 最も古いものを削除
        x("DELETE FROM embeddings WHERE id IN (SELECT id FROM embeddings WHERE person_id=? ORDER BY id LIMIT ?)", (pid, extra))


def clear_embeddings(pid):
    x("DELETE FROM embeddings WHERE person_id=?", (pid,))


def all_embeddings():
    rows = q("SELECT e.person_id, e.vec FROM embeddings e JOIN people p ON p.id=e.person_id WHERE p.active=1")
    return [(r["person_id"], _dec(r["vec"])) for r in rows]


def names():
    return {r["id"]: r["name"] for r in q("SELECT id,name FROM people WHERE active=1")}


# ---------- 出席 ----------
def att_get(pid, d):
    return one("SELECT * FROM attendance WHERE person_id=? AND date=?", (pid, d))


def att_range(d1, d2, group=None):
    sql = "SELECT a.* FROM attendance a JOIN people p ON p.id=a.person_id WHERE a.date BETWEEN ? AND ?"
    args = [d1, d2]
    if group:
        sql += " AND p.group_id=?"
        args.append(group)
    return {(r["person_id"], r["date"]): r for r in q(sql, args)}


def punch(pid, now, score=None):
    """入室を1日1回記録します。戻り値: ('in'|'already', status)"""
    p = person(pid)
    g = groups_map().get(p["group_id"]) or logic.DEFAULT_GROUP
    d, t = now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S")
    status = logic.arrival_status(g, now)
    rec = att_get(pid, d)
    if rec is None:
        x("INSERT INTO attendance(person_id,date,check_in,status,score,source) VALUES(?,?,?,?,?,'auto')",
          (pid, d, t, status, score))
        return "in", status
    if not rec["check_in"]:          # 手動で登録されていたが、実際に来た
        new = rec["status"] if rec["status"] == "excused" else status
        x("UPDATE attendance SET check_in=?, status=?, score=?, source='auto' WHERE person_id=? AND date=?",
          (t, new, score, pid, d))
        return "in", new
    return "already", rec["status"]


def set_snapshot(pid, d, path):
    x("UPDATE attendance SET snapshot=? WHERE person_id=? AND date=?", (path, pid, d))


def mark(pid, d, status, note=""):
    if status == "clear":
        x("DELETE FROM attendance WHERE person_id=? AND date=?", (pid, d))
        return
    x("""INSERT INTO attendance(person_id,date,status,source,note) VALUES(?,?,?,'manual',?)
         ON CONFLICT(person_id,date) DO UPDATE SET status=excluded.status, note=excluded.note""",
      (pid, d, status, note))


# ---------- 未登録者 ----------
def add_unknown(kind, snapshot, score):
    x("INSERT INTO unknown_events(ts,kind,snapshot,score) VALUES(?,?,?,?)", (now_s(), kind, snapshot, score))


def unknown_list(limit=100):
    return q("SELECT * FROM unknown_events ORDER BY id DESC LIMIT ?", (limit,))


def purge_old():
    """RETENTION_DAYS より古い画像を削除します（プライバシー保護）。"""
    cutoff = datetime.now() - timedelta(days=config.RETENTION_DAYS)
    for root in (config.SNAP_DIR, config.UNK_DIR):
        for f in root.rglob("*.jpg"):
            try:
                if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                    f.unlink()
            except OSError:
                pass
