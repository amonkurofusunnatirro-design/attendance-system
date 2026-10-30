"""警告音とTelegram通知。すべて別スレッドで実行され、認識処理を止めません。"""
import threading
from datetime import datetime, timedelta

import config
import db
import logic

try:
    import requests
except ImportError:
    requests = None

MSG = {
    "ja": {"in": "{name}さん {t} に到着しました（{status}）", "late": "遅刻", "present": "出席",
           "absent": "{name}さんは本日出席していません。", "unknown": "未登録の人物を検出しました",
           "spoof": "偽の顔（写真/画面）を検出しました", "absent_sum": "{g}: 欠席 ({n}名): {names}"},
    "en": {"in": "{name} arrived at {t} ({status})", "late": "late", "present": "on time",
           "absent": "{name} is absent today.", "unknown": "Unknown person detected",
           "spoof": "Fake face (photo/screen) detected", "absent_sum": "{g}: absent ({n}): {names}"},
}


def m(key, **kw):
    return MSG.get(config.LANG, MSG["en"])[key].format(**kw)


def beep(kind):
    if not config.SERVER_SOUND:
        return

    def run():
        try:
            import winsound
            seq = {"in": [(1200, 120)], "late": [(700, 200)],
                   "unknown": [(400, 350), (400, 350)], "spoof": [(300, 600)] * 3}.get(kind, [])
            for f, d in seq:
                winsound.Beep(f, d)
        except ImportError:
            print("\a", end="", flush=True)
    threading.Thread(target=run, daemon=True).start()


_warned = set()


def _warn(key, text):
    if key not in _warned:        # 同じ警告は1回だけ表示
        _warned.add(key)
        print(text)


def _send(chat, text, photo=None):
    """Telegramへ送信し、成功なら True。失敗の理由はコンソールに表示します。"""
    try:
        base = f"https://api.telegram.org/bot{config.TG_TOKEN}"
        if photo and photo.exists():
            with open(photo, "rb") as f:
                r = requests.post(f"{base}/sendPhoto", data={"chat_id": chat, "caption": text},
                                  files={"photo": f}, timeout=10)
        else:
            r = requests.post(f"{base}/sendMessage", data={"chat_id": chat, "text": text}, timeout=10)
        j = r.json()
        if j.get("ok"):
            return True
        desc = str(j.get("description", r.status_code))
        print(f"Telegramエラー: {desc} (chat_id={chat})")
        if "chat not found" in desc or "can't initiate" in desc or "blocked" in desc:
            print("  -> 相手が先にボットへ /start を送る必要があります。chat_id が正しいかも確認してください。")
        elif "Unauthorized" in desc or r.status_code == 401:
            print("  -> ボットのトークン (FACEATTEND_TG_TOKEN) が正しくありません。")
    except Exception as e:
        print(f"Telegram送信失敗: {e}")
    return False


def telegram(chat, text, photo=None):
    if not chat:
        return
    if not config.TG_TOKEN:
        _warn("token", "Telegram: FACEATTEND_TG_TOKEN が未設定のため、通知は送信されません。")
        return
    if requests is None:
        _warn("requests", "Telegram: requests が未インストールです (pip install requests)")
        return
    threading.Thread(target=_send, args=(chat, text, photo), daemon=True).start()


def person_arrived(p, status, t):
    text = m("in", name=p["name"], t=t, status=m(status))
    own = str(p.get("chat_id") or "")
    if own:
        telegram(own, text)
    admin = str(config.TG_ADMIN_CHAT or "")
    if config.TG_NOTIFY_ADMIN_ARRIVAL and admin and admin != own:
        telegram(admin, text)


_last_alert = {}


def admin_alert(kind, photo=None):
    import time
    if time.time() - _last_alert.get(kind, 0) < 60:     # 1分に1回まで
        return
    _last_alert[kind] = time.time()
    if config.TG_TOKEN and not config.TG_ADMIN_CHAT:
        _warn("admin", "Telegram: FACEATTEND_TG_ADMIN_CHAT が未設定のため、管理者への警告は送信されません。")
    telegram(config.TG_ADMIN_CHAT, m(kind), photo)


def absent_loop():
    """毎分確認: グループの始業後、欠席者リストを1回だけ送信します。"""
    import time
    while True:
        try:
            now = datetime.now()
            d = now.strftime("%Y-%m-%d")
            hol = db.holidays()
            for g in db.groups():
                key = f"absent_sent:{d}:{g['id']}"
                if db.meta_get(key) or d in hol or now.isoweekday() not in logic.workdays(g):
                    continue
                if now < logic.late_limit(g, now.date()) + timedelta(minutes=config.ABSENT_REPORT_AFTER_MIN):
                    continue
                ppl = db.people(group=g["id"])
                recs = db.att_range(d, d, g["id"])
                gone = [p for p in ppl if (p["id"], d) not in recs]
                db.meta_set(key, "1")
                if gone:
                    telegram(config.TG_ADMIN_CHAT, m("absent_sum", g=g["name"], n=len(gone),
                                                       names=", ".join(p["name"] for p in gone[:30])))
                    for p in gone:
                        telegram(p.get("chat_id"), m("absent", name=p["name"]))
        except Exception as e:
            print(f"absent_loop: {e}")
        time.sleep(60)


if __name__ == "__main__":
    # 動作確認: python notify.py  -> 管理者チャットにテストメッセージを送信
    if not (config.TG_TOKEN and config.TG_ADMIN_CHAT):
        print("FACEATTEND_TG_TOKEN と FACEATTEND_TG_ADMIN_CHAT を設定してから実行してください。")
    elif requests is None:
        print("pip install requests を実行してください。")
    else:
        print("送信成功！" if _send(config.TG_ADMIN_CHAT, "テスト: 顔認証出席システムからの通知です。") else "送信に失敗しました（上のエラーを確認）。")