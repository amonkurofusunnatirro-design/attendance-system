"""時間割・遅刻・レポートのルール（データベースに依存しません）。"""
from datetime import datetime, time, timedelta

DEFAULT_GROUP = {"id": None, "name": "-", "start_time": "09:00", "grace_min": 0,
                 "end_time": "18:00", "workdays": "1,2,3,4,5"}
STATUSES = ("present", "late", "absent", "excused")


def hm(s):
    h, m = str(s).split(":")[:2]
    return time(int(h), int(m))


def workdays(g):
    return {int(x) for x in str(g["workdays"]).split(",") if x.strip()}


def late_limit(g, d):
    return datetime.combine(d, hm(g["start_time"])) + timedelta(minutes=int(g["grace_min"]))


def arrival_status(g, now):
    return "late" if now > late_limit(g, now.date()) else "present"


def late_minutes(g, d, check_in):
    if not check_in:
        return 0
    t = datetime.combine(d, hm(check_in))
    diff = (t - datetime.combine(d, hm(g["start_time"]))).total_seconds() / 60
    return max(0, int(diff - int(g["grace_min"])))


def day_status(g, rec, d, now, holidays):
    """present | late | excused | absent | off | pending | future"""
    if rec:
        return rec["status"]
    if d.isoformat() in holidays or d.isoweekday() not in workdays(g):
        return "off"
    if d > now.date():
        return "future"
    if d == now.date() and now <= late_limit(g, d):
        return "pending"
    return "absent"


def iter_days(people, groups, recs, holidays, d1, d2, now):
    for p in people:
        g = groups.get(p["group_id"]) or DEFAULT_GROUP
        d = d1
        while d <= d2:
            rec = recs.get((p["id"], d.isoformat()))
            yield p, g, d, rec, day_status(g, rec, d, now, holidays)
            d += timedelta(days=1)


def build_report(people, groups, recs, holidays, d1, d2, now):
    stats = {p["id"]: {"id": p["id"], "name": p["name"], "role": p["role"],
                       "group": (groups.get(p["group_id"]) or DEFAULT_GROUP)["name"],
                       "present": 0, "late": 0, "excused": 0, "absent": 0, "late_min": 0}
             for p in people}
    for p, g, d, rec, st in iter_days(people, groups, recs, holidays, d1, d2, now):
        if st in ("present", "late", "excused", "absent"):
            stats[p["id"]][st] += 1
        if st == "late" and rec:
            stats[p["id"]]["late_min"] += late_minutes(g, d, rec["check_in"])
    rows = list(stats.values())
    for r in rows:
        total = r["present"] + r["late"] + r["absent"]
        r["rate"] = round(100 * (r["present"] + r["late"]) / total, 1) if total else None
    return rows
