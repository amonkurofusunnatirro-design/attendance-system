"""顔検出と認識。高速化のため detection と recognition モジュールだけを読み込みます。"""
import threading
from dataclasses import dataclass

import numpy as np

import config


@dataclass
class Det:
    box: tuple              # x1,y1,x2,y2
    score: float
    emb: np.ndarray = None  # 必要なときに embed() で計算
    kps: object = None


def quality_ok(d):
    return d.score >= config.MIN_DET_SCORE and (d.box[2] - d.box[0]) >= config.MIN_FACE_PX


class Engine:
    """2段階処理: detect() は軽く、embed() は重い。埋め込みは必要な顔だけ計算します。"""

    def __init__(self):
        from insightface.app import FaceAnalysis
        import onnxruntime as ort
        gpu = "CUDAExecutionProvider" in ort.get_available_providers()
        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] if gpu else ["CPUExecutionProvider"]
        name = config.MODEL_NAME if config.MODEL_NAME != "auto" else ("buffalo_l" if gpu else "buffalo_s")
        size = config.DET_SIZE or (640 if gpu else (480 if name == "buffalo_s" else 320))
        self.model_name = name
        self.device = f"{'GPU' if gpu else 'CPU'} / {name} / det {size}"
        print(f"Model: {self.device}")
        app = FaceAnalysis(name=name, providers=providers, allowed_modules=["detection", "recognition"])
        app.prepare(ctx_id=0 if gpu else -1, det_size=(size, size))
        self.det_model, self.rec_model = app.models["detection"], app.models["recognition"]
        self.lock = threading.Lock()

    def detect(self, frame):
        with self.lock:
            boxes, kpss = self.det_model.detect(frame, max_num=0, metric="default")
        if boxes is None or len(boxes) == 0:
            return []
        return [Det(tuple(int(v) for v in b[:4]), float(b[4]), None, kpss[i] if kpss is not None else None)
                for i, b in enumerate(boxes)]

    def embed(self, frame, det):
        if det.emb is None:
            from insightface.app.common import Face
            face = Face(bbox=np.array(det.box, np.float32), kps=det.kps, det_score=det.score)
            with self.lock:
                self.rec_model.get(frame, face)
            det.emb = face.normed_embedding.astype(np.float32)
        return det.emb

    def analyze(self, frame):
        dets = self.detect(frame)
        for d in dets:
            self.embed(frame, d)
        return dets


class Gallery:
    """全員の顔データを1つの行列に保持: 行列積1回で全員と照合します。"""

    def __init__(self):
        self.mat = np.zeros((0, 512), np.float32)
        self.owner = np.zeros(0, int)
        self.pids = []
        self.names = {}
        self._lock = threading.Lock()

    def reload(self):
        import db
        rows = db.all_embeddings()
        pids = sorted({r[0] for r in rows})
        idx = {p: i for i, p in enumerate(pids)}
        if rows:
            mat = np.array([r[1] for r in rows], np.float32)
            mat /= (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-6)
            owner = np.array([idx[r[0]] for r in rows])
        else:
            mat, owner = np.zeros((0, 512), np.float32), np.zeros(0, int)
        with self._lock:
            self.mat, self.owner, self.pids, self.names = mat, owner, pids, db.names()

    def match(self, emb):
        """-> (person_id | None, score, reason)"""
        with self._lock:
            mat, owner, pids = self.mat, self.owner, self.pids
        if not pids:
            return None, 0.0, "empty"
        e = np.asarray(emb, np.float32)
        e = e / (np.linalg.norm(e) + 1e-6)
        best = np.full(len(pids), -1.0, np.float32)
        np.maximum.at(best, owner, mat @ e)
        order = np.argsort(best)[::-1]
        top = float(best[order[0]])
        second = float(best[order[1]]) if len(pids) > 1 else -1.0
        if top < config.THRESHOLD:
            return None, top, "low"
        if second >= config.THRESHOLD and top - second < config.MARGIN:
            return None, top, "ambiguous"
        return pids[order[0]], top, "ok"
