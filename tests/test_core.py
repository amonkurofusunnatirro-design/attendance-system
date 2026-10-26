"""擬似カメラ・擬似エンジンによるテスト（実カメラ・実モデル不要）:  python -m unittest -v"""
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

os.environ["FACEATTEND_DATA"] = tempfile.mkdtemp()
os.environ["FACEATTEND_ADMIN_PASSWORD"] = "testpass123"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402
import logic  # noqa: E402
from engine import Det  # noqa: E402

rng = np.random.default_rng(1)
_n = lambda v: v / np.linalg.norm(v)  # noqa: E731
VEC = {k: _n(rng.normal(size=512).astype(np.float32)) for k in "ABX"}
VEC["A2"] = _n(VEC["A"] + 0.02 * rng.normal(size=512).astype(np.float32))
CODE = {None: 0, "A": 1, "A2": 2, "B": 3, "X": 4, "small": 5}


class FakeCam:
    source, mode, ok, has_depth = "fake", "fake", True, False

    def __init__(self):
        self.who, self.seq = None, 0

    def start(self):
        return True

    def read(self):
        self.seq += 1
        f = np.zeros((480, 640, 3), np.uint8)
        f[0, 0, 0] = CODE[self.who]
        return f, None, self.seq


class FakeEngine:
    device = "fake"

    calls = 0

    def detect(self, frame):
        code = int(frame[0, 0, 0])
        if code == 0:
            return []
        key = {1: "A", 2: "A2", 3: "B", 4: "X", 5: "A"}[code]
        w = 40 if code == 5 else 150
        return [Det((200, 100, 200 + w, 100 + w), 0.95, None, key)]

    def embed(self, frame, det):
        if det.emb is None:
            FakeEngine.calls += 1
            det.emb = VEC[det.kps]
        return det.emb

    def analyze(self, frame):
        ds = self.detect(frame)
        for d in ds:
            self.embed(frame, d)
        return ds


class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init()
        cls.gid = db.save_group(None, "Class-1", "09:00", 5, "17:00", "1,2,3,4,5")
        db.upsert_person("a1", "Alice", "student", cls.gid, "")
        db.upsert_person("b1", "Bob", "staff", cls.gid, "")
        db.add_embedding("a1", VEC["A"])
        db.add_embedding("b1", VEC["B"])
        from app import create_app
        cls.cam = FakeCam()
        cls.app = create_app(FakeEngine(), cls.cam)
        cls.c = cls.app.test_client()
        cls.H = {"X-Requested-With": "FaceAttendance"}

    def wait(self, typ, timeout=4, after=0):
        t0 = time.time()
        while time.time() - t0 < timeout:
            evs, _ = self.app.pl.events_after(after)
            hit = [e for e in evs if e["type"] == typ]
            if hit:
                return hit[0]
            time.sleep(0.05)
        return None

    def test_1_known_person_fast(self):
        self.cam.who = "A"
        t0 = time.time()
        ev = self.wait("in")
        self.assertIsNotNone(ev)
        self.assertEqual(ev["pid"], "a1")
        self.assertLess(time.time() - t0, 1.0)
        self.cam.who = None

    def test_2_cooldown_no_duplicate(self):
        self.cam.who = "A"
        time.sleep(0.6)
        evs, _ = self.app.pl.events_after(0)
        self.assertEqual(len([e for e in evs if e["type"] == "in" and e["pid"] == "a1"]), 1)
        self.cam.who = None

    def test_3_unknown_alarm(self):
        _, last = self.app.pl.events_after(0)
        self.cam.who = "X"
        self.assertIsNotNone(self.wait("unknown", after=last))
        self.assertTrue(db.unknown_list())
        self.cam.who = None

    def test_4_small_face_no_false_alarm(self):
        time.sleep(0.3)
        _, last = self.app.pl.events_after(0)
        self.cam.who = "small"
        time.sleep(1.5)
        evs, _ = self.app.pl.events_after(last)
        self.assertEqual([e for e in evs if e["type"] == "unknown"], [])
        self.cam.who = None

    def test_4b_identified_person_not_reembedded_every_frame(self):
        self.cam.who = "A"
        time.sleep(0.2)
        n0 = FakeEngine.calls
        time.sleep(0.5)                      # REVERIFY_SEC=1.0 のため0.5秒間はほぼ再計算されない
        self.assertLessEqual(FakeEngine.calls - n0, 2)
        self.cam.who = None

    def test_5_multi_embedding_match(self):
        self.assertEqual(self.app.gallery.match(VEC["A2"])[0], "a1")

    def test_6_late_out_already(self):
        db.upsert_person("c1", "Carol", "student", self.gid, "")
        d = datetime(2026, 10, 21, 9, 3)       # 猶予(5分)以内
        self.assertEqual(db.punch("c1", d), ("in", "present"))
        self.assertEqual(db.punch("c1", d + timedelta(minutes=5))[0], "already")
        self.assertEqual(db.punch("c1", d + timedelta(minutes=45))[0], "out")
        db.upsert_person("c2", "Dan", "student", self.gid, "")
        self.assertEqual(db.punch("c2", datetime(2026, 10, 21, 9, 20)), ("in", "late"))

    def test_7_report_absent_and_weekend(self):
        db.upsert_person("z1", "Zed", "student", self.gid, "")
        now = datetime(2026, 10, 22, 12, 0)
        g = db.groups_map()
        recs = db.att_range("2026-10-21", "2026-10-22", self.gid)
        rows = logic.build_report(db.people(group=self.gid), g, recs, {}, datetime(2026, 10, 21).date(),
                                  datetime(2026, 10, 22).date(), now)
        z = [r for r in rows if r["id"] == "z1"][0]
        self.assertEqual(z["absent"], 2)
        c2 = [r for r in rows if r["id"] == "c2"][0]
        self.assertEqual((c2["late"], c2["absent"], c2["late_min"]), (1, 1, 15))
        self.assertEqual(logic.day_status(g[self.gid], None, datetime(2026, 10, 24).date(), now, {}), "off")

    def test_8_api_auth_csrf_export(self):
        self.assertEqual(self.c.get("/api/people").status_code, 401)
        self.assertEqual(self.c.post("/login", data={"password": "wrong"}).status_code, 200)
        self.assertEqual(self.c.post("/login", data={"password": "testpass123"}).status_code, 302)
        self.assertEqual(self.c.get("/api/people").status_code, 200)
        self.assertEqual(self.c.post("/api/mark", json={}).status_code, 403)
        r = self.c.post("/api/mark", json={"person_id": "z1", "date": "2026-10-21", "status": "excused",
                                           "note": "kasal"}, headers=self.H)
        self.assertEqual(r.status_code, 200)
        day = self.c.get("/api/day?date=2026-10-21").get_json()
        self.assertEqual([x for x in day["rows"] if x["id"] == "z1"][0]["status"], "excused")
        for u in ("/api/export.csv", "/api/export.xlsx", "/api/report", "/api/unknown", "/api/groups"):
            self.assertEqual(self.c.get(u + ("?from=2026-10-21&to=2026-10-21" if "export" in u else "")).status_code, 200, u)
        self.assertEqual(self.c.get("/snap/../attendance.db").status_code, 404)

    def test_9_enroll_blocks_duplicate_face(self):
        self.c.post("/login", data={"password": "testpass123"})
        r = self.c.post("/api/people", json={"id": "N1", "name": "New", "role": "staff", "group_id": self.gid},
                        headers=self.H)
        self.assertEqual(r.status_code, 200)
        self.cam.who = "A"
        time.sleep(0.3)
        r = self.c.post("/api/people/n1/capture", headers=self.H)
        self.assertEqual((r.status_code, r.get_json()["error"]), (409, "duplicate_face"))
        self.cam.who = None

    def test_10_pages(self):
        for u in ("/", "/api/status", "/login"):
            self.assertEqual(self.c.get(u).status_code, 200, u)


if __name__ == "__main__":
    unittest.main(verbosity=2)
