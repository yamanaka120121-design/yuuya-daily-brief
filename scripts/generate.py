#!/usr/bin/env python3
"""
yuuya-daily-brief — メイン生成スクリプト
RSS取得 → HTML生成 → LINE送信
"""

import argparse
import os
import textwrap
from datetime import datetime, timezone, timedelta

import feedparser
import requests

JST = timezone(timedelta(hours=9))

# ─── RSS フィード定義 ──────────────────────────────────────────────────────────

MORNING_FEEDS = [
    ("NHK 主要ニュース",     "https://www3.nhk.or.jp/rss/news/cat0.xml",   3),
    ("NHK 社会",             "https://www3.nhk.or.jp/rss/news/cat1.xml",   2),
    ("NHK 文化・エンタメ",   "https://www3.nhk.or.jp/rss/news/cat6.xml",   2),
]

NOON_FEEDS = [
    ("NHK 主要ニュース",     "https://www3.nhk.or.jp/rss/news/cat0.xml",   2),
    ("NHK 科学・医療",       "https://www3.nhk.or.jp/rss/news/cat3.xml",   2),
    ("NHK テクノロジー",     "https://www3.nhk.or.jp/rss/news/cat5.xml",   2),
]

# ─── フィード取得 ──────────────────────────────────────────────────────────────

def fetch_feed(url: str, max_items: int) -> list[dict]:
    try:
        feed = feedparser.parse(url)
        items = []
        for entry in feed.entries[:max_items]:
            summary = entry.get("summary", "")
            # HTML タグを簡易除去
            import re
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

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans",
                 "Noto Sans JP", sans-serif;
    background: #f4f5f7;
    color: #222;
    padding: 16px;
  }}
  .container {{ max-width: 640px; margin: 0 auto; }}
  header {{
    background: {header_color};
    color: white;
    border-radius: 12px;
    padding: 20px 20px 14px;
    margin-bottom: 20px;
  }}
  header h1 {{ font-size: 1.25em; font-weight: 700; }}
  header p  {{ font-size: 0.8em; opacity: 0.85; margin-top: 4px; }}
  .section-title {{
    font-size: 0.75em;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: {accent_color};
    margin: 20px 0 8px;
  }}
  .card {{
    background: white;
    border-radius: 10px;
    padding: 14px 16px;
    margin-bottom: 10px;
  }}
  .card a {{
    color: #1a4a8a;
    font-weight: 600;
    font-size: 0.95em;
    text-decoration: none;
    line-height: 1.45;
    display: block;
  }}
  .card a:hover {{ text-decoration: underline; }}
  .card p {{
    font-size: 0.8em;
    color: #666;
    margin-top: 5px;
    line-height: 1.5;
  }}
  footer {{
    text-align: center;
    font-size: 0.72em;
    color: #aaa;
    margin-top: 28px;
    padding-bottom: 24px;
  }}
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>{heading}</h1>
    <p>{date_str}</p>
  </header>
  {body}
  <footer>yuuya-daily-brief · 山中裕也 専用</footer>
</div>
</body>
</html>
"""

def build_body(items_by_source: list[tuple]) -> str:
    html = ""
    for source_name, items in items_by_source:
        if not items:
            continue
        html += f'<p class="section-title">{source_name}</p>\n'
        for item in items:
            html += (
                f'<div class="card">'
                f'<a href="{item["link"]}" target="_blank" rel="noopener">'
                f'{item["title"]}</a>'
            )
            if item["summary"]:
                html += f'<p>{item["summary"]}</p>'
            html += "</div>\n"
    return html


def generate_html(content_type: str, items_by_source: list[tuple], now: datetime) -> str:
    date_str = now.strftime("%Y年%m月%d日（%a） %H:%M JST")
    if content_type == "morning":
        heading       = "朝のブリーフ"
        title         = f"朝のブリーフ — {now.strftime('%m/%d')}"
        header_color  = "#2d6a4f"
        accent_color  = "#2d6a4f"
    else:
        heading       = "昼のブリーフ"
        title         = f"昼のブリーフ — {now.strftime('%m/%d')}"
        header_color  = "#1a4a8a"
        accent_color  = "#1a4a8a"

    body = build_body(items_by_source)
    if not body:
        body = '<div class="card"><p>現在取得できるニュースがありません。</p></div>'

    return HTML_TEMPLATE.format(
        title=title,
        heading=heading,
        date_str=date_str,
        header_color=header_color,
        accent_color=accent_color,
        body=body,
    )

# ─── LINE 送信 ────────────────────────────────────────────────────────────────

def send_line(token: str, user_id: str, message: str) -> None:
    resp = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "to": user_id,
            "messages": [{"type": "text", "text": message}],
        },
        timeout=15,
    )
    resp.raise_for_status()
    print(f"LINE 送信完了 (status={resp.status_code})")

# ─── エントリーポイント ────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="yuuya-daily-brief generator")
    parser.add_argument("--type", choices=["morning", "noon"], required=True,
                        help="配信種別")
    args = parser.parse_args()

    now          = datetime.now(JST)
    content_type = args.type
    feeds        = MORNING_FEEDS if content_type == "morning" else NOON_FEEDS

    print(f"[{now.strftime('%H:%M JST')}] {content_type} ブリーフ 生成開始")

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
    url     = (
        "https://yamanaka120121-design.github.io"
        f"/yuuya-daily-brief/{content_type}.html"
    )
    message = f"【{date_label} {label}のブリーフ】\n{url}"
    send_line(token, user_id, message)


if __name__ == "__main__":
    main()
