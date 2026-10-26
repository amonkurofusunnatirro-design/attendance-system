"""補助コマンド。
  python tools.py import-old <旧フォルダ>   - 旧 app_jp (faces_db.json, 出席.csv) のデータを移行
  python tools.py switch-model <名前>       - モデル変更（全員の顔データが消えます。登録者は残ります）
"""
import csv
import json
import sys
from pathlib import Path

import numpy as np

import db


def import_old(folder):
    folder = Path(folder)
    db.init()
    gid = db.groups()[0]["id"]
    faces = folder / "faces_db.json"
    n = 0
    if faces.exists():
        for sid, it in json.loads(faces.read_text(encoding="utf-8")).items():
            pid = sid.strip().lower()
            db.upsert_person(pid, it["name"], "student", gid, "")
            v = np.array(it["embedding"], np.float32)
            db.add_embedding(pid, v / (np.linalg.norm(v) + 1e-6))
            n += 1
        db.meta_set("model", "buffalo_l")    # 旧システムは buffalo_l を使用していた
        print(f"{n}名を移行しました。旧顔データは 'buffalo_l' モデル用です:")
        print("  -> FACEATTEND_MODEL=buffalo_l を指定して起動してください（または再登録して buffalo_s を使用）。")
    csvs = [p for p in folder.glob("*.csv")]
    k = 0
    for f in csvs:
        try:
            for r in csv.DictReader(open(f, encoding="utf-8-sig")):
                pid = (r.get("ID") or "").strip().lower()
                if pid and db.person(pid) and not db.att_get(pid, r["日付"]):
                    db.x("INSERT INTO attendance(person_id,date,check_in,status,source) VALUES(?,?,?,?,'import')",
                         (pid, r["日付"], r["時刻"], "late" if r["状態"] == "遅刻" else "present"))
                    k += 1
        except Exception as e:
            print(f"{f.name}: スキップしました ({e})")
    print(f"{k}件の出席記録を移行しました。")


def switch_model(name):
    db.init()
    db.x("DELETE FROM embeddings")
    db.meta_set("model", name)
    print(f"モデルを '{name}' に変更しました。全員を再登録してください（管理画面 -> 登録者 -> 顔登録）。")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "import-old":
        import_old(sys.argv[2])
    elif len(sys.argv) == 3 and sys.argv[1] == "switch-model":
        switch_model(sys.argv[2])
    else:
        print(__doc__)
