"""ドア処理: フレーム -> 顔 -> 追跡(track) -> 登録/未登録の判定 -> イベント(音・記録)。

速度: 常に最新フレームだけを処理します（キューなし）。顔がはっきり見えて信頼度が高ければ
1フレームで確定します。未登録警告は、顔がはっきり見えて UNKNOWN_AFTER_SEC 秒間認識できな
かった場合のみ出すため、通り過ぎる人に誤警報は出ません。"""
import collections
import threading
import time
from datetime import datetime

import cv2

import config
import db
import notify
from engine import quality_ok

GREEN, AMBER, RED, CYAN, YELLOW, BLUE = (60, 190, 90), (20, 160, 240), (50, 50, 220), (230, 200, 60), (40, 210, 240), (200, 140, 60)


def iou(a, b):
    ix1, iy1, ix2, iy2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


class Track:
    def __init__(self, tid, box, now):
        self.id, self.box, self.first, self.last = tid, box, now, now
        self.cand, self.cand_n = None, 0
        self.identity, self.status = None, ""
        self.unk_n, self.unk_sent = 0, False
        self.spoof_n, self.spoof_sent = 0, False
        self.near = False
        self.miss = 0
        self.next_verify = 0.0


class Pipeline:
    def __init__(self, cam, engine, gallery, liveness):
        self.cam, self.engine, self.gallery, self.liveness = cam, engine, gallery, liveness
        self.events = collections.deque(maxlen=200)
        self._eid = 0
        self._lock = threading.Lock()
        self.tracks, self._tid = [], 0
        self.view = []                 # [(枠, ラベル, 色)] 映像に描画するための情報
        self.latest = (None, [], 0.0)  # (フレーム, 検出結果, 時刻) 顔登録用
        self.last_announce, self.last_status = {}, {}
        self.fps = 0.0
        self._run = False
        self.lab = config.LABELS.get(config.LANG, config.LABELS["en"])

    # ---------- イベント ----------
    def emit(self, typ, **kw):
        with self._lock:
            self._eid += 1
            ev = {"id": self._eid, "ts": time.time(), "type": typ, **kw}
            self.events.append(ev)
        notify.beep(typ)
        return ev

    def events_after(self, after):
        with self._lock:
            if after < 0:
                return [], self._eid
            return [e for e in self.events if e["id"] > after], self._eid

    # ---------- メインループ ----------
    def start(self):
        self._run = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._run = False

    def _loop(self):
        last_seq, t_prev = -1, time.time()
        while self._run:
            frame, depth, seq = self.cam.read()
            if frame is None or seq == last_seq:
                time.sleep(0.005)
                continue
            last_seq = seq
            try:
                dets = self.engine.detect(frame)
                self.latest = (frame, dets, time.time())
                self._update(dets, frame, depth, time.time())
            except Exception as e:
                print(f"認識エラー: {e}")
                time.sleep(0.1)
            dt = time.time() - t_prev
            t_prev = time.time()
            self.fps = 0.9 * self.fps + 0.1 * (1 / dt) if dt > 0 else self.fps

    def _update(self, dets, frame, depth, now):
        used = set()
        for det in sorted(dets, key=lambda d: -(d.box[2] - d.box[0])):
            best, bi = None, 0.3
            for t in self.tracks:
                if t.id not in used and iou(t.box, det.box) > bi:
                    best, bi = t, iou(t.box, det.box)
            if best is None:
                self._tid += 1
                best = Track(self._tid, det.box, now)
                self.tracks.append(best)
            used.add(best.id)
            best.box, best.last = det.box, now
            self._decide(best, det, frame, depth, now)
        self.tracks = [t for t in self.tracks if now - t.last <= config.TRACK_TTL]
        self.view = [self._look(t) for t in self.tracks if now - t.last < 0.4]

    def _decide(self, t, det, frame, depth, now):
        t.near = not quality_ok(det)
        if t.near:
            return
        if t.identity is not None and now < t.next_verify:
            return                                   # 認識済みの人: 埋め込みを計算しない（高速化）
        if not self.liveness.check(frame, depth, det.box):
            t.spoof_n += 1
            if t.spoof_n >= 3 and not t.spoof_sent:
                t.spoof_sent = True
                snap = self._save(frame, det.box, config.UNK_DIR, "spoof")
                db.add_unknown("spoof", snap, 0.0)
                self.emit("spoof")
                notify.admin_alert("spoof", config.DATA / snap if snap else None)
            return
        t.spoof_n = 0
        pid, score, _ = self.gallery.match(self.engine.embed(frame, det))
        if pid:
            t.unk_n = 0
            t.cand_n = t.cand_n + 1 if pid == t.cand else 1
            t.cand = pid
            if pid == t.identity:
                t.miss, t.next_verify = 0, now + config.REVERIFY_SEC
                return
            if score >= config.STRONG or t.cand_n >= config.CONFIRM_COUNT:
                t.miss, t.next_verify = 0, now + config.REVERIFY_SEC
                self._identified(t, pid, score, frame, det.box, now)
                return
        else:
            t.cand, t.cand_n = None, 0
        if t.identity is not None:
            # 前の人の代わりに別の顔が来た可能性: 毎フレーム確認し、本人確定を引き継がない
            t.miss, t.next_verify = t.miss + 1, now
            if t.miss >= config.IDENTITY_DROP_FRAMES:
                t.identity, t.status, t.unk_n, t.miss, t.first = None, "", 0, 0, now
            return
        if pid:
            return                                   # 登録者だが確定待ち
        t.unk_n += 1
        if not t.unk_sent and t.unk_n >= config.UNKNOWN_MIN_FRAMES and now - t.first >= config.UNKNOWN_AFTER_SEC:
            t.unk_sent = True
            snap = self._save(frame, det.box, config.UNK_DIR, "unknown")
            db.add_unknown("unknown", snap, score)
            self.emit("unknown", score=round(score, 2))
            notify.admin_alert("unknown", config.DATA / snap if snap else None)

    def _identified(self, t, pid, score, frame, box, now):
        t.identity, t.unk_sent = pid, False
        p = db.person(pid)
        if not p:
            return
        if now - self.last_announce.get(pid, 0) < config.COOLDOWN_SEC:
            t.status = self.last_status.get(pid, "")
            return
        self.last_announce[pid] = now
        when = datetime.now()
        kind, status = db.punch(pid, when, round(score, 3))
        t.status = status
        self.last_status[pid] = status
        if kind == "in":
            snap = self._save(frame, box, config.SNAP_DIR / when.strftime("%Y-%m-%d"), pid)
            if snap:
                db.set_snapshot(pid, when.strftime("%Y-%m-%d"), snap)
            notify.person_arrived(p, status, when.strftime("%H:%M"))
        group = db.groups_map().get(p["group_id"])
        self.emit(kind, pid=pid, name=p["name"], status=status, group=group["name"] if group else "")

    # ---------- ヘルパー ----------
    def _save(self, frame, box, folder, name):
        try:
            folder.mkdir(parents=True, exist_ok=True)
            h, w = frame.shape[:2]
            bw, bh = box[2] - box[0], box[3] - box[1]
            x1, y1 = max(0, int(box[0] - bw * .25)), max(0, int(box[1] - bh * .25))
            x2, y2 = min(w, int(box[2] + bw * .25)), min(h, int(box[3] + bh * .25))
            fn = folder / f"{name}_{datetime.now().strftime('%H%M%S_%f')[:10]}.jpg"
            ok, buf = cv2.imencode(".jpg", frame[y1:y2, x1:x2], [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not ok:
                raise ValueError("JPEG変換に失敗")
            fn.write_bytes(buf.tobytes())      # cv2.imwrite は Windows の日本語パスで無言で失敗するため使わない
            if not fn.exists() or fn.stat().st_size == 0:
                raise OSError(f"ファイルが作成されませんでした: {fn}")
            return str(fn.relative_to(config.DATA)).replace("\\", "/")
        except Exception as e:
            print(f"画像を保存できませんでした: {e}")
            return None

    def _look(self, t):
        if t.near:
            return t.box, self.lab["closer"], YELLOW
        if t.spoof_sent:
            return t.box, self.lab["fake"], RED
        if t.identity:
            name = self.gallery.names.get(t.identity, t.identity)
            col = AMBER if t.status == "late" else GREEN
            return t.box, name, col
        if t.unk_sent:
            return t.box, self.lab["unknown"], RED
        return t.box, self.lab["scan"], CYAN