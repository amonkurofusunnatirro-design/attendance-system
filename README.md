# 顔認証出席システム — ドア前の顔認証出席システム

学校・専門学校・大学・企業向けの出席管理システムです。人がドアを立ち止まらずに通るだけで、自動で顔を認識します。

- **認識できた場合**: 緑の帯と音で通知（遅刻は黄色）。出席が自動で記録されます。
- **認識できない場合**: 赤い帯と警告音。顔画像を保存し、Telegramで管理者に通知します。

## 起動方法
1. Python 3.10 以上をインストールします。
2. Windows は `start.bat`、Linux/Mac は `./start.sh` を実行します（初回はライブラリとモデルをダウンロードします）。
3. コンソールに **管理者パスワード** が表示されます（`data/ADMIN_PASSWORD.txt` にも保存）。ログイン後、「システム」画面で変更してください。
4. ブラウザで開きます。
   - ドア用画面: `http://127.0.0.1:5000`（最初に「開始」を1回クリックすると、音と全画面が有効になります）
   - 管理画面: `http://127.0.0.1:5000/admin`
5. 管理画面の **グループ** でクラス・部署を作成します（始業時刻、猶予（分）、勤務日、休日）。
6. **登録者** で人を追加し、**顔登録** でカメラの前で5回以上「撮影」します（毎回少し顔の向きを変える）。写真のアップロードでも登録できます。

旧 `app_jp` からの移行: `python tools.py import-old <旧フォルダ>`（その後 `FACEATTEND_MODEL=buffalo_l` を指定して起動）。

## ドアへの設置のコツ
- カメラは目の高さ（1.4〜1.6m）で、顔に向けて1〜2m先に設置します。背後に窓などの強い光がないようにしてください。
- キオスク表示の自動起動（クリックなしで音が鳴ります）:
  `chrome --kiosk --autoplay-policy=no-user-gesture-required "http://127.0.0.1:5000/?speak=1"`（`speak=1` で名前を音声で読み上げます）
- 遠くから認識したい場合: `FACEATTEND_DET_SIZE=640` とし、カメラ解像度を上げます（config.py の CAM_W / CAM_H）。

## 旧システムからの改善点
| 課題 | 対応 |
|---|---|
| 認識が遅い | 常に最新フレームのみ処理。検出と認識を2段階化。認識済みの人は毎フレームではなく1秒に1回だけ再確認。GPUがなければ自動で高速モデル（`buffalo_s`）を使用 |
| 認識できなくても無反応 | 顔がはっきり見えて0.8秒認識できなければ、赤い帯・警告音・画像保存・Telegram通知。遠い・横向き・ぼやけた顔には誤警報を出さず「もっと近くへ」と表示 |
| 別人のすり抜け | 認識済みの人の位置に別の顔が来たら本人確定を取り消し、再判定 |
| なりすまし（写真・画面） | RealSense深度、または `models/antispoof.onnx`。無効の間は管理画面に警告を表示 |
| 精度 | 1人あたり最大10枚の顔サンプル、1位と2位のスコア差の確認、同じ顔を別人に二重登録できない仕組み |
| 遅刻基準が9:00固定 | グループごとに始業時刻・猶予・勤務日・休日を設定 |
| 欠席者が分からない | 「欠席」「公欠」の状態、レポート、Excel/CSV出力 |
| 退室が記録されない | 入室・退室時刻を記録（MIN_STAY_MIN 経過後の再通過で退室） |
| CSV・ターミナル操作 | SQLiteデータベース、Webからの顔登録、パスワード付き管理画面 |
| 証拠がない | 入室時の顔画像と類似度スコアを保存（保存期間を過ぎると自動削除） |
| 通知 | Telegram: 遅刻・欠席を本人へ、未登録・偽物の顔を管理者へ |

## 設定
`config.py` または環境変数で変更できます。
- `FACEATTEND_DATA`、`FACEATTEND_LANG`（ja / uz / en）、`FACEATTEND_HOST`、`FACEATTEND_PORT`
- `FACEATTEND_CAMERA`（auto、0、`rtsp://...`）、`FACEATTEND_MODEL`、`FACEATTEND_DET_SIZE`
- `FACEATTEND_LIVENESS`、`FACEATTEND_SERVER_SOUND=1`（PC本体のビープ音、Windows）、`FACEATTEND_TG_TOKEN` と `FACEATTEND_TG_ADMIN_CHAT`
- `FACEATTEND_RETENTION_DAYS`、`FACEATTEND_ADMIN_PASSWORD`、`FACEATTEND_KEY`（顔データの暗号化。鍵の生成: `python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"`）
- 精度・速度の調整: `THRESHOLD`（0.45）、`STRONG`（0.60）、`MARGIN`、`UNKNOWN_AFTER_SEC`、`COOLDOWN_SEC`、`REVERIFY_SEC`

Telegram通知を使う場合は、`start.bat` を実行する前に環境変数を設定します（PowerShellの例）:
```powershell
$env:FACEATTEND_TG_TOKEN = "<BotFather token>"
$env:FACEATTEND_TG_ADMIN_CHAT = "<admin chat ID>"
.\start.bat
```

モデルを変更すると顔データは使えなくなります: `python tools.py switch-model buffalo_l` を実行し、全員を再登録してください。
Telegram: 各人の「Telegram チャットID」欄にIDを入力します（本人が先にボットへ /start を送る必要があります）。

## セキュリティとプライバシー
- サーバーは標準で `127.0.0.1` のみで待ち受けます。ネットワークに公開する場合（`FACEATTEND_HOST=0.0.0.0`）は、パスワードを変更し、VPN/HTTPSを使用してください。
- `data/` フォルダ（顔データ・画像）は生体情報です。第三者に渡さず、gitにも含めないでください（`.gitignore` 設定済み）。
- 顔データの利用について本人から書面で同意を得て、個人情報保護法（APPI）など関連法令を遵守してください。
- Telegram のボットトークンや管理者チャットIDなどの秘密情報は、ソースコードに記載せず環境変数で設定してください。公開リポジトリに含めないでください。既に公開・共有したトークンは BotFather で失効させ、新しいものに交換してください。
- GitHub にはソースコードのみを公開してください。`data/` には生体情報・出席記録・管理者パスワードが含まれるため、リポジトリに追加しないでください。

## 現在の制限事項
- 授業ごとの出席には未対応です。1日1回の入退室記録で、ドア設置を想定しています。
- マスクや暗い環境では精度が下がります。よく似た2人（兄弟など）は MARGIN の判定により「未登録」となる場合があります。
- Webカメラ用のなりすまし対策モデルはコードに組み込み済みですが、モデルファイルは同梱していません。お使いのカメラで動作を確認してください。

## テスト
`python -m unittest discover -s tests -v` — 擬似カメラによる自動テスト11項目（認識、未登録警告、遅刻、退室、レポート、管理API、セキュリティ）。
