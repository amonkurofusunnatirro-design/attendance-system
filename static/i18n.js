const I18N = {
ja: {
 look:"カメラを見てください", in:"ようこそ", late_msg:"遅刻です", late:"遅刻", already:"本日は登録済みです",
 unknown:"未登録の人物", unknown_sub:"登録されていません。管理者に連絡してください", spoof:"偽の顔", spoof_sub:"写真または画面を検出しました",
 start:"開始", start_sub:"音声と全画面のため、一度クリックしてください", passes:"最近の通過", none_yet:"まだ誰も通過していません",
 cam_off:"カメラが接続されていません。接続を確認してください。", registered:"名登録",
 speak_in:"ようこそ、{name}さん", speak_late:"{name}さん、遅刻です", speak_unknown:"未登録の人物です",
 present:"出席", absent:"欠席", excused:"公欠", off:"休み", pending:"待機中", future:"未来",
 nav_today:"本日", nav_people:"登録者", nav_groups:"グループ", nav_report:"レポート", nav_alerts:"警告", nav_account:"システム",
 logout:"ログアウト", date:"日付", group:"グループ", all_groups:"すべてのグループ", name:"氏名", id:"ID", role:"区分",
 student:"学生・生徒", staff:"社員・職員", chat_id:"Telegram チャットID", faces:"顔データ", actions:"操作",
 save:"保存", delete:"削除", edit:"編集", enroll:"顔登録", capture:"撮影", upload_photo:"写真をアップロード",
 reset_faces:"顔データを消去", check_in:"入室", late_min:"遅刻(分)", status:"状態",
 note:"備考", clear:"解除", start_time:"開始", grace:"猶予(分)", end_time:"終了", workdays:"稼働日",
 holidays:"休日", add:"追加", from:"開始日", to:"終了日", export_csv:"CSV出力", export_xlsx:"Excel出力",
 rate:"出席率", no_rows:"データなし", saved:"保存しました", confirm_delete:"削除しますか？", pw_old:"現在のパスワード", pw_new:"新しいパスワード（8文字以上）",
 change_pw:"パスワード変更", camera:"カメラ", liveness:"なりすまし対策", people_n:"登録人数", fps:"処理速度(fps)",
 live_off:"写真・画面によるなりすまし対策が無効です。RealSense深度カメラか models/antispoof.onnx を追加してください。",
 kind:"種類", time:"時刻", k_unknown:"未登録", k_spoof:"偽の顔", enroll_hint:"正面を向き、毎回少し角度を変えて5回以上撮影してください。",
 close:"閉じる", no_image:"画像なし", mark:"変更", camera_view:"カメラ", e_generic:"エラーが発生しました", e_bad_input:"入力を確認してください（ID: 英数字と - _ .）",
 e_no_face:"顔が検出できません", e_one_face_needed:"顔が1つだけ映るようにしてください", e_duplicate_face:"この顔は別の人で登録済みです",
 e_group_not_empty:"グループに所属者がいます", e_duplicate_name:"同名のグループがあります", e_bad_image:"画像を読み込めません",
 e_bad_password:"現在のパスワードが違います", e_too_short:"パスワードが短すぎます", e_not_found:"見つかりません", e_openpyxl_missing:"openpyxl が未インストールです",
 login_title:"管理者ログイン", password:"パスワード", sign_in:"ログイン", bad_login:"パスワードが違います", too_many:"試行が多すぎます。1分お待ちください。",
 wd1:"月", wd2:"火", wd3:"水", wd4:"木", wd5:"金", wd6:"土", wd7:"日", faces_of:"{n}/{m}枚",
},
en: {
 look:"Look at the camera", in:"Welcome", late_msg:"You are late", late:"Late", already:"Already checked in today",
 unknown:"Unknown person", unknown_sub:"Not registered. Please contact the administrator", spoof:"Fake face", spoof_sub:"Photo or screen detected",
 start:"Start", start_sub:"Click once to enable sound and full screen", passes:"Recent passes", none_yet:"Nobody has passed yet",
 cam_off:"Camera not connected. Check the connection.", registered:"registered",
 speak_in:"Welcome, {name}", speak_late:"{name}, you are late", speak_unknown:"Unknown person",
 present:"Present", absent:"Absent", excused:"Excused", off:"Off", pending:"Pending", future:"Upcoming",
 nav_today:"Today", nav_people:"People", nav_groups:"Groups", nav_report:"Reports", nav_alerts:"Alerts", nav_account:"System",
 logout:"Log out", date:"Date", group:"Group", all_groups:"All groups", name:"Name", id:"ID", role:"Type",
 student:"Student", staff:"Staff", chat_id:"Telegram chat ID", faces:"Faces", actions:"Actions",
 save:"Save", delete:"Delete", edit:"Edit", enroll:"Enroll face", capture:"Capture", upload_photo:"Upload photo",
 reset_faces:"Reset faces", check_in:"In", late_min:"Late (min)", status:"Status",
 note:"Note", clear:"Clear", start_time:"Start", grace:"Grace (min)", end_time:"End", workdays:"Work days",
 holidays:"Holidays", add:"Add", from:"From", to:"To", export_csv:"Download CSV", export_xlsx:"Download Excel",
 rate:"Attendance %", no_rows:"No data", saved:"Saved", confirm_delete:"Delete this?", pw_old:"Current password", pw_new:"New password (8+ chars)",
 change_pw:"Change password", camera:"Camera", liveness:"Spoof protection", people_n:"Registered", fps:"Speed (fps)",
 live_off:"Photo/screen spoof protection is OFF. Add a RealSense depth camera or models/antispoof.onnx.",
 kind:"Type", time:"Time", k_unknown:"Unknown", k_spoof:"Fake face", enroll_hint:"Look straight and turn your head slightly each time. Capture at least 5 times.",
 close:"Close", no_image:"No image", mark:"Mark", camera_view:"Camera", e_generic:"Something went wrong", e_bad_input:"Check the fields (ID: letters, digits, - _ .)",
 e_no_face:"No face in frame", e_one_face_needed:"Exactly one face must be in frame", e_duplicate_face:"This face is already registered to someone else",
 e_group_not_empty:"The group still has people", e_duplicate_name:"A group with this name exists", e_bad_image:"Could not read the image",
 e_bad_password:"Current password is wrong", e_too_short:"Password is too short", e_not_found:"Not found", e_openpyxl_missing:"openpyxl is not installed",
 login_title:"Administrator sign-in", password:"Password", sign_in:"Sign in", bad_login:"Wrong password", too_many:"Too many attempts. Wait a minute.",
 wd1:"Mon", wd2:"Tue", wd3:"Wed", wd4:"Thu", wd5:"Fri", wd6:"Sat", wd7:"Sun", faces_of:"{n}/{m} faces",
}};
const LANGS = Object.keys(I18N);
const LANG = (() => {
  const q = new URLSearchParams(location.search).get('lang');
  if (q && I18N[q]) { try { localStorage.setItem('lang', q); } catch (e) {} return q; }
  let s = null; try { s = localStorage.getItem('lang'); } catch (e) {}
  return I18N[s] ? s : (I18N[document.documentElement.lang] ? document.documentElement.lang : 'ja');
})();
function t(k, v) {
  let s = (I18N[LANG] && I18N[LANG][k]) ?? I18N.en[k] ?? k;
  if (v) for (const a in v) s = s.replace('{' + a + '}', v[a]);
  return s;
}
document.documentElement.lang = LANG;