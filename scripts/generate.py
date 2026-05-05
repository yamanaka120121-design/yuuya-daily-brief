#!/usr/bin/env python3
"""
yuuya-daily-brief — メイン生成スクリプト
RSS取得 → HTML生成（漢字一問付き）→ LINE送信
"""

import argparse
import os
import re
import textwrap
from datetime import datetime, timezone, timedelta

import feedparser
import requests

JST = timezone(timedelta(hours=9))

# ─── RSS フィード定義 ──────────────────────────────────────────────────────────

MORNING_FEEDS = [
    ("社会のニュース（NHK）",  "https://www3.nhk.or.jp/rss/news/cat1.xml", 3),
    ("文化・エンタメ（NHK）",  "https://www3.nhk.or.jp/rss/news/cat6.xml", 3),
]

NOON_FEEDS = [
    ("科学・医療（NHK）",      "https://www3.nhk.or.jp/rss/news/cat5.xml", 3),
    ("文化・エンタメ（NHK）",  "https://www3.nhk.or.jp/rss/news/cat6.xml", 3),
]

# ─── 漢字検定準一級 日替わり一問 ──────────────────────────────────────────────

KANJI_QUESTIONS = [
    {"q": "「齟齬」の読みは？",          "a": "そご",           "meaning": "物事がうまくかみ合わないこと"},
    {"q": "「蹉跌」の読みは？",          "a": "さてつ",         "meaning": "つまずき、失敗すること"},
    {"q": "「逡巡」の読みは？",          "a": "しゅんじゅん",   "meaning": "ためらって前に進めないこと"},
    {"q": "「忸怩」の読みは？",          "a": "じくじ",         "meaning": "恥ずかしく思うさま"},
    {"q": "「闊歩」の読みは？",          "a": "かっぽ",         "meaning": "大股で堂々と歩くこと"},
    {"q": "「恬淡」の読みは？",          "a": "てんたん",       "meaning": "物事にこだわらず、さっぱりしているさま"},
    {"q": "「蒙昧」の読みは？",          "a": "もうまい",       "meaning": "道理に暗く、無知なさま"},
    {"q": "「慫慂」の読みは？",          "a": "しょうよう",     "meaning": "すすめてそうさせること"},
    {"q": "「杳として」の読みは？",      "a": "ようとして",     "meaning": "遠くて消息が不明なさま"},
    {"q": "「矍鑠」の読みは？",          "a": "かくしゃく",     "meaning": "老いても元気で丈夫なさま"},
    {"q": "「啻に」の読みは？",          "a": "ただに",         "meaning": "ただそれだけでなく（〜のみならず）"},
    {"q": "「憧憬」の読みは？",          "a": "しょうけい",     "meaning": "あこがれること"},
    {"q": "「諧謔」の読みは？",          "a": "かいぎゃく",     "meaning": "ユーモア、冗談"},
    {"q": "「贖罪」の読みは？",          "a": "しょくざい",     "meaning": "罪をつぐなうこと"},
    {"q": "「嗜好」の読みは？",          "a": "しこう",         "meaning": "好んで楽しむこと"},
    {"q": "「逼迫」の読みは？",          "a": "ひっぱく",       "meaning": "さしせまって余裕がなくなること"},
    {"q": "「慇懃」の読みは？",          "a": "いんぎん",       "meaning": "礼儀正しく丁寧なさま"},
    {"q": "「幽邃」の読みは？",          "a": "ゆうすい",       "meaning": "奥深く静かで趣のあるさま"},
    {"q": "「澎湃」の読みは？",          "a": "ほうはい",       "meaning": "勢いが盛んに起こるさま"},
    {"q": "「蹌踉」の読みは？",          "a": "そうろう",       "meaning": "よろよろと歩くさま"},
    {"q": "「饗宴」の読みは？",          "a": "きょうえん",     "meaning": "盛大なもてなしの宴"},
    {"q": "「僭越」の読みは？",          "a": "せんえつ",       "meaning": "身分や立場を越えて出過ぎること"},
    {"q": "「杞憂」の読みは？",          "a": "きゆう",         "meaning": "必要のない心配をすること"},
    {"q": "「蟄居」の読みは？",          "a": "ちっきょ",       "meaning": "家の中に閉じこもること"},
    {"q": "「捧腹絶倒」の読みは？",      "a": "ほうふくぜっとう","meaning": "腹を抱えて大笑いすること"},
    {"q": "「頓挫」の読みは？",          "a": "とんざ",         "meaning": "物事が途中で行き詰まること"},
    {"q": "「罵倒」の読みは？",          "a": "ばとう",         "meaning": "激しくののしること"},
    {"q": "「縹渺」の読みは？",          "a": "ひょうびょう",   "meaning": "広くはるかに広がるさま"},
    {"q": "「驥尾に付す」の読みは？",    "a": "きびにふす",     "meaning": "すぐれた人に従って功を得ること"},
    {"q": "「諄諄」の読みは？",          "a": "じゅんじゅん",   "meaning": "丁寧にくり返し言い聞かせるさま"},
]


def get_todays_kanji(now: datetime) -> dict:
    day_index = now.timetuple().tm_yday
    return KANJI_QUESTIONS[day_index % len(KANJI_QUESTIONS)]


# ─── フィード取得 ──────────────────────────────────────────────────────────────

def fetch_feed(url: str, max_items: int) -> list[dict]:
    try:
        feed = feedparser.parse(url)
        items = []
        for entry in feed.entries[:max_items]:
            summary = entry.get("summary", "")
            summary = re.sub(r"<[^>]+>", "", summary).strip()
            summary = textwrap.shorten(summary, width=120, placeholder="…")
            items.append({
                "title":   entry.get("title", "（タイトルなし）"),
                "link":    entry.get("link",  "#"),
                "summary": summary,
            })
        return items
    except Exception as e:
        print(f"  [警告] フィード取得失敗 {url}: {e}")
        return []


# ─── HTML 生成 ────────────────────────────────────────────────────────────────

TAG_MAP = {
    "社会": ("tag tag-society",  "社会"),
    "文化": ("tag tag-culture",  "文化・エンタメ"),
    "科学": ("tag tag-science",  "科学・医療"),
}

def _tag_class(source_name: str) -> tuple[str, str]:
    for key, val in TAG_MAP.items():
        if key in source_name:
            return val
    return ("tag tag-default", source_name)


def build_body(items_by_source: list[tuple]) -> str:
    html = ""
    for source_name, items in items_by_source:
        if not items:
            continue
        cls, label = _tag_class(source_name)
        html += f'<p class="section-label">{label}</p>\n'
        for item in items:
            html += (
                f'<div class="card">'
                f'<a class="news-card" href="{item["link"]}" target="_blank" rel="noopener">'
                f'<p class="news-title">{item["title"]}</p>'
            )
            if item["summary"]:
                html += f'<p class="news-summary">{item["summary"]}</p>'
            html += '<span class="news-link">記事を読む →</span></a></div>\n'
    return html


def build_kanji_html(kanji: dict) -> str:
    return (
        '<p class="section-label kanji">漢字検定 準一級 — 今日の一問</p>\n'
        '<div class="card kanji-card">\n'
        f'  <p class="kanji-q">{kanji["q"]}</p>\n'
        '  <details class="kanji-hint">\n'
        '    <summary>答えを見る</summary>\n'
        f'    <p class="kanji-a">読み：{kanji["a"]}</p>\n'
        f'    <p class="kanji-m">意味：{kanji["meaning"]}</p>\n'
        '  </details>\n'
        '</div>\n'
    )


def generate_html(content_type: str, items_by_source: list[tuple], now: datetime) -> str:
    date_str = now.strftime("%Y年%m月%d日（%a） %H:%M JST")
    if content_type == "morning":
        heading      = "朝の記事"
        title        = f"朝の記事 — {now.strftime('%m/%d')}"
        header_color = "#2d6a4f"
        accent_color = "#2d6a4f"
    else:
        heading      = "昼の記事"
        title        = f"昼の記事 — {now.strftime('%m/%d')}"
        header_color = "#1a4a8a"
        accent_color = "#1a4a8a"

    body = build_body(items_by_source)
    if not body:
        body = '<div class="card"><p>現在取得できるニュースがありません。</p></div>'

    if content_type == "morning":
        body = build_kanji_html(get_todays_kanji(now)) + body

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: "Noto Sans JP", -apple-system, BlinkMacSystemFont, sans-serif;
    background: #f1f5f9; color: #1e293b; min-height: 100vh; padding: 16px 16px 40px;
  }}
  .container {{ max-width: 600px; margin: 0 auto; }}

  /* ── ヘッダー ── */
  .page-header {{ margin-bottom: 20px; padding-top: 4px; }}
  .page-date {{ font-size: 11px; color: #94a3b8; font-weight: 500; margin-bottom: 2px; }}
  .page-title {{ font-size: 22px; font-weight: 700; color: #1e293b; }}
  .page-title span {{ color: {header_color}; }}

  /* ── セクションラベル ── */
  .section-label {{
    display: inline-block; font-size: 11px; font-weight: 700;
    padding: 3px 10px; border-radius: 99px; letter-spacing: 0.04em;
    background: {header_color}; color: white; margin-bottom: 10px; margin-top: 20px;
  }}
  .section-label.kanji {{ background: #b45309; }}

  /* ── カード共通 ── */
  .card {{
    background: white; border-radius: 16px;
    box-shadow: 0 2px 8px rgba(0,0,0,.06);
    padding: 16px; margin-bottom: 10px;
  }}
  .card + .card {{ margin-top: 0; }}

  /* ── 漢字カード ── */
  .card.kanji-card {{ border-left: 4px solid #b45309; }}
  .kanji-q {{ font-size: 15px; font-weight: 600; color: #1e293b; line-height: 1.5; }}
  .kanji-hint {{ margin-top: 4px; }}
  .kanji-hint summary {{
    font-size: 13px; color: #b45309; cursor: pointer;
    font-weight: 600; user-select: none; list-style: none;
    display: inline-flex; align-items: center; gap: 4px;
  }}
  .kanji-hint summary::before {{ content: "▶"; font-size: 9px; }}
  details[open] .kanji-hint summary::before {{ content: "▼"; }}
  .kanji-a {{ font-size: 14px; font-weight: 700; color: #1e293b; margin-top: 10px; }}
  .kanji-m {{ font-size: 12px; color: #64748b; margin-top: 3px; }}

  /* ── ニュースカード ── */
  .news-card {{ display: block; text-decoration: none; color: inherit; }}
  .news-card:hover .news-title {{ color: {header_color}; }}
  .tag {{
    display: inline-block; font-size: 11px; font-weight: 600;
    padding: 2px 8px; border-radius: 99px; margin-bottom: 6px;
  }}
  .tag-society {{ background: #dbeafe; color: #1d4ed8; }}
  .tag-culture  {{ background: #fef3c7; color: #92400e; }}
  .tag-science  {{ background: #d1fae5; color: #065f46; }}
  .tag-default  {{ background: #f1f5f9; color: #475569; }}
  .news-title {{
    font-size: 14px; font-weight: 600; color: #1e293b;
    line-height: 1.5; margin-bottom: 4px;
  }}
  .news-summary {{ font-size: 12px; color: #64748b; line-height: 1.6; }}
  .news-link {{
    display: inline-block; margin-top: 8px;
    font-size: 12px; font-weight: 600; color: {header_color};
  }}

  /* ── フッター ── */
  .page-footer {{
    text-align: center; font-size: 11px; color: #cbd5e1;
    margin-top: 32px;
  }}
</style>
</head>
<body>
<div class="container">
  <div class="page-header">
    <p class="page-date">{date_str}</p>
    <h1 class="page-title"><span>{heading}</span></h1>
  </div>
  {body}
  <p class="page-footer">山中優弥 専用 · yuuya-daily</p>
</div>
</body>
</html>"""


# ─── LINE 送信 ────────────────────────────────────────────────────────────────

def send_line(token: str, user_id: str, message: str) -> None:
    resp = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"to": user_id, "messages": [{"type": "text", "text": message}]},
        timeout=15,
    )
    resp.raise_for_status()
    print(f"LINE 送信完了 (status={resp.status_code})")


# ─── エントリーポイント ────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", choices=["morning", "noon"], required=True)
    args = parser.parse_args()

    now          = datetime.now(JST)
    content_type = args.type
    feeds        = MORNING_FEEDS if content_type == "morning" else NOON_FEEDS

    print(f"[{now.strftime('%H:%M JST')}] {content_type} 記事 生成開始")

    items_by_source = []
    for name, url, max_items in feeds:
        print(f"  取得中: {name}")
        items = fetch_feed(url, max_items)
        items_by_source.append((name, items))
        print(f"    → {len(items)} 件")

    html     = generate_html(content_type, items_by_source, now)
    out_path = f"docs/{content_type}.html"
    os.makedirs("docs", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML 保存: {out_path}")

    token   = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
    user_id = os.environ["LINE_USER_ID"]
    label   = "朝" if content_type == "morning" else "昼"
    date_label = now.strftime("%-m/%-d")
    url = (
        "https://yamanaka120121-design.github.io"
        f"/yuuya-daily-brief/{content_type}.html"
    )
    message = f"【{date_label} {label}の記事】\n{url}"
    send_line(token, user_id, message)


if __name__ == "__main__":
    main()
