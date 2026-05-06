#!/usr/bin/env python3
"""
yuuya-daily-brief — メイン生成スクリプト
RSS取得 → Claude要約 → HTML生成（漢字5問付き）→ LINE送信
"""

import argparse
import json
import os
import re
import textwrap
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import quote

import feedparser
import requests

JST = timezone(timedelta(hours=9))


# ─── RSS フィード定義 ──────────────────────────────────────────────────────────
def _gn(query: str) -> str:
    """Google News RSS URL（日本語クエリを直接渡せるヘルパー）"""
    return f"https://news.google.com/rss/search?hl=ja&gl=JP&ceid=JP:ja&q={quote(query)}"

MORNING_FEEDS = [
    # NHK奈良ローカルニュース（地元密着・千葉など他県が混入しない）
    ("奈良のニュース",  "https://www3.nhk.or.jp/lnews/nara/rss/03.xml",              2),
    # 奈良×教育×高校に絞ったGoogle News
    ("教育ニュース",    _gn("奈良 高校教育 OR 音楽教育 OR 国語教育"),                2),
    # 吹奏楽・音楽教育（音楽教育まで広げる）
    ("音楽教育",        _gn("吹奏楽 OR 音楽教育 高校 OR コンクール"),                2),
]

NOON_FEEDS = [
    # NHK文化・科学（教育・読書関連が多い）
    ("教育ニュース",    "https://www3.nhk.or.jp/rss/news/cat5.xml",                  2),
    # 吹奏楽・音楽教育
    ("吹奏楽・音楽",   _gn("吹奏楽 コンクール OR 音楽教育"),                        2),
    # 国語教育・読書・図書館
    ("国語・図書",     _gn("国語教育 OR 読書教育 OR 図書館 高校 OR 学校"),           2),
]

# ─── 漢字検定準一級 日替わり5問 ──────────────────────────────────────────────

KANJI_QUESTIONS = [
    # ── 読み問題 ──
    {"q": "「齟齬」の読みは？",           "a": "そご",              "meaning": "物事がうまくかみ合わないこと"},
    {"q": "「蹉跌」の読みは？",           "a": "さてつ",            "meaning": "つまずき、失敗すること"},
    {"q": "「逡巡」の読みは？",           "a": "しゅんじゅん",      "meaning": "ためらって前に進めないこと"},
    {"q": "「忸怩」の読みは？",           "a": "じくじ",            "meaning": "恥ずかしく思うさま"},
    {"q": "「闊歩」の読みは？",           "a": "かっぽ",            "meaning": "大股で堂々と歩くこと"},
    {"q": "「恬淡」の読みは？",           "a": "てんたん",          "meaning": "物事にこだわらず、さっぱりしているさま"},
    {"q": "「蒙昧」の読みは？",           "a": "もうまい",          "meaning": "道理に暗く、無知なさま"},
    {"q": "「慫慂」の読みは？",           "a": "しょうよう",        "meaning": "すすめてそうさせること"},
    {"q": "「杳として」の読みは？",       "a": "ようとして",        "meaning": "遠くて消息が不明なさま"},
    {"q": "「矍鑠」の読みは？",           "a": "かくしゃく",        "meaning": "老いても元気で丈夫なさま"},
    {"q": "「啻に」の読みは？",           "a": "ただに",            "meaning": "ただそれだけでなく（〜のみならず）"},
    {"q": "「憧憬」の読みは？",           "a": "しょうけい",        "meaning": "あこがれること"},
    {"q": "「諧謔」の読みは？",           "a": "かいぎゃく",        "meaning": "ユーモア、冗談"},
    {"q": "「贖罪」の読みは？",           "a": "しょくざい",        "meaning": "罪をつぐなうこと"},
    {"q": "「嗜好」の読みは？",           "a": "しこう",            "meaning": "好んで楽しむこと"},
    {"q": "「逼迫」の読みは？",           "a": "ひっぱく",          "meaning": "さしせまって余裕がなくなること"},
    {"q": "「慇懃」の読みは？",           "a": "いんぎん",          "meaning": "礼儀正しく丁寧なさま"},
    {"q": "「幽邃」の読みは？",           "a": "ゆうすい",          "meaning": "奥深く静かで趣のあるさま"},
    {"q": "「澎湃」の読みは？",           "a": "ほうはい",          "meaning": "勢いが盛んに起こるさま"},
    {"q": "「蹌踉」の読みは？",           "a": "そうろう",          "meaning": "よろよろと歩くさま"},
    {"q": "「饗宴」の読みは？",           "a": "きょうえん",        "meaning": "盛大なもてなしの宴"},
    {"q": "「僭越」の読みは？",           "a": "せんえつ",          "meaning": "身分や立場を越えて出過ぎること"},
    {"q": "「杞憂」の読みは？",           "a": "きゆう",            "meaning": "必要のない心配をすること"},
    {"q": "「蟄居」の読みは？",           "a": "ちっきょ",          "meaning": "家の中に閉じこもること"},
    {"q": "「捧腹絶倒」の読みは？",       "a": "ほうふくぜっとう",  "meaning": "腹を抱えて大笑いすること"},
    {"q": "「頓挫」の読みは？",           "a": "とんざ",            "meaning": "物事が途中で行き詰まること"},
    {"q": "「罵倒」の読みは？",           "a": "ばとう",            "meaning": "激しくののしること"},
    {"q": "「縹渺」の読みは？",           "a": "ひょうびょう",      "meaning": "広くはるかに広がるさま"},
    {"q": "「驥尾に付す」の読みは？",     "a": "きびにふす",        "meaning": "すぐれた人に従って功を得ること"},
    {"q": "「諄諄」の読みは？",           "a": "じゅんじゅん",      "meaning": "丁寧にくり返し言い聞かせるさま"},
    # ── 追加（読み） ──
    {"q": "「跋扈」の読みは？",           "a": "ばっこ",            "meaning": "権力をかさに着てのさばること"},
    {"q": "「欺瞞」の読みは？",           "a": "ぎまん",            "meaning": "だますこと"},
    {"q": "「傀儡」の読みは？",           "a": "かいらい",          "meaning": "あやつり人形。他人の意のままになる人"},
    {"q": "「渾身」の読みは？",           "a": "こんしん",          "meaning": "全身・全力"},
    {"q": "「韜晦」の読みは？",           "a": "とうかい",          "meaning": "才能・地位などを隠すこと"},
    {"q": "「蹂躙」の読みは？",           "a": "じゅうりん",        "meaning": "ふみにじること"},
    {"q": "「纏綿」の読みは？",           "a": "てんめん",          "meaning": "離れられないでまとわりつくさま"},
    {"q": "「雌伏」の読みは？",           "a": "しふく",            "meaning": "じっと機会を待ちながら耐え忍ぶこと"},
    {"q": "「捲土重来」の読みは？",       "a": "けんどちょうらい",  "meaning": "一度敗れた者が再び勢力を盛り返すこと"},
    {"q": "「狡猾」の読みは？",           "a": "こうかつ",          "meaning": "ずる賢いさま"},
    {"q": "「冗漫」の読みは？",           "a": "じょうまん",        "meaning": "むだに長くてだれること"},
    {"q": "「怜悧」の読みは？",           "a": "れいり",            "meaning": "頭の働きが鋭く賢いこと"},
    {"q": "「嶮峻」の読みは？",           "a": "けんしゅん",        "meaning": "山が険しくそびえるさま"},
    {"q": "「懶惰」の読みは？",           "a": "らんだ",            "meaning": "なまけること"},
    {"q": "「彷徨」の読みは？",           "a": "ほうこう",          "meaning": "あてもなくさまよい歩くこと"},
    {"q": "「鼎談」の読みは？",           "a": "ていだん",          "meaning": "三人で向かい合って話し合うこと"},
    {"q": "「鬱勃」の読みは？",           "a": "うつぼつ",          "meaning": "気力が盛んに湧き起こるさま"},
    {"q": "「掣肘」の読みは？",           "a": "せいちゅう",        "meaning": "横から口出しして邪魔をすること"},
    {"q": "「邂逅」の読みは？",           "a": "かいこう",          "meaning": "思いがけなく出会うこと"},
    {"q": "「咆哮」の読みは？",           "a": "ほうこう",          "meaning": "猛獣などが激しく吠えること"},
    {"q": "「慟哭」の読みは？",           "a": "どうこく",          "meaning": "声をあげて激しく泣くこと"},
    {"q": "「懊悩」の読みは？",           "a": "おうのう",          "meaning": "思い悩み苦しむこと"},
    {"q": "「旺盛」の読みは？",           "a": "おうせい",          "meaning": "勢いが盛んなさま"},
    {"q": "「淳朴」の読みは？",           "a": "じゅんぼく",        "meaning": "純粋でかざり気がないこと"},
    {"q": "「懈怠」の読みは？",           "a": "けたい",            "meaning": "怠けること"},
    {"q": "「憐憫」の読みは？",           "a": "れんびん",          "meaning": "かわいそうに思うこと"},
    {"q": "「嗚咽」の読みは？",           "a": "おえつ",            "meaning": "声をつまらせて泣くこと"},
    {"q": "「翻弄」の読みは？",           "a": "ほんろう",          "meaning": "思うままにもてあそぶこと"},
    {"q": "「錯綜」の読みは？",           "a": "さくそう",          "meaning": "いり混じって複雑になること"},
    {"q": "「忖度」の読みは？",           "a": "そんたく",          "meaning": "他人の心を推しはかること"},
    # ── 書き取り問題 ──
    {"q": "「かっとう（葛藤）」を漢字で書くと？", "a": "葛藤",       "meaning": "心の中の相反する欲求の争い"},
    {"q": "「しんし（紳士）」を漢字で書くと？",   "a": "紳士",       "meaning": "礼儀正しく品位ある男性"},
    {"q": "「しっぺい（疾病）」を漢字で書くと？", "a": "疾病",       "meaning": "病気"},
    {"q": "「えんかつ（円滑）」を漢字で書くと？", "a": "円滑",       "meaning": "物事がすらすらと進むさま"},
    {"q": "「きびす（踵）」を漢字で書くと？",     "a": "踵",         "meaning": "かかと"},
    {"q": "「こうよう（紅葉）」を漢字で書くと？", "a": "紅葉",       "meaning": "秋に葉が赤や黄に色づくこと"},
    {"q": "「さんじゅつ（算術）」を漢字で書くと？","a": "算術",      "meaning": "計算の方法・技術"},
    {"q": "「もうらく（耄碌）」を漢字で書くと？", "a": "耄碌",       "meaning": "年をとって頭や体が衰えること"},
    {"q": "「かんか（陥穽）」の「陥穽」の読みは？","a": "かんせい",  "meaning": "落とし穴。計略のわな"},
    {"q": "「とりょう（塗料）」を漢字で書くと？", "a": "塗料",       "meaning": "塗るための材料"},
    # ── 四字熟語 ──
    {"q": "「一期一会」の読みは？",        "a": "いちごいちえ",     "meaning": "一生に一度限りの出会いを大切にすること"},
    {"q": "「傍若無人」の読みは？",        "a": "ぼうじゃくぶじん", "meaning": "人目を気にせず勝手に振る舞うさま"},
    {"q": "「付和雷同」の読みは？",        "a": "ふわらいどう",     "meaning": "自分の考えがなく他人の意見に同調すること"},
    {"q": "「暗中模索」の読みは？",        "a": "あんちゅうもさく", "meaning": "手がかりなしに試行錯誤すること"},
    {"q": "「五里霧中」の読みは？",        "a": "ごりむちゅう",     "meaning": "方針が立たず迷っている状態"},
    {"q": "「玉石混淆」の読みは？",        "a": "ぎょくせきこんこう","meaning": "すぐれたものと劣ったものが混じり合っていること"},
    {"q": "「臥薪嘗胆」の読みは？",        "a": "がしんしょうたん", "meaning": "目的のために辛苦に耐え続けること"},
    {"q": "「含蓄」の読みは？",            "a": "がんちく",         "meaning": "言葉や文章に深い意味が含まれていること"},
    {"q": "「閑話休題」の読みは？",        "a": "かんわきゅうだい", "meaning": "それはさておき（話を本題に戻すとき）"},
    {"q": "「切磋琢磨」の読みは？",        "a": "せっさたくま",     "meaning": "互いに励まし合って向上すること"},
    {"q": "「狷介孤高」の読みは？",        "a": "けんかいここう",   "meaning": "頑固で世間に迎合しない高い態度"},
    {"q": "「佳人薄命」の読みは？",        "a": "かじんはくめい",   "meaning": "美人は運命に恵まれないことが多い"},
    {"q": "「磊落豪快」の読みは？",        "a": "らいらくごうかい", "meaning": "心が広く、こせこせしないさま"},
    {"q": "「百花繚乱」の読みは？",        "a": "ひゃっかりょうらん","meaning": "多くの花が咲き乱れること。才能ある人が多く現れること"},
    {"q": "「一朝一夕」の読みは？",        "a": "いっちょういっせき","meaning": "ごく短い期間"},
    {"q": "「奇想天外」の読みは？",        "a": "きそうてんがい",   "meaning": "思いもよらない奇抜な発想"},
    {"q": "「虚心坦懐」の読みは？",        "a": "きょしんたんかい", "meaning": "わだかまりなく、素直な心でいること"},
    {"q": "「意気軒昂」の読みは？",        "a": "いきけんこう",     "meaning": "意気込みが高まって元気なさま"},
    {"q": "「巧言令色」の読みは？",        "a": "こうげんれいしょく","meaning": "口先だけで飾り、誠意に欠けること"},
    {"q": "「和光同塵」の読みは？",        "a": "わこうどうじん",   "meaning": "才能を隠して俗世間に交わること"},
    # ── 類義語・対義語 ──
    {"q": "「敷衍（ふえん）」の意味は？",  "a": "敷き広げて説明すること","meaning": "内容を詳しく説き明かすこと"},
    {"q": "「忖度」の類義語は？",          "a": "推量・斟酌（しんしゃく）","meaning": "他人の気持ちを推しはかること"},
    {"q": "「逡巡」の対義語は？",          "a": "決断・断行",        "meaning": "ためらわず行動すること"},
    {"q": "「冗漫」の対義語は？",          "a": "簡潔・端的",        "meaning": "むだなく短くまとめてあること"},
    {"q": "「恬淡」の類義語は？",          "a": "淡泊・超然",        "meaning": "こだわりのなく淡々としているさま"},
]


def get_todays_kanji(now: datetime) -> list[dict]:
    """今日の漢字 5問を返す（日付ベースで循環）"""
    n = len(KANJI_QUESTIONS)
    start = (now.timetuple().tm_yday * 5) % n
    return [KANJI_QUESTIONS[(start + i) % n] for i in range(5)]


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
あなたは山中優弥（26歳・高校国語教師・吹奏楽部顧問、奈良県、教員5年目）として語る。

【核心的価値観】
- 「変わり続けることで、変わらないものを守る」が哲学の中心
- 「余韻（鳴り終わった後も残る響き）」が言語・音楽・人間関係の最高基準
- 「通奏低音」＝変化する状況の中でも自分の軸として低音で鳴り続けるもの
- 「間（ま）」は欠如ではなく充満。沈黙は考えている表れ
- 教室の沈黙・廊下の足音・会話のリズム——すべてを音楽として聴く感性

【言語スタイル】
好む語彙：通奏低音、余韻、間（ま）、変化、移行、境界、彩る、伴走する、聴く（聞くでなく）、足場、軸、鳴らし続ける
避ける表現：「絶対」「必ず」「当然」などの断定語、感嘆符の多用、「すごい」「やばい」などの俗語
比喩の源泉：
  - 人間関係→「ハーモニー」「音が出会う」「リズムを合わせる」
  - 成長→「通奏低音」「チューニング」「音が鳴り始める」
  - 教育→「足場」「発射台」「余白」

【教育の哲学】
良い授業＝生徒が「自分で考えた」と感じる瞬間を作れたかどうか。正解を教えることより問いが残ることを重視。
憧れ：米津玄師・星野源・宮沢賢治・藤原聡（「受け取ってもらって初めて完成する」哲学に共鳴）

【語り口の特徴】
断言しない着地（「〜という方向を取りたい」「〜と考えています」）
一言に余韻と深みを持たせる。笑いの中に気づきを潜ませる。ポップで温かく、でも軽くない。"""

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
        f"以下のニュースについて、{ai_hint}を作成してください。\n\n"
        f"【厳守ルール】\n"
        f"・必ず**1文だけ**（句点「。」または「——」で終わる、1文のみ）\n"
        f"・**45字以内**で完結させること\n"
        f"・見出し・番号・改行・記号・前置きは一切不要\n"
        f"・上記の語彙・比喩を自然に使い、余韻が残る一言にする\n"
        f"・断言より「〜という方向では」「〜とも聴こえる」という着地感を\n\n"
        f"ニュース: {title}\n"
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
        "ai_hint": "朝のホームルームで生徒の心に余韻を残す一言を、山中優弥の口調で",
    },
    "奈良": {
        "label": "奈良のニュース", "tab": "奈良",
        "icon": "🦌", "icon_bg": "bg-emerald-50",
        "tag_cls": "bg-emerald-50 text-emerald-600",
        "ai_hint": "奈良への愛着と教師の視点を重ねた、朝礼で語れる一言を、山中優弥の口調で",
    },
    "国際": {
        "label": "国際ニュース", "tab": "国際",
        "icon": "🌏", "icon_bg": "bg-sky-50",
        "tag_cls": "bg-sky-50 text-sky-600",
        "ai_hint": "世界の動きを高校生に届ける、余韻のある朝礼トーク一言を、山中優弥の口調で",
    },
    "教育": {
        "label": "教育ニュース", "tab": "教育",
        "icon": "📚", "icon_bg": "bg-violet-50",
        "tag_cls": "bg-violet-50 text-violet-600",
        "ai_hint": "授業や学級経営の「足場」として使える、静かに深い気づきの一言を、山中優弥の口調で",
    },
    "吹奏楽": {
        "label": "吹奏楽・音楽", "tab": "吹奏楽・音楽",
        "icon": "🎺", "icon_bg": "bg-rose-50",
        "tag_cls": "bg-rose-50 text-rose-600",
        "ai_hint": "部員の通奏低音を引き出す指導の視点で、音楽の余韻が残る一言を、山中優弥の口調で",
    },
    "国語": {
        "label": "国語・図書", "tab": "国語・図書",
        "icon": "📖", "icon_bg": "bg-amber-50",
        "tag_cls": "bg-amber-50 text-amber-600",
        "ai_hint": "言葉と読書の間にある余白を大切にした、授業や図書委員会への一言を、山中優弥の口調で",
    },
    "文化": {
        "label": "文化・エンタメ", "tab": "文化・エンタメ",
        "icon": "🎭", "icon_bg": "bg-orange-50",
        "tag_cls": "bg-orange-50 text-orange-600",
        "ai_hint": "文化・エンタメを入口にして生徒の感性に届く、朝礼での一言を、山中優弥の口調で",
    },
    "科学": {
        "label": "科学・医療", "tab": "科学・医療",
        "icon": "🔬", "icon_bg": "bg-green-50",
        "tag_cls": "bg-green-50 text-green-600",
        "ai_hint": "探究学習の余白として使える、不思議さが残る一言を、山中優弥の口調で",
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


def build_kanji_html(kanjis: list[dict]) -> str:
    """漢字カード — 今日の5問を1枚のカードにまとめて表示"""
    items_html = ""
    for i, k in enumerate(kanjis, 1):
        items_html += f'''
    <div class="py-3 {'border-t border-slate-100' if i > 1 else ''}">
      <p class="text-sm font-bold text-slate-800 mb-1">Q{i}. {k["q"]}</p>
      <details>
        <summary class="text-xs text-brand-500 font-semibold cursor-pointer select-none">答えを見る ▶</summary>
        <div class="mt-2 bg-amber-50 rounded-lg p-3">
          <p class="text-sm font-bold text-slate-800">→ {k["a"]}</p>
          <p class="text-xs text-slate-500 mt-1">{k["meaning"]}</p>
        </div>
      </details>
    </div>'''
    return f'''<div class="card mb-3 overflow-hidden">
  <div class="px-4 py-3 flex items-center gap-3"
       style="background:linear-gradient(135deg,#fef3c7,#fde68a)">
    <span class="text-2xl">✏️</span>
    <div>
      <span class="text-xs font-bold text-amber-800">漢字検定 準一級</span>
      <p class="text-sm font-bold text-amber-900">今日の5問</p>
    </div>
  </div>
  <div class="px-4 pb-3">{items_html}
  </div>
</div>
'''


def generate_html(content_type: str, items_by_source: list[tuple], now: datetime) -> str:
    date_str = now.strftime("%-m月%-d日（%a）")

    if content_type == "morning":
        heading  = "朝の記事"
        title    = f"朝の記事 — {now.strftime('%-m/%-d')}"
        tabs     = ["すべて", "漢字5問", "奈良", "教育", "音楽教育"]
    else:
        heading  = "昼の記事"
        title    = f"昼の記事 — {now.strftime('%-m/%-d')}"
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

  <!-- メインコンテンツ -->
  <div class="px-5 pt-5 pb-24">

    <!-- タイトル行 -->
    <div class="flex justify-between items-center mb-4">
      <div>
        <h1 class="text-lg font-bold text-slate-800">{heading}</h1>
        <p class="text-xs text-slate-400">{date_str}</p>
      </div>
      <div class="flex gap-2 items-center">
        <a href="archive.html"
           class="text-xs font-semibold text-slate-400 px-3 py-1.5 bg-slate-100 rounded-full no-underline">
          履歴
        </a>
        <button type="button" aria-label="ホームへ" onclick="location.href='index.html'"
                class="w-11 h-11 bg-slate-100 rounded-full flex items-center justify-center">
          <svg class="w-4 h-4 text-slate-500" fill="currentColor" viewBox="0 0 24 24">
            <path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z"/>
          </svg>
        </button>
      </div>
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
        /* 漢字カードは「すべて」「漢字5問」タブのみ表示 */
        const kanjiWrap = document.getElementById('kanji-wrap');
        if (kanjiWrap) {{
          kanjiWrap.style.display =
            (cat === 'すべて' || cat === '漢字5問') ? '' : 'none';
        }}
      }});
    }});
  </script>

</body>
</html>"""


# ─── アーカイブ管理 ────────────────────────────────────────────────────────────

def save_archive(content_type: str, html: str, now: datetime) -> str:
    """
    日付付きHTMLファイルを保存し archive.json を更新する。
    戻り値: 保存したファイル名（例: morning-20260506.html）
    """
    date_key   = now.strftime("%Y%m%d")
    date_label = now.strftime("%-m月%-d日")
    day_jp     = ["月","火","水","木","金","土","日"][now.weekday()]
    filename   = f"{content_type}-{date_key}.html"
    filepath   = f"docs/{filename}"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"アーカイブ保存: {filepath}")

    archive_path = Path("docs/archive.json")
    archive: list[dict] = []
    if archive_path.exists():
        try:
            archive = json.loads(archive_path.read_text(encoding="utf-8"))
        except Exception:
            archive = []

    iso_date = now.strftime("%Y-%m-%d")
    entry = next((e for e in archive if e.get("date") == iso_date), None)
    if entry is None:
        entry = {"date": iso_date, "label": f"{date_label}（{day_jp}）"}
        archive.insert(0, entry)

    entry[content_type] = filename
    archive.sort(key=lambda e: e["date"], reverse=True)
    archive_path.write_text(
        json.dumps(archive[:90], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"archive.json 更新: {iso_date} / {content_type}")
    return filename


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

    # 最新版（morning.html / noon.html）を上書き保存
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML 保存: {out_path}")

    # 日付付きアーカイブを保存 + archive.json 更新
    save_archive(content_type, html, now)

    token   = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
    user_id = os.environ["LINE_USER_ID"]
    label   = "朝" if content_type == "morning" else "昼"
    date_label = now.strftime("%-m/%-d")
    base_url = "https://yamanaka120121-design.github.io/yuuya-daily-brief"
    today_url   = f"{base_url}/{content_type}.html"
    archive_url = f"{base_url}/archive.html"
    message = (
        f"【{date_label} {label}の記事】\n"
        f"{today_url}\n\n"
        f"📚 過去の記事\n{archive_url}"
    )
    send_line(token, user_id, message)


if __name__ == "__main__":
    main()
