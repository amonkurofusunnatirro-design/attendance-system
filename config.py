"""すべての設定。環境変数 (FACEATTEND_*) でも変更できます。"""
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = Path(os.environ.get("FACEATTEND_DATA", BASE / "data"))
DB_PATH = DATA / "attendance.db"
SNAP_DIR = DATA / "snapshots"      # 入室した人の顔画像（証拠）
UNK_DIR = DATA / "unknown"         # 未登録・偽物の顔
MODELS = BASE / "models"


def _e(name, default, cast=str):
    v = os.environ.get(name)
    return default if v in (None, "") else cast(v)


def _b(v):
    return str(v).lower() in ("1", "true", "yes", "on")


LANG = _e("FACEATTEND_LANG", "ja")
if LANG not in ("ja", "en"):
    LANG = "ja"
HOST = _e("FACEATTEND_HOST", "127.0.0.1")          # ネットワーク公開は 0.0.0.0（必ずパスワード付きで）
PORT = _e("FACEATTEND_PORT", 5000, int)

# ---- カメラ ----
CAMERA_SOURCE = _e("FACEATTEND_CAMERA", "auto")    # auto | 0 | 1 | rtsp://...
CAM_W, CAM_H = 640, 480

# ---- モデル（速度と精度） ----
MODEL_NAME = _e("FACEATTEND_MODEL", "auto")        # auto: GPUがあれば buffalo_l（高精度）、なければ buffalo_s（約20倍高速）
DET_SIZE = _e("FACEATTEND_DET_SIZE", 0, int)       # 0 = 自動（GPU 640 / CPU 320）。遠くから認識するには大きくしてください

# ---- 認識ルール ----
THRESHOLD = 0.45          # これより類似度が低い場合は未登録
STRONG = 0.60             # これ以上なら1フレームで確定（高速化）
MARGIN = 0.05             # 1位と2位の人物の最小スコア差（取り違え防止）
CONFIRM_COUNT = 2         # 通常の信頼度で確定に必要な連続フレーム数
MIN_FACE_PX = 60          # これより小さい顔は「もっと近くへ」扱い（警告は出さない）
MIN_DET_SCORE = 0.6
UNKNOWN_AFTER_SEC = 0.8   # 顔がはっきり見えてもこの時間認識できなければ「未登録」警告
UNKNOWN_MIN_FRAMES = 3
TRACK_TTL = 1.0
REVERIFY_SEC = 1.0        # 認識済みの人をこの秒数ごとに再確認（高速化）
IDENTITY_DROP_FRAMES = 3  # 認識済みの人と別の顔がこのフレーム数連続で一致しなければ本人確定を取り消す
COOLDOWN_SEC = 20         # 同じ人を再通知しない間隔（秒）
MAX_EMB_PER_PERSON = 10

# ---- なりすまし対策 ----
LIVENESS = _e("FACEATTEND_LIVENESS", "auto")       # auto | depth | model | off
LIVENESS_MIN_RANGE_MM = 12
LIVENESS_MIN_DIST_MM = 250
LIVENESS_MAX_DIST_MM = 1500
ANTISPOOF_MODEL = MODELS / "antispoof.onnx"
ANTISPOOF_MIN = 0.5
SHOW_DEPTH = False

# ---- 警告音 ----
SERVER_SOUND = _b(_e("FACEATTEND_SERVER_SOUND", "0"))   # PC本体のビープ音（Windows）

# ---- Telegram（任意） ----
TG_TOKEN = _e("FACEATTEND_TG_TOKEN", "")
TG_ADMIN_CHAT = _e("FACEATTEND_TG_ADMIN_CHAT", "")
TG_NOTIFY_ADMIN_ARRIVAL = _b(_e("FACEATTEND_TG_NOTIFY_ARRIVAL", "1"))   # 入室通知を管理者チャットにも送る
ABSENT_REPORT_AFTER_MIN = 30   # 始業時刻（+猶予）からこの分数後に欠席者レポートを送信

RETENTION_DAYS = _e("FACEATTEND_RETENTION_DAYS", 90, int)   # 画像の保存期間（日）

LABELS = {
    "ja": {"unknown": "未登録", "fake": "偽物", "closer": "もっと近くへ", "scan": "..."},
    "en": {"unknown": "Unknown", "fake": "FAKE", "closer": "Come closer", "scan": "..."},
}
