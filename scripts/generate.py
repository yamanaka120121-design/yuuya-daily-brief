#!/usr/bin/env python3
"""
yuuya-daily-brief — メイン生成スクリプト
RSS取得 → (OpenAI 要約) → HTML生成（漢字一問付き）→ LINE送信
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
# (表示名, URL, 取得件数)  ← SOURCE_META のキーが表示名に含まれていること

_GN = "https://news.google.com/rss/search?hl=ja&gl=JP&ceid=JP:ja&q="

MORNING_FEEDS = [
    # 朝礼トークの素材（奈良・教育・吹奏楽に絞る）
    ("奈良のニュース",  _GN + "%E5%A5%88%E8%89%AF",                               2),  # 奈良
    ("教育ニュース",    _GN + "%E9%AB%98%E6%A0%A1+%E6%95%99%E5%93%A1+%E6%8C%87%E5%B0%8E", 2),  # 高校+教員+指導
    ("吹奏楽・音楽",   _GN + "%E5%90%B9%E5%A5%8F%E6%A5%BD",                      2),  # 吹奏楽
]

NOON_FEEDS = [
    # 授業・部活・図書委員会の準備素材
    ("教育ニュース",   _GN + "%E6%8E%88%E6%A5%AD+%E5%AD%A6%E7%BF%92+%E9%AB%98%E6%A0%A1", 2),  # 授業+学習+高校
    ("吹奏楽・音楽",  _GN + "%E5%90%B9%E5%A5%8F%E6%A5%BD+%E3%82%B3%E3%83%B3%E3%82%AF%E3%83%BC%E3%83%AB", 2),  # 吹奏楽+コンクール
    ("国語・図書",    _GN + "%E5%9B%BD%E8%AA%9E+%E8%AA%AD%E6%9B%B8+%E5%9B%B3%E6%9B%B8%E9%A4%A8",          2),  # 国語+読書+図書館
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


# ─── Claude (Anthropic) 要約 ───────────────────────────────────────────────────

_PERSONA = """\
あなたは奈良県の高校で国語科と吹奏楽部を担当する教師・山中優弥先生（教員5年目）です。
【人物像】音楽と言葉の間にある豊かな世界が好き。奈良の自然・歴史・文化に愛着がある。
生徒との対話を何より大切にし、押しつけがましくない。たとえ話が上手で、
音楽用語（テンポ・ハーモニー・フォルテなど）や国語の言葉を日常会話に自然に使う。
ポップで温かみがあり、でも一言が深い。笑いの中に気づきを入れるのが得意。"""

def ai_rewrite(title: str, summary: str, ai_hint: str) -> str:
    """
    Anthropic claude-haiku-4-5 でカテゴリ別・教員向けのひとこと要約を生成する。
    ANTHROPIC_API_KEY が未設定の場合は元の summary をそのまま返す。
    """
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key or not summary:
        return summary

    prompt = (
        f"{_PERSONA}\n\n"
        f"以下のニュースについて、{ai_hint}を作成してください。\n"
        f"【厳守ルール】\n"
        f"・**必ず1文だけ**（句点「。」は1個のみ）\n"
        f"・**40字以内**で完結させること\n"
        f"・見出し・番号・改行・前置きは一切不要\n"
        f"・音楽や言葉のたとえが自然に入るとベスト\n\n"
        f"ニュースタイトル: {title}\n"
        f"概要: {summary}"
    )
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5",
                "max_tokens": 150,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"].strip()
    except Exception as e:
        print(f"  [Claude警告] {e}")
        return summary


# ─── HTML 生成 ────────────────────────────────────────────────────────────────

SOURCE_META = {
    "社会": {
        "label": "社会のニュース", "tab": "社会ニュース",
        "icon": "🏛️", "icon_bg": "bg-blue-50",
        "tag_cls": "bg-blue-50 text-blue-600",
        "ai_hint": "朝のホームルームで生徒に語りかける一言（口語調・50字以内）",
    },
    "奈良": {
        "label": "奈良のニュース", "tab": "奈良",
        "icon": "🦌", "icon_bg": "bg-emerald-50",
        "tag_cls": "bg-emerald-50 text-emerald-600",
        "ai_hint": "地元・奈良の話題として朝礼で紹介できる一言（口語調・50字以内）",
    },
    "国際": {
        "label": "国際ニュース", "tab": "国際",
        "icon": "🌏", "icon_bg": "bg-sky-50",
        "tag_cls": "bg-sky-50 text-sky-600",
        "ai_hint": "高校生に世界の動きを伝える朝礼トーク一言（口語調・50字以内）",
    },
    "教育": {
        "label": "教育ニュース", "tab": "教育",
        "icon": "📚", "icon_bg": "bg-violet-50",
        "tag_cls": "bg-violet-50 text-violet-600",
        "ai_hint": "高校教師が授業改善・学級経営に活かすヒント（具体的アクション・50字以内）",
    },
    "吹奏楽": {
        "label": "吹奏楽・音楽", "tab": "吹奏楽・音楽",
        "icon": "🎺", "icon_bg": "bg-rose-50",
        "tag_cls": "bg-rose-50 text-rose-600",
        "ai_hint": "吹奏楽部顧問として部活指導や演奏技術向上に活かすヒント（50字以内）",
    },
    "国語": {
        "label": "国語・図書", "tab": "国語・図書",
        "icon": "📖", "icon_bg": "bg-amber-50",
        "tag_cls": "bg-amber-50 text-amber-600",
        "ai_hint": "高校国語の授業づくりや図書委員会活動に活かすヒント（50字以内）",
    },
    "文化": {
        "label": "文化・エンタメ", "tab": "文化・エンタメ",
        "icon": "🎭", "icon_bg": "bg-orange-50",
        "tag_cls": "bg-orange-50 text-orange-600",
        "ai_hint": "朝礼や雑談で使える文化・エンタメの話題として一言（口語調・50字以内）",
    },
    "科学": {
        "label": "科学・医療", "tab": "科学・医療",
        "icon": "🔬", "icon_bg": "bg-green-50",
        "tag_cls": "bg-green-50 text-green-600",
        "ai_hint": "理科横断・探究学習のヒントとして授業に活かす一言（50字以内）",
    },
}

def _meta(source_name: str) -> dict:
    for key, val in SOURCE_META.items():
        if key in source_name:
            return val
    return {
        "label": source_name, "tab": source_name,
        "icon": "📰", "icon_bg": "bg-slate-100",
        "tag_cls": "bg-slate-100 text-slate-500",
    }


def _read_time(title: str, summary: str) -> str:
    mins = max(1, round((len(title) + len(summary)) / 400))
    return f"📖 {mins}分"


def build_body(items_by_source: list[tuple], content_type: str = "morning") -> str:
    """記事一覧（教育ブログ 画面03）と同じカードレイアウトで生成する"""
    html = '<ul class="space-y-3">\n'
    for source_name, items in items_by_source:
        if not items:
            continue
        m = _meta(source_name)
        for item in items:
            read_t  = _read_time(item["title"], item["summary"])
            comment = ai_rewrite(item["title"], item["summary"], m.get("ai_hint", ""))
            ai_html = ""
            if comment and comment != item["summary"]:
                ai_html = (
                    f'<p class="text-xs text-brand-500 mt-1 leading-relaxed">'
                    f'💡 {comment}</p>'
                )
            html += f'''<li><a href="{item["link"]}" target="_blank" rel="noopener"
  class="card p-3 flex gap-3 items-start w-full text-left no-underline block"
  data-category="{m["tab"]}">
  <div class="w-16 h-16 rounded-xl {m["icon_bg"]} flex-shrink-0 flex items-center justify-center text-2xl">{m["icon"]}</div>
  <div class="flex-1">
    <div class="flex gap-1 mb-1">
      <span class="tag {m["tag_cls"]}">{m["label"]}</span>
      <span class="tag bg-slate-100 text-slate-500">{read_t}</span>
    </div>
    <p class="text-sm font-semibold text-slate-700 leading-snug">{item["title"]}</p>
    {ai_html}
  </div>
</a></li>
'''
    html += "</ul>\n"
    return html


def build_kanji_html(kanji: dict) -> str:
    """漢字カード — 教育ブログの「featured article」スタイルで表示"""
    return f'''<div class="card mb-1 overflow-hidden">
  <div class="h-20 flex items-center justify-center"
       style="background:linear-gradient(135deg,#fef3c7,#fde68a)">
    <span class="text-4xl">✏️</span>
  </div>
  <div class="p-4">
    <div class="flex gap-2 mb-2">
      <span class="tag bg-amber-50 text-amber-600">漢字検定 準一級</span>
      <span class="tag bg-slate-100 text-slate-500">今日の一問</span>
    </div>
    <p class="text-sm font-bold text-slate-800 mb-1">{kanji["q"]}</p>
    <details>
      <summary class="text-sm text-brand-500 font-semibold mt-2 cursor-pointer select-none">答えを見る →</summary>
      <div class="mt-3 pt-3 border-t border-slate-100">
        <p class="text-base font-bold text-slate-800">読み：{kanji["a"]}</p>
        <p class="text-xs text-slate-500 mt-1">意味：{kanji["meaning"]}</p>
      </div>
    </details>
  </div>
</div>
'''


def generate_html(content_type: str, items_by_source: list[tuple], now: datetime) -> str:
    time_str = now.strftime("%H:%M")
    date_str = now.strftime("%Y年%m月%d日（%a）")

    if content_type == "morning":
        heading  = "朝の記事"
        title    = f"朝の記事 — {now.strftime('%m/%d')}"
        tabs     = ["すべて", "漢字一問", "奈良", "教育", "吹奏楽・音楽"]
    else:
        heading  = "昼の記事"
        title    = f"昼の記事 — {now.strftime('%m/%d')}"
        tabs     = ["すべて", "教育", "吹奏楽・音楽", "国語・図書"]

    tabs_html = "".join(
        f'<button type="button" data-cat="{t}" '
        f'class="tab-btn flex-shrink-0 text-sm font-semibold px-4 py-2 rounded-full '
        f'{"bg-brand-500 text-white" if i == 0 else "bg-slate-100 text-slate-500"}">'
        f'{t}</button>'
        for i, t in enumerate(tabs)
    )

    article_body = build_body(items_by_source, content_type)
    if not article_body or article_body == '<ul class="space-y-3">\n</ul>\n':
        article_body = '<div class="card p-4"><p class="text-sm text-slate-500">現在取得できるニュースがありません。</p></div>'

    kanji_block = build_kanji_html(get_todays_kanji(now)) if content_type == "morning" else ""

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.tailwindcss.com"></script>
<script>tailwind.config={{theme:{{extend:{{colors:{{brand:{{50:'#f0f7ff',100:'#dbeeff',200:'#b6dcfe',300:'#75c0fc',400:'#3aa2f8',500:'#1183e9',600:'#0566c7',700:'#0552a1'}}}},fontFamily:{{sans:['"Noto Sans JP"','sans-serif']}}}}}}}}</script>
<style>
  body{{background:#f1f5f9}}
  .card{{background:white;border-radius:16px;box-shadow:0 2px 8px rgba(0,0,0,.06)}}
  .tag{{font-size:11px;font-weight:600;padding:3px 9px;border-radius:99px;display:inline-block}}
  details summary{{list-style:none}}
  details summary::-webkit-details-marker{{display:none}}
</style>
</head>
<body class="font-sans min-h-screen" style="background:#f1f5f9">

  <!-- ステータスバー -->
  <div class="bg-white px-6 pt-3 pb-2 flex justify-between items-center">
    <span class="text-xs font-semibold text-slate-700">{time_str}</span>
    <span class="text-xs text-slate-400">{date_str}</span>
    <div class="flex gap-1 items-center text-slate-500">
      <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M1 9l2 2c4.97-4.97 13.03-4.97 18 0l2-2C16.93 2.93 7.08 2.93 1 9zm8 8l3 3 3-3c-1.65-1.66-4.34-1.66-6 0zm-4-4l2 2c2.76-2.76 7.24-2.76 10 0l2-2C15.14 9.14 8.87 9.14 5 13z"/></svg>
      <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M15.67 4H14V2h-4v2H8.33C7.6 4 7 4.6 7 5.33v15.33C7 21.4 7.6 22 8.33 22h7.33C16.4 22 17 21.4 17 20.67V5.33C17 4.6 16.4 4 15.67 4z"/></svg>
    </div>
  </div>

  <!-- メインコンテンツ (画面03 記事一覧 と同レイアウト) -->
  <div class="px-5 pt-3 pb-24">

    <!-- タイトル行 -->
    <div class="flex justify-between items-center mb-4">
      <h1 class="text-lg font-bold text-slate-800">{heading}</h1>
      <button type="button" aria-label="ホームへ" onclick="history.back()"
              class="w-11 h-11 bg-slate-100 rounded-full flex items-center justify-center">
        <svg class="w-4 h-4 text-slate-500" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7"/>
        </svg>
      </button>
    </div>

    <!-- フィルタータブ -->
    <div class="flex gap-2 mb-4 overflow-x-auto pb-1">
      {tabs_html}
    </div>

    <!-- 漢字カード (朝のみ) -->
    <div id="kanji-wrap">{kanji_block}</div>

    <!-- 記事リスト -->
    {article_body}

  </div>

  <!-- ボトムナビ -->
  <nav class="fixed bottom-0 left-0 right-0 bg-white border-t border-slate-100
              flex justify-around px-2 py-2 pb-4 z-10">
    <a href="index.html"
       class="flex flex-col items-center gap-1 min-w-[44px] min-h-[44px] justify-center text-slate-400 no-underline">
      <svg class="w-6 h-6" fill="currentColor" viewBox="0 0 24 24"><path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z"/></svg>
      <span class="text-xs">ホーム</span>
    </a>
    <a href="morning.html"
       class="flex flex-col items-center gap-1 min-w-[44px] min-h-[44px] justify-center no-underline {"text-brand-500" if content_type == "morning" else "text-slate-400"}">
      <svg class="w-6 h-6" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364-6.364l-.707.707M6.343 17.657l-.707.707M17.657 17.657l-.707-.707M6.343 6.343l-.707-.707M12 7a5 5 0 100 10 5 5 0 000-10z"/>
      </svg>
      <span class="text-xs {"font-semibold" if content_type == "morning" else ""}">朝</span>
    </a>
    <a href="noon.html"
       class="flex flex-col items-center gap-1 min-w-[44px] min-h-[44px] justify-center no-underline {"text-brand-500" if content_type == "noon" else "text-slate-400"}">
      <svg class="w-6 h-6" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
      </svg>
      <span class="text-xs {"font-semibold" if content_type == "noon" else ""}">昼</span>
    </a>
    <a href="memo.html"
       class="flex flex-col items-center gap-1 min-w-[44px] min-h-[44px] justify-center text-slate-400 no-underline">
      <svg class="w-6 h-6" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/>
      </svg>
      <span class="text-xs">メモ</span>
    </a>
  </nav>

  <!-- ホームインジケーター -->
  <div class="fixed bottom-0 left-0 right-0 h-1 flex items-end justify-center pb-1 pointer-events-none">
    <div class="w-32 h-1 bg-slate-300 rounded-full"></div>
  </div>

  <script>
    /* ── フィルタータブ ── */
    document.querySelectorAll('.tab-btn').forEach(btn => {{
      btn.addEventListener('click', () => {{
        const cat = btn.dataset.cat;
        /* タブの見た目を切り替える */
        document.querySelectorAll('.tab-btn').forEach(b => {{
          b.classList.remove('bg-brand-500', 'text-white');
          b.classList.add('bg-slate-100', 'text-slate-500');
        }});
        btn.classList.remove('bg-slate-100', 'text-slate-500');
        btn.classList.add('bg-brand-500', 'text-white');
        /* カードを絞り込む */
        document.querySelectorAll('[data-category]').forEach(card => {{
          const li = card.closest('li') || card;
          li.style.display =
            (cat === 'すべて' || card.dataset.category === cat) ? '' : 'none';
        }});
        /* 漢字カードは「すべて」「漢字一問」タブのみ表示 */
        const kanjiWrap = document.getElementById('kanji-wrap');
        if (kanjiWrap) {{
          kanjiWrap.style.display =
            (cat === 'すべて' || cat === '漢字一問') ? '' : 'none';
        }}
      }});
    }});
  </script>

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
