"""カメラ入力: 別スレッドで常に最新フレームを読み込みます（遅延が溜まりません）。
RealSense（カラー+深度）、Webカメラ、IPカメラ（RTSP）に対応。切断されたら自動で再接続します。"""
import sys
import threading
import time

import cv2
import numpy as np

import config

try:
    import pyrealsense2 as rs
except ImportError:
    rs = None


class Camera:
    def __init__(self, source=None):
        self.source = str(source if source is not None else config.CAMERA_SOURCE)
        self.mode = None
        self.ok = False
        self._lock = threading.Lock()
        self._frame = self._depth = None
        self._seq = 0
        self._run = False
        self._pipe = self._align = self._cap = None

    @property
    def has_depth(self):
        return self.mode == "realsense"

    def start(self):
        self._run = True
        self.ok = self._open()
        threading.Thread(target=self._loop, daemon=True).start()
        return self.ok

    def stop(self):
        self._run = False

    def _open(self):
        if self.source == "auto" and rs is not None:
            try:
                p, cfg = rs.pipeline(), rs.config()
                cfg.enable_stream(rs.stream.depth, config.CAM_W, config.CAM_H, rs.format.z16, 30)
                cfg.enable_stream(rs.stream.color, config.CAM_W, config.CAM_H, rs.format.bgr8, 30)
                p.start(cfg)
                self._pipe, self._align, self.mode = p, rs.align(rs.stream.color), "realsense"
                print("RealSenseを起動しました。")
                return True
            except Exception as e:
                print(f"RealSenseを起動できません ({e})。Webカメラを試します...")
        src = 0 if self.source == "auto" else (int(self.source) if self.source.isdigit() else self.source)
        cap = cv2.VideoCapture(src, cv2.CAP_DSHOW) if (sys.platform == "win32" and isinstance(src, int)) \
            else cv2.VideoCapture(src)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAM_W)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAM_H)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self._cap, self.mode = cap, ("ipcam" if isinstance(src, str) else "webcam")
            print(f"カメラを起動しました: {self.mode}")
            return True
        cap.release()
        print("エラー: カメラが見つかりません。")
        return False

    def _close(self):
        try:
            if self._pipe:
                self._pipe.stop()
            if self._cap:
                self._cap.release()
        except Exception:
            pass
        self._pipe = self._cap = None

    def _grab(self):
        if self._pipe:
            fr = self._align.process(self._pipe.wait_for_frames(5000))
            c, d = fr.get_color_frame(), fr.get_depth_frame()
            return (np.asanyarray(c.get_data()), np.asanyarray(d.get_data())) if c and d else (None, None)
        if self._cap:
            ok, f = self._cap.read()
            return (f, None) if ok else (None, None)
        return None, None

    def _loop(self):
        fails = 0
        while self._run:
            if not self.ok:
                time.sleep(2)
                self._close()
                self.ok = self._open()
                continue
            try:
                f, d = self._grab()
            except Exception as e:
                print(f"カメラエラー: {e}")
                f = d = None
            if f is None:
                fails += 1
                time.sleep(0.05)
                if fails > 40:           # 約2秒フレームが来ない場合は再接続
                    self._close()
                    self.ok, fails = False, 0
                continue
            fails = 0
            with self._lock:
                self._frame, self._depth, self._seq = f, d, self._seq + 1

    def read(self):
        with self._lock:
            return self._frame, self._depth, self._seq
