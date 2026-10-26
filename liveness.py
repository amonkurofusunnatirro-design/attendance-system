"""なりすまし（写真・画面）判定: RealSense深度、または任意のanti-spoof ONNXモデル。"""
import numpy as np
import cv2

import config


def _depth_live(depth, box):
    h, w = depth.shape[:2]
    x1, y1, x2, y2 = box
    bw, bh = x2 - x1, y2 - y1
    cx1, cx2 = int(max(0, x1 + bw * .25)), int(min(w, x2 - bw * .25))
    cy1, cy2 = int(max(0, y1 + bh * .25)), int(min(h, y2 - bh * .25))
    if cx2 <= cx1 or cy2 <= cy1:
        return False
    region = depth[cy1:cy2, cx1:cx2].astype(np.float32)
    valid = region[region > 0]
    if valid.size < 0.3 * region.size:
        return False
    p10, p90 = np.percentile(valid, [10, 90])
    if not (config.LIVENESS_MIN_DIST_MM <= float(np.median(valid)) <= config.LIVENESS_MAX_DIST_MM):
        return False
    return (p90 - p10) >= config.LIVENESS_MIN_RANGE_MM


class Liveness:
    def __init__(self, has_depth):
        mode = config.LIVENESS
        have_model = config.ANTISPOOF_MODEL.exists()
        if mode == "auto":
            mode = "depth" if has_depth else ("model" if have_model else "off")
        if mode == "depth" and not has_depth:
            print("警告: 深度カメラがないため、なりすまし対策を無効にしました。")
            mode = "off"
        self.sess = None
        if mode == "model":
            if not have_model:
                print(f"警告: {config.ANTISPOOF_MODEL} が見つからないため、なりすまし対策を無効にしました。")
                mode = "off"
            else:
                import onnxruntime as ort
                self.sess = ort.InferenceSession(str(config.ANTISPOOF_MODEL), providers=["CPUExecutionProvider"])
        self.mode = mode

    def check(self, frame, depth, box):
        if self.mode == "depth" and depth is not None:
            return _depth_live(depth, box)
        if self.mode == "model" and self.sess is not None:
            return self._model(frame, box)
        return True

    def _model(self, frame, box, scale=2.7):
        """Silent-Face MiniFASNet方式の80x80切り出し（モデルファイルは別途配置）。"""
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = box
        bw, bh = max(1, x2 - x1), max(1, y2 - y1)
        s = min((h - 1) / bh, (w - 1) / bw, scale)
        nw, nh, cx, cy = bw * s, bh * s, x1 + bw / 2, y1 + bh / 2
        l, t = max(0, cx - nw / 2), max(0, cy - nh / 2)
        r, b = min(w - 1, cx + nw / 2), min(h - 1, cy + nh / 2)
        crop = frame[int(t):int(b) + 1, int(l):int(r) + 1]
        if crop.size == 0:
            return False
        inp = cv2.resize(crop, (80, 80)).astype(np.float32).transpose(2, 0, 1)[None]
        out = self.sess.run(None, {self.sess.get_inputs()[0].name: inp})[0][0]
        e = np.exp(out - out.max())
        return float((e / e.sum())[1]) >= config.ANTISPOOF_MIN
