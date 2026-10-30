"""顔認証出席システム - ドア用画面(キオスク) + 管理画面。   起動: python app.py"""
import csv
import io
import re
import threading
import time
from datetime import date, datetime, timedelta
from functools import wraps

import cv2
import numpy as np
from flask import (Flask, Response, abort, jsonify, redirect, render_template, request,
                   send_from_directory, session)
from werkzeug.security import check_password_hash, generate_password_hash

import config
import db
import logic
import notify
from engine import Gallery, quality_ok
from liveness import Liveness
from pipeline import Pipeline
from textdraw import put_text, text_size


def create_app(engine, camera):
    db.init()
    db.purge_old()
    mname = getattr(engine, "model_name", None)
    if mname:   # 異なるモデルの顔データは互換性がありません
        saved, has = db.meta_get("model"), db.one("SELECT 1 AS x FROM embeddings LIMIT 1")
        if saved and saved != mname and has:
            raise SystemExit(f"\nエラー: 顔データベースは '{saved}' モデルで作成されていますが、現在は '{mname}' が選択されています。\n"
                             f"  1) FACEATTEND_MODEL={saved} を指定して起動する、または\n"
                             f"  2) python tools.py switch-model {mname}  (顔データが消えるため再登録が必要です)\n")
        if not saved or not has:
            db.meta_set("model", mname)
    gallery = Gallery()
    gallery.reload()
    cam_ok = camera.start()
    live = Liveness(camera.has_depth)
    pl = Pipeline(camera, engine, gallery, live)
    if cam_ok or camera.source != "auto":
        pl.start()
    threading.Thread(target=notify.absent_loop, daemon=True).start()

    app = Flask(__name__)
    app.secret_key = db.secret_key()
    app.config.update(SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_HTTPONLY=True,
                      MAX_CONTENT_LENGTH=8 * 1024 * 1024, TEMPLATES_AUTO_RELOAD=False)
    app.pl, app.gallery, app.camera = pl, gallery, camera
    attempts = {}

    # ---------- ヘルパー ----------
    def err(code, status=400, **kw):
        return jsonify(error=code, **kw), status

    def admin(f):
        @wraps(f)
        def w(*a, **k):
            if not session.get("adm"):
                return err("auth", 401) if request.path.startswith("/api") else redirect("/login")
            return f(*a, **k)
        return w

    @app.before_request
    def csrf():
        if request.method in ("POST", "PUT", "DELETE") and request.path.startswith("/api") \
                and request.headers.get("X-Requested-With") != "FaceAttendance":
            return err("csrf", 403)

    def parse_date(s, default):
        try:
            return datetime.strptime(s, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return default

    def group_arg():
        g = request.args.get("group", "")
        return int(g) if g.isdigit() else None

    # ---------- ドア画面 ----------
    @app.get("/")
    def kiosk():
        return render_template("kiosk.html", lang=config.LANG)

    @app.get("/api/status")
    def status():
        return jsonify(camera=camera.mode, camera_ok=camera.ok, liveness=live.mode, fps=round(pl.fps, 1),
                       people=len(gallery.pids), device=getattr(engine, "device", "?"), lang=config.LANG)

    @app.get("/api/events")
    def events():
        evs, last = pl.events_after(request.args.get("after", -1, int))
        return jsonify(events=evs, last=last)

    def draw(img, view):
        for box, label, color in view:
            x1, y1, x2, y2 = box
            cv2.rectangle(img, (x1, y1), (x2, y2), color, 3)
            tw, th = text_size(label, 20)
            top = max(y1 - th - 14, 0)
            cv2.rectangle(img, (x1, top), (x1 + tw + 10, top + th + 12), color, -1)
            put_text(img, label, (x1 + 5, top + 5), size=20, color=(255, 255, 255))

    def placeholder(text):
        img = np.zeros((480, 640, 3), np.uint8)
        put_text(img, text, (20, 225), size=22, color=(60, 60, 230))
        return cv2.imencode(".jpg", img)[1].tobytes()

    @app.get("/video_feed")
    def video_feed():
        def gen():
            last = -1
            while True:
                t0 = time.time()
                frame, depth, seq = camera.read()
                if frame is None:
                    data = placeholder("カメラが準備できていません")
                    time.sleep(0.4)
                elif seq == last:
                    time.sleep(0.01)
                    continue
                else:
                    last = seq
                    img = frame.copy()
                    draw(img, list(pl.view))
                    if config.SHOW_DEPTH and depth is not None:
                        cmap = cv2.applyColorMap(cv2.convertScaleAbs(depth, alpha=0.03), cv2.COLORMAP_JET)
                        img = np.hstack((img, cmap))
                    data = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 75])[1].tobytes()
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + data + b"\r\n"
                time.sleep(max(0, 0.04 - (time.time() - t0)))   # 約25fpsに制限
        return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

    # ---------- ログイン ----------
    @app.route("/login", methods=["GET", "POST"])
    def login():
        msg = ""
        if request.method == "POST":
            ip = request.remote_addr
            recent = [t for t in attempts.get(ip, []) if time.time() - t < 60]
            if len(recent) >= 5:
                msg = "too_many"
            elif check_password_hash(db.meta_get("admin_hash"), request.form.get("password", "")):
                session["adm"] = True
                return redirect("/admin")
            else:
                recent.append(time.time())
                msg = "bad"
            attempts[ip] = recent
        return render_template("login.html", lang=config.LANG, msg=msg)

    @app.get("/logout")
    def logout():
        session.clear()
        return redirect("/login")

    @app.get("/admin")
    @admin
    def admin_page():
        return render_template("admin.html", lang=config.LANG)

    # ---------- グループ / 休日 ----------
    @app.get("/api/groups")
    @admin
    def groups_get():
        return jsonify(groups=db.groups(), holidays=db.holidays())

    @app.post("/api/groups")
    @admin
    def groups_post():
        j = request.get_json(force=True)
        name = str(j.get("name", "")).strip()[:60]
        try:
            logic.hm(j.get("start_time")), logic.hm(j.get("end_time"))
            grace = max(0, min(240, int(j.get("grace_min", 0))))
            wd = ",".join(sorted({str(int(x)) for x in str(j.get("workdays", "")).split(",") if x.strip() and 1 <= int(x) <= 7}))
        except (ValueError, TypeError, AttributeError):
            return err("bad_input")
        if not name:
            return err("bad_input")
        try:
            gid = db.save_group(j.get("id"), name, j["start_time"], grace, j["end_time"], wd)
        except Exception:
            return err("duplicate_name", 409)
        return jsonify(ok=True, id=gid)

    @app.delete("/api/groups/<int:gid>")
    @admin
    def groups_del(gid):
        return jsonify(ok=True) if db.delete_group(gid) else err("group_not_empty", 409)

    @app.post("/api/holidays")
    @admin
    def hol_post():
        j = request.get_json(force=True)
        if parse_date(j.get("date"), None) is None:
            return err("bad_input")
        db.x("INSERT INTO holidays(date,note) VALUES(?,?) ON CONFLICT(date) DO UPDATE SET note=excluded.note",
             (j["date"], str(j.get("note", ""))[:100]))
        return jsonify(ok=True)

    @app.delete("/api/holidays/<d>")
    @admin
    def hol_del(d):
        db.x("DELETE FROM holidays WHERE date=?", (d,))
        return jsonify(ok=True)

    # ---------- 登録者 ----------
    @app.get("/api/people")
    @admin
    def people_get():
        gm = db.groups_map()
        rows = db.people(group=group_arg())
        for r in rows:
            r["group_name"] = gm.get(r["group_id"], {}).get("name", "")
        return jsonify(people=rows, max_faces=config.MAX_EMB_PER_PERSON)

    @app.post("/api/people")
    @admin
    def people_post():
        j = request.get_json(force=True)
        pid = str(j.get("id", "")).strip().lower()[:40]
        name = str(j.get("name", "")).strip()[:80]
        role = j.get("role") if j.get("role") in ("student", "staff") else "student"
        gid = j.get("group_id") if str(j.get("group_id") or "").isdigit() else None
        if not re.fullmatch(r"[a-z0-9_.\-]+", pid or "") or not name:
            return err("bad_input")
        db.upsert_person(pid, name, role, int(gid) if gid else None, str(j.get("chat_id", "")).strip()[:40])
        gallery.reload()
        return jsonify(ok=True, id=pid)

    @app.delete("/api/people/<pid>")
    @admin
    def people_del(pid):
        db.remove_person(pid, hard=request.args.get("hard") == "1")
        gallery.reload()
        return jsonify(ok=True)

    def add_face(pid, emb):
        if not db.person(pid):
            return err("not_found", 404)
        other, score, _ = gallery.match(emb)
        if other and other != pid and request.args.get("force") != "1":
            return err("duplicate_face", 409, who=gallery.names.get(other, other), score=round(score, 2))
        db.add_embedding(pid, emb)
        gallery.reload()
        return jsonify(ok=True, faces=db.one("SELECT COUNT(*) n FROM embeddings WHERE person_id=?", (pid,))["n"])

    @app.post("/api/people/<pid>/capture")
    @admin
    def capture(pid):
        frame, dets, ts = pl.latest
        if frame is None or not dets or time.time() - ts > 1.0:
            return err("no_face")
        good = [d for d in dets if quality_ok(d)]
        if len(good) != 1:
            return err("one_face_needed")
        return add_face(pid, engine.embed(frame, good[0]))

    @app.post("/api/people/<pid>/upload")
    @admin
    def upload(pid):
        f = request.files.get("photo")
        img = cv2.imdecode(np.frombuffer(f.read(), np.uint8), cv2.IMREAD_COLOR) if f else None
        if img is None:
            return err("bad_image")
        if max(img.shape[:2]) > 1600:
            s = 1600 / max(img.shape[:2])
            img = cv2.resize(img, None, fx=s, fy=s)
        dets = engine.analyze(img)
        if len(dets) != 1:
            return err("one_face_needed")
        return add_face(pid, dets[0].emb)

    @app.delete("/api/people/<pid>/faces")
    @admin
    def faces_del(pid):
        db.clear_embeddings(pid)
        gallery.reload()
        return jsonify(ok=True)

    # ---------- 出席 ----------
    @app.get("/api/day")
    @admin
    def day():
        now = datetime.now()
        d = parse_date(request.args.get("date"), now.date())
        gm, hol = db.groups_map(), db.holidays()
        ppl = db.people(group=group_arg())
        recs = db.att_range(d.isoformat(), d.isoformat(), group_arg())
        rows, cnt = [], {}
        for p, g, _, rec, st in logic.iter_days(ppl, gm, recs, hol, d, d, now):
            cnt[st] = cnt.get(st, 0) + 1
            rows.append({"id": p["id"], "name": p["name"], "role": p["role"], "group": g["name"], "status": st,
                         "check_in": rec and rec["check_in"],
                         "late_min": logic.late_minutes(g, d, rec["check_in"]) if rec and st == "late" else 0,
                         "snapshot": rec and rec["snapshot"], "note": (rec or {}).get("note", ""),
                         "manual": bool(rec and rec["source"] == "manual")})
        order = {"late": 0, "present": 1, "absent": 2, "excused": 3, "pending": 4, "off": 5}
        rows.sort(key=lambda r: (order.get(r["status"], 9), r["name"]))
        return jsonify(date=d.isoformat(), rows=rows, counts=cnt, holiday=hol.get(d.isoformat()))

    @app.post("/api/mark")
    @admin
    def mark():
        j = request.get_json(force=True)
        if j.get("status") not in logic.STATUSES + ("clear",) or not db.person(j.get("person_id")) \
                or parse_date(j.get("date"), None) is None:
            return err("bad_input")
        db.mark(j["person_id"], j["date"], j["status"], str(j.get("note", ""))[:200])
        return jsonify(ok=True)

    def range_args():
        now = datetime.now()
        d2 = parse_date(request.args.get("to"), now.date())
        d1 = parse_date(request.args.get("from"), d2 - timedelta(days=29))
        if d1 > d2 or (d2 - d1).days > 366:
            d1 = d2 - timedelta(days=29)
        return d1, d2, now

    @app.get("/api/report")
    @admin
    def report():
        d1, d2, now = range_args()
        gm = db.groups_map()
        ppl = db.people(group=group_arg())
        recs = db.att_range(d1.isoformat(), d2.isoformat(), group_arg())
        return jsonify(rows=logic.build_report(ppl, gm, recs, db.holidays(), d1, d2, now),
                       **{"from": d1.isoformat(), "to": d2.isoformat()})

    @app.get("/api/export.<fmt>")
    @admin
    def export(fmt):
        d1, d2, now = range_args()
        gm, hol = db.groups_map(), db.holidays()
        ppl = db.people(group=group_arg())
        recs = db.att_range(d1.isoformat(), d2.isoformat(), group_arg())
        head = ["ID", "Name", "Group", "Date", "Status", "Check-in", "Late (min)", "Note"]
        rows = []
        for p, g, d, rec, st in logic.iter_days(ppl, gm, recs, hol, d1, d2, now):
            if st in ("off", "future", "pending"):
                continue
            rows.append([p["id"], p["name"], g["name"], d.isoformat(), st,
                         (rec or {}).get("check_in") or "",
                         logic.late_minutes(g, d, rec["check_in"]) if rec and st == "late" else 0,
                         (rec or {}).get("note", "")])
        fname = f"FACEATTEND_{d1}_{d2}.{fmt}"
        if fmt == "csv":
            buf = io.StringIO()
            csv.writer(buf).writerows([head] + rows)
            return Response("\ufeff" + buf.getvalue(), mimetype="text/csv; charset=utf-8",
                            headers={"Content-Disposition": f"attachment; filename={fname}"})
        if fmt == "xlsx":
            try:
                from openpyxl import Workbook
            except ImportError:
                return err("openpyxl_missing", 501)
            wb = Workbook()
            ws = wb.active
            ws.append(head)
            for r in rows:
                ws.append(r)
            out = io.BytesIO()
            wb.save(out)
            return Response(out.getvalue(), headers={"Content-Disposition": f"attachment; filename={fname}"},
                            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        abort(404)

    # ---------- 未登録者 / 画像 / パスワード ----------
    @app.get("/api/unknown")
    @admin
    def unknown():
        return jsonify(rows=db.unknown_list())

    @app.get("/snap/<path:p>")
    @admin
    def snap(p):
        return send_from_directory(config.DATA, p, max_age=3600)

    @app.post("/api/password")
    @admin
    def password():
        j = request.get_json(force=True)
        if not check_password_hash(db.meta_get("admin_hash"), j.get("old", "")):
            return err("bad_password", 403)
        if len(str(j.get("new", ""))) < 8:
            return err("too_short")
        db.meta_set("admin_hash", generate_password_hash(j["new"]))
        return jsonify(ok=True)

    return app


if __name__ == "__main__":
    from camera import Camera
    from engine import Engine
    print("モデルを読み込み中...（初回はインターネットからダウンロードします）")
    application = create_app(Engine(), Camera())
    if config.HOST != "127.0.0.1":
        print("注意: サーバーがネットワークに公開されています。管理者パスワードを変更し、HTTPS/VPNを使用してください。")
    print(f"ドア画面: http://127.0.0.1:{config.PORT}   管理画面: http://127.0.0.1:{config.PORT}/admin")
    application.run(host=config.HOST, port=config.PORT, debug=False, threaded=True)
