#!/usr/bin/env python3
"""
乾媽智囊團 - Notion 同步腳本
用法：python notion_sync.py
環境變數：NOTION_TOKEN（或直接在下方填入）
"""

import os, json, re, time, math
from urllib.request import urlopen, Request
from urllib.error import HTTPError

# ===== 設定區 =====
NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")   # 從環境變數讀取
DB_IDS = {
    "問題": "665202e226834609a738368a68add331",
    "美食": "842af218833a4666ab11aece5765e04d",
    "住宿": "b76929d8ea0e4c3ebc9cb3b625b5f6f1",
    "景點": "262599c27dd64f98b366b3ed16e06e8c",
    "團購": "8f604901c7744574a554c2592edf2c26",
}
OUTPUT_HTML = "index.html"
# ==================

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

def notion_request(url, payload=None):
    """呼叫 Notion API（支援 POST/GET）"""
    data = json.dumps(payload).encode() if payload else None
    method = "POST" if data else "GET"
    req = Request(url, data=data, headers=HEADERS, method=method)
    with urlopen(req) as r:
        return json.loads(r.read())

def query_database(db_id):
    """分頁抓取整個資料庫的所有頁面"""
    pages, cursor = [], None
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    while True:
        payload = {"page_size": 100}
        if cursor:
            payload["start_cursor"] = cursor
        result = notion_request(url, payload)
        pages.extend(result.get("results", []))
        if not result.get("has_more"):
            break
        cursor = result.get("next_cursor")
        time.sleep(0.3)   # 避免 rate limit
    return pages

def get_prop(page, name, default=None):
    """取得頁面屬性值"""
    props = page.get("properties", {})
    p = props.get(name)
    if not p:
        return default
    t = p.get("type")
    if t == "title":
        parts = p.get("title", [])
        return "".join(x.get("plain_text","") for x in parts).strip() or default
    if t == "rich_text":
        parts = p.get("rich_text", [])
        return "".join(x.get("plain_text","") for x in parts).strip() or default
    if t == "select":
        s = p.get("select")
        return s.get("name") if s else default
    if t == "multi_select":
        return [x.get("name","") for x in p.get("multi_select", [])]
    if t == "date":
        d = p.get("date")
        return d.get("start") if d else default
    if t == "checkbox":
        return p.get("checkbox", False)
    if t == "number":
        v = p.get("number")
        return v if v is not None else default
    if t == "relation":
        return [x.get("id","") for x in p.get("relation", [])]
    if t == "url":
        return p.get("url") or default
    if t == "rollup":
        ro = p.get("rollup", {})
        if ro.get("type") == "number":
            return ro.get("number") or default
        if ro.get("type") == "array":
            arr = ro.get("array", [])
            texts = []
            for item in arr:
                if item.get("type") == "title":
                    texts.extend(x.get("plain_text","") for x in item.get("title",[]))
                elif item.get("type") == "rich_text":
                    texts.extend(x.get("plain_text","") for x in item.get("rich_text",[]))
            return ", ".join(t for t in texts if t) or default
    return default

def clean(text):
    """移除 notion 內部連結殘留"""
    if not text:
        return None
    text = re.sub(r'\s*\(https://www\.notion\.so/[^)]*\)', '', str(text))
    text = re.sub(r'\(https?://[^)]*\)', '', text).strip()
    return text if text and text != "nan" else None

def extract_names(raw):
    """從 'Name (notion_url), Name2 ...' 格式提取名字清單"""
    if not raw:
        return []
    cleaned = re.sub(r'\s*\(https://www\.notion\.so/[^)]*\)', '', str(raw))
    return [p.strip() for p in cleaned.split(",") if p.strip()]

def safe_int(v):
    try:
        return int(float(v))
    except:
        return 0

# ===================================================
#  抓取各資料庫
# ===================================================
def fetch_questions():
    print("  抓取問題資料庫...")
    pages = query_database(DB_IDS["問題"])
    records = []
    for page in pages:
        q = clean(get_prop(page, "問題🔴"))
        if not q:
            continue
        tags_raw = get_prop(page, "分類", "")
        if isinstance(tags_raw, list):
            tags = tags_raw
        else:
            tags = [t.strip() for t in str(tags_raw).split(",") if t.strip()]

        food_list  = extract_names(get_prop(page, "美食清單", ""))
        hotel_list = extract_names(get_prop(page, "住宿清單", ""))
        spot_list  = extract_names(get_prop(page, "景點清單", ""))
        related_q  = extract_names(get_prop(page, "相關問題", ""))

        records.append({
            "q":           q,
            "date":        clean(get_prop(page, "日期")),
            "tags":        tags,
            "top":         bool(get_prop(page, "置頂", False)),
            "food_count":  safe_int(get_prop(page, "美食數", 0)),
            "hotel_count": safe_int(get_prop(page, "住宿數", 0)),
            "spot_count":  safe_int(get_prop(page, "景點數", 0)),
            "food_list":   food_list,
            "hotel_list":  hotel_list,
            "spot_list":   spot_list,
            "related_q":   related_q,
        })
    records.sort(key=lambda x: x["date"] or "", reverse=True)
    print(f"    → {len(records)} 筆")
    return records

def fetch_food():
    print("  抓取美食資料庫...")
    pages = query_database(DB_IDS["美食"])
    records = []
    for page in pages:
        name = clean(get_prop(page, "名字🔴"))
        if not name:
            continue
        # 從多選欄位抓縣市標籤
        city_tags = get_prop(page, "縣市", [])
        if isinstance(city_tags, list):
            city = ", ".join(city_tags) if city_tags else None
        else:
            city = clean(str(city_tags))

        # city_tags: from city-specific columns like 台北美食, 新北美食
        props = page.get("properties", {})
        city_tag_list = []
        for col_name in props:
            if col_name.endswith("美食"):
                v = props[col_name]
                if v and v.get("type") == "multi_select" and v.get("multi_select"):
                    city_name = col_name.replace("美食", "")
                    city_tag_list.append(city_name)
        if not city_tag_list:
            city_tag_list = city_tags if isinstance(city_tags, list) else []

        records.append({
            "name":      name,
            "city":      city,
            "city_tags": city_tag_list,
            "district":  clean(get_prop(page, "行政區")),
            "review":    clean(get_prop(page, "心得")),
            "tags":      city_tags if isinstance(city_tags, list) else [],
            "google":    clean(get_prop(page, "google地圖")),
            "fb":        clean(get_prop(page, "FB")),
            "ig":        clean(get_prop(page, "IG")),
            "website":   clean(get_prop(page, "官網")),
            "tiji":      clean(get_prop(page, "提及🟡")),
            "cat":       clean(get_prop(page, "類別")),
            "qi":        [],
        })
    print(f"    → {len(records)} 筆")
    return records

def fetch_hotel():
    print("  抓取住宿資料庫...")
    pages = query_database(DB_IDS["住宿"])
    records = []
    for page in pages:
        name = clean(get_prop(page, "名字🔴"))
        if not name:
            continue
        city_tags = get_prop(page, "縣市", [])
        city = ", ".join(city_tags) if isinstance(city_tags, list) and city_tags else clean(str(city_tags))
        props = page.get("properties", {})
        city_tag_list = []
        for col_name in props:
            if col_name.endswith("住宿"):
                v = props[col_name]
                if v and v.get("type") == "multi_select" and v.get("multi_select"):
                    city_tag_list.append(col_name.replace("住宿", ""))
        if not city_tag_list:
            city_tag_list = city_tags if isinstance(city_tags, list) else []
        records.append({
            "name":      name,
            "city":      city,
            "city_tags": city_tag_list,
            "district":  clean(get_prop(page, "行政區")),
            "review":    clean(get_prop(page, "心得")),
            "tags":      city_tags if isinstance(city_tags, list) else [],
            "google":    clean(get_prop(page, "google地圖")),
            "fb":        clean(get_prop(page, "FB")),
            "ig":        clean(get_prop(page, "IG")),
            "website":   clean(get_prop(page, "官網")),
            "tiji":      clean(get_prop(page, "提及🟡")),
            "qi":        [],
        })
    print(f"    → {len(records)} 筆")
    return records

def fetch_spot():
    print("  抓取景點資料庫...")
    pages = query_database(DB_IDS["景點"])
    records = []
    for page in pages:
        name = clean(get_prop(page, "名字🔴"))
        if not name:
            continue
        city_tags = get_prop(page, "縣市", [])
        city = ", ".join(city_tags) if isinstance(city_tags, list) and city_tags else clean(str(city_tags))
        props = page.get("properties", {})
        city_tag_list = []
        for col_name in props:
            if col_name.endswith("住宿"):
                v = props[col_name]
                if v and v.get("type") == "multi_select" and v.get("multi_select"):
                    city_tag_list.append(col_name.replace("住宿", ""))
        if not city_tag_list:
            city_tag_list = city_tags if isinstance(city_tags, list) else []
        records.append({
            "name":      name,
            "city":      city,
            "city_tags": city_tag_list,
            "district":  clean(get_prop(page, "行政區")),
            "review":    clean(get_prop(page, "心得")),
            "tags":      city_tags if isinstance(city_tags, list) else [],
            "google":    clean(get_prop(page, "google地圖")),
            "fb":        clean(get_prop(page, "FB")),
            "ig":        clean(get_prop(page, "IG")),
            "website":   clean(get_prop(page, "官網")),
            "tiji":      clean(get_prop(page, "提及🟡")),
            "qi":        [],
        })
    print(f"    → {len(records)} 筆")
    return records

def build_question_index(questions, food, hotel, spot):
    """建立雙向索引：qi（店家→問題）和 fi/hi/si（問題→店家）"""
    q_index   = {item["q"]: i for i, item in enumerate(questions)}
    food_map  = {x["name"]: (i, x) for i, x in enumerate(food)}
    hotel_map = {x["name"]: (i, x) for i, x in enumerate(hotel)}
    spot_map  = {x["name"]: (i, x) for i, x in enumerate(spot)}

    for qi, rec in enumerate(questions):
        fi_list, hi_list, si_list = [], [], []
        for name in rec.get("food_list", []):
            if name in food_map:
                fi, fx = food_map[name]
                fi_list.append(fi)
                if qi not in fx["qi"]:
                    fx["qi"].append(qi)
        for name in rec.get("hotel_list", []):
            if name in hotel_map:
                hi, hx = hotel_map[name]
                hi_list.append(hi)
                if qi not in hx["qi"]:
                    hx["qi"].append(qi)
        for name in rec.get("spot_list", []):
            if name in spot_map:
                si, sx = spot_map[name]
                si_list.append(si)
                if qi not in sx["qi"]:
                    sx["qi"].append(qi)
        rec["fi"] = fi_list
        rec["hi"] = hi_list
        rec["si"] = si_list

    # 相關問題轉成 index
    for rec in questions:
        rec["rqi"] = [q_index[q] for q in rec.get("related_q", []) if q in q_index]
        for k in ("related_q", "food_list", "hotel_list", "spot_list"):
            rec.pop(k, None)

# ===================================================
#  讀取 HTML 模板（從現有的 build3.py 取得樣式/JS）
# ===================================================
def get_html_template():
    """回傳 HTML 模板的 CSS 和 JS 部分（從 build3.py 取得）"""
    # 嘗試讀取 build3.py 取得 CSS/JS
    try:
        with open("build3.py", "r", encoding="utf-8") as f:
            src = f.read()
        css_match = re.search(r'CSS = r"""(.*?)"""', src, re.DOTALL)
        js_match  = re.search(r'JS = r"""(.*?)"""',  src, re.DOTALL)
        if css_match and js_match:
            return css_match.group(1), js_match.group(1)
    except:
        pass
    return None, None

# ===================================================
#  主程式
# ===================================================

def fetch_gp():
    """抓取團購行程表：待開團=未打勾，開團期間包含今天"""
    print("  抓取團購資料庫...")
    pages = query_database(DB_IDS["團購"])
    records = []
    from datetime import date
    today = date.today()
    today_str = today.isoformat()

    for page in pages:
        waiting = get_prop(page, "待開團", False)
        if waiting:
            continue
        name = clean(get_prop(page, "項目")) or clean(get_prop(page, "Name")) or "（未命名）"
        # 開團期間
        period_prop = page.get("properties", {}).get("開團期間", {})
        period_start = None
        period_end = None
        if period_prop.get("type") == "date" and period_prop.get("date"):
            period_start = period_prop["date"].get("start")
            period_end = period_prop["date"].get("end") or period_start
        # 篩選開團期間包含今天
        if period_start and period_end:
            if not (period_start <= today_str <= period_end):
                continue
        elif period_start:
            if period_start != today_str:
                continue
        else:
            continue
        period_display = None
        if period_start and period_end and period_start != period_end:
            period_display = period_start + " ~ " + period_end
        elif period_start:
            period_display = period_start
        # 倒數天數
        countdown = None
        try:
            cd_raw = get_prop(page, "倒數天數")
            if cd_raw is not None:
                countdown = int(float(str(cd_raw)))
        except:
            pass
        if countdown is None and period_end:
            try:
                from datetime import date as _d
                end = _d.fromisoformat(period_end)
                countdown = (end - today).days
            except:
                pass
        url = clean(get_prop(page, "網址"))
        records.append({"name": name, "period": period_display, "countdown": countdown, "url": url})

    records.sort(key=lambda x: x["countdown"] if x["countdown"] is not None else 9999)
    print(f"    -> {len(records)} 筆開團中")
    return records


def main():
    if not NOTION_TOKEN:
        print("❌ 錯誤：請設定 NOTION_TOKEN 環境變數")
        print("   執行方式：NOTION_TOKEN=your_token python notion_sync.py")
        return

    print("🔄 開始從 Notion 同步資料...\n")

    # 1. 抓取資料
    questions = fetch_questions()
    food      = fetch_food()
    hotel     = fetch_hotel()
    spot      = fetch_spot()

    # 2. 建立問題反查索引
    print("\n  建立關聯索引...")
    build_question_index(questions, food, hotel, spot)

    # 3. 組合資料
    gp = fetch_gp()
    db = {"q": questions, "f": food, "h": hotel, "s": spot, "gp": gp}
    db_json = json.dumps(db, ensure_ascii=False, separators=(",", ":"))

    # 確認沒有 </script> 破壞 HTML
    db_json = db_json.replace("</script>", "<\\/script>")

    print(f"\n  資料大小：{len(db_json)/1024:.1f} KB")
    print(f"  問題：{len(questions)}，美食：{len(food)}，住宿：{len(hotel)}，景點：{len(spot)}，團購：{len(gp)}")

    # 4. 儲存 JSON（備用）
    with open("db_latest.json", "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    print("  ✓ 已儲存 db_latest.json")

    # 5. 產生 HTML（使用內建模板）
    print("\n  產生 HTML...")
    try:
        from html_template import TEMPLATE
        html = TEMPLATE.replace("DATA_PLACEHOLDER", db_json)
    except ImportError:
        print("  ⚠️  找不到 html_template.py，請確認檔案在同一個資料夾")
        return

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    size = os.path.getsize(OUTPUT_HTML)
    print(f"  ✓ 已產生 {OUTPUT_HTML}（{size/1024:.1f} KB）")
    print("\n✅ 同步完成！")

if __name__ == "__main__":
    main()
