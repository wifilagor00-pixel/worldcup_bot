"""
5-Video Daily World Cup Pipeline
=================================
1. 赛事回顾 (Match Review)      5. 精彩五佳 (Top 5 Moments)
2. 赛事预测 (Match Prediction)   4. 历史趣闻 (Historic Trivia)
3. 球星故事 (Star Story)

No API keys needed — uses Wikimedia Commons for images.
Optional: set PEXELS_KEY env var for better quality images.
"""

import asyncio, json, os, random, re
from datetime import datetime
from pathlib import Path

import requests
from moviepy import (AudioFileClip, ColorClip, CompositeVideoClip,
                      ImageClip, concatenate_videoclips, vfx)
import edge_tts

# ═══════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════

VOICE      = "zh-CN-YunjianNeural"
W, H, FPS  = 1080, 1920, 24                # 9:16 vertical
SEG_DUR    = 30                              # seconds per video
IMG_COUNT  = 4                               # images per video
PEXELS_KEY = os.environ.get("PEXELS_KEY", "")
ROOT       = Path(__file__).parent
OUT        = ROOT / "output"
TMP        = ROOT / "tmp"
OUT.mkdir(exist_ok=True); TMP.mkdir(exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════
# IMAGE SEARCH  (Wikimedia → no key | Pexels → needs key)
# ═══════════════════════════════════════════════════════════════════════

def search_images(query, n=IMG_COUNT):
    """Return list of CC image URLs. Tries Pexels first, then Wikimedia."""
    if PEXELS_KEY:
        urls = _pexels(query, n)
        if urls: return urls
    return _wikimedia(query, n)


def _pexels(query, n):
    try:
        r = requests.get("https://api.pexels.com/v1/search", timeout=10,
                         headers={"Authorization": PEXELS_KEY},
                         params={"query": query, "per_page": n, "orientation": "portrait"})
        return [p["src"]["large"] for p in r.json().get("photos", [])]
    except Exception:
        return []


def _wikimedia(query, n):
    try:
        api = "https://commons.wikimedia.org/w/api.php"
        # search for files
        sr = requests.get(api, timeout=15, params={
            "action": "query", "list": "search", "srsearch": query,
            "srnamespace": 6, "format": "json", "srlimit": n * 3,
        }).json()
        titles = [r["title"] for r in sr["query"]["search"]]
        # get image URLs
        ir = requests.get(api, timeout=15, params={
            "action": "query", "titles": "|".join(titles),
            "prop": "imageinfo", "iiprop": "url|size", "format": "json",
        }).json()
        urls = []
        for p in ir["query"]["pages"].values():
            ii = p.get("imageinfo", [])
            if ii and ii[0]["width"] > 400:
                urls.append(ii[0]["url"])
        return urls[:n]
    except Exception:
        return []


def download(url, path):
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        path.write_bytes(r.content)
        return path
    except Exception:
        return None

# ═══════════════════════════════════════════════════════════════════════
# KEN BURNS SLIDESHOW
# ═══════════════════════════════════════════════════════════════════════

def ken_burns(img_path, duration):
    """Single clip: image with slow random pan over a 9:16 canvas."""
    clip = ImageClip(str(img_path), duration=duration)
    scale = random.uniform(1.35, 1.55)
    clip = clip.resized(width=int(W * scale))

    max_x = max(clip.w - W, 0)
    max_y = max(clip.h - H, 0)
    sx, sy = random.randint(0, max_x), random.randint(0, max_y)
    ex, ey = random.randint(0, max_x), random.randint(0, max_y)

    def pos(t):
        p = t / duration if duration > 0 else 0
        return (-(sx + (ex - sx) * p), -(sy + (ey - sy) * p))

    clip = clip.with_position(pos)
    bg   = ColorClip((W, H), color=(0, 0, 0), duration=duration)
    return CompositeVideoClip([bg, clip])


def build_slideshow(images, audio_path, output_path):
    """Ken Burns on each image → fade in/out → concat → attach audio."""
    audio = AudioFileClip(str(audio_path))
    dur   = audio.duration
    seg   = dur / len(images)

    clips = []
    for img in images:
        c = ken_burns(img, seg)
        c = c.with_effects([vfx.FadeIn(0.6), vfx.FadeOut(0.6)])
        clips.append(c)

    video = concatenate_videoclips(clips)
    video = video.with_audio(audio)
    video.write_videofile(str(output_path), fps=FPS, logger=None)

# ═══════════════════════════════════════════════════════════════════════
# TTS
# ═══════════════════════════════════════════════════════════════════════

async def tts(text, out):
    await edge_tts.Communicate(text, VOICE).save(str(out))

# ═══════════════════════════════════════════════════════════════════════
# TOPIC SCRIPT GENERATORS  (each ~120-150 chars ≈ 30s spoken)
# ═══════════════════════════════════════════════════════════════════════

# -- shared scraper for live results ------------------------------------

def _scrape_results():
    """Reuse the GMA News scraper for live match data."""
    try:
        r = requests.get(
            "https://www.gmanetwork.com/news/sports/football/991493/"
            "2026-fifa-world-cup-updates-and-results-june-15-2026/story/",
            timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        matches = re.findall(
            r"([A-Z][\w\s&\.'-]+?)\s+(\d+)\s*[–\-]\s*(\d+)\s+([A-Z][\w\s&\.'-]+?)(?:<|\.|,|\n)",
            r.text)
        seen = set()
        items = []
        for h, hg, ag, a in matches:
            h, a = h.strip(), a.strip()
            if len(h) > 30 or len(a) > 30:
                continue
            key = (h, a)
            if key not in seen:
                seen.add(key)
                items.append(f"{h}{hg}比{ag}{a}")
        return items
    except Exception:
        return []


def script_match_review():
    """Passionate recap of latest match results."""
    results = _scrape_results()
    today   = datetime.now().strftime("%m月%d日")
    head    = f"2026世界杯最新战报！{today}，比赛战火纷飞！"
    body    = "，".join(results[:5]) if results else "多场精彩对决轮番上演，进球不断，悬念迭起！"
    tail    = "更多精彩，敬请锁定下一轮赛事回顾！"
    return head + body + "。" + tail


def script_match_prediction():
    """Upcoming match preview with bold predictions."""
    teams = ["巴西", "德国", "阿根廷", "法国", "荷兰", "日本",
             "瑞典", "科特迪瓦", "澳大利亚", "摩洛哥"]
    t1, t2 = random.sample(teams, 2)
    return (f"世界杯赛事预测！接下来{t1}对阵{t2}的比赛万众瞩目。"
            f"{t1}攻击线火力全开，而{t2}防守固若金汤。"
            f"这将是一场矛与盾的终极对决！"
            f"谁能笑到最后？让我们拭目以待！")


STAR_STORIES = [
    "世界杯球星故事！基利安姆巴佩，法国超级前锋，速度如闪电，突破如利剑。"
    "从摩纳哥少年到世界冠军，他用一次次惊艳表现征服全球球迷。"
    "本届世界杯，他再次带领法国队冲击荣耀，传奇仍在继续！",

    "世界杯球星故事！维尼修斯，巴西新一代天才，脚下技术出神入化。"
    "他从小在街头踢球，用天赋和汗水征服了世界。"
    "每一次触球都是一次艺术表演，他就是巴西足球的未来！",

    "世界杯球星故事！朱德贝林厄姆，英格兰中场核心，年纪轻轻却沉稳大气。"
    "他在场上无所不能，能攻善守，是教练最信任的战术支点。"
    "这届世界杯，他承载着英格兰的全部希望！",

    "世界杯球星故事！贾马尔穆西亚拉，德国队的新生代领袖。"
    "他拥有令人惊叹的盘带技术和冷静的门前嗅觉。"
    "从拜仁青训到世界杯舞台，他的成长之路激励着无数年轻球员！",

    "世界杯球星故事！久保健英，日本队的中场魔术师。"
    "他身材不高却技术精湛，被誉为日本梅西。"
    "这届世界杯上，他用一次次精妙传球证明亚洲足球的实力！",
]


def script_star_story():
    """Pick a random star profile."""
    return random.choice(STAR_STORIES)


HISTORIC_TRIVIA = [
    "世界杯历史趣闻！你知道最快进球纪录是多少吗？"
    "二零零二年，土耳其前锋哈坎苏克在季军争夺战中，开场仅十一秒就攻破韩国队大门！"
    "这个纪录至今无人能破，堪称世界杯史上的闪电奇迹！",

    "世界杯历史趣闻！一九五零年世界杯决赛，乌拉圭在马拉卡纳球场击败巴西。"
    "现场近二十万观众见证了这场被称为马拉卡纳惨案的经典对决。"
    "巴西人至今提起仍心有余悸，这就是足球的魅力与残酷！",

    "世界杯历史趣闻！二零零六年齐达内在决赛中的头顶马特拉齐事件。"
    "这位法国传奇用一张红牌结束了自己的世界杯生涯。"
    "那一刻成为足球史上最具争议的瞬间之一，令人唏嘘不已！",

    "世界杯历史趣闻！一九九零年喀麦隆击败阿根廷，成为首支在世界杯击败卫冕冠军的非洲球队。"
    "这支非洲雄狮用顽强的斗志震惊了世界足坛。"
    "从此，非洲足球在世界舞台上崭露头角！",

    "世界杯历史趣闻！二零零二年世界杯，韩国队创造了亚洲球队最佳战绩。"
    "他们一路击败意大利、西班牙等强敌，最终杀入四强。"
    "那支红魔军团的故事至今仍是亚洲足球的骄傲！",
]


def script_historic_trivia():
    """Random World Cup historical fun fact."""
    return random.choice(HISTORIC_TRIVIA)


def script_top5_moments():
    """Top 5 moments so far — dynamic mix."""
    results = _scrape_results()
    today   = datetime.now().strftime("%m月%d日")
    head    = f"世界杯精彩五佳！{today}，为您盘点本届赛事最精彩瞬间！"
    moments = (
        results[:5] if len(results) >= 3
        else ["精彩扑救令人拍案叫绝", "绝妙进球点燃全场激情",
              "团队配合行云流水", "逆转获胜荡气回肠", "球迷狂欢震撼人心"]
    )
    body = "！".join(f"第{moments.index(m)+1 if isinstance(m, str) else i+1}大精彩，{m}"
                     for i, m in enumerate(moments[:5]))
    return head + body + "！这就是今天的精彩五佳，明天再见！"


# ═══════════════════════════════════════════════════════════════════════
# TOPIC REGISTRY
# ═══════════════════════════════════════════════════════════════════════

TOPICS = [
    {"slug": "1-match-review",     "title": "赛事回顾",
     "desc": "2026世界杯每日战报 | 最新比分与赛果速递",
     "kw":   "football world cup match stadium celebration",
     "gen":  script_match_review},

    {"slug": "2-match-prediction", "title": "赛事预测",
     "desc": "世界杯比赛前瞻 | 独家分析与比分预测",
     "kw":   "soccer player action stadium crowd fans",
     "gen":  script_match_prediction},

    {"slug": "3-star-story",       "title": "球星故事",
     "desc": "世界杯球星传奇 | 绿茵场上的闪耀明星",
     "kw":   "football star player portrait celebration",
     "gen":  script_star_story},

    {"slug": "4-historic-trivia",  "title": "历史趣闻",
     "desc": "世界杯冷知识 | 你不知道的足球历史故事",
     "kw":   "world cup history trophy classic football vintage",
     "gen":  script_historic_trivia},

    {"slug": "5-top5-moments",     "title": "精彩五佳",
     "desc": "世界杯五佳瞬间 | 每日最精彩的赛场时刻",
     "kw":   "soccer goal celebration amazing moment action",
     "gen":  script_top5_moments},
]

# ═══════════════════════════════════════════════════════════════════════
# PIPELINE
# ═══════════════════════════════════════════════════════════════════════

async def process_topic(topic):
    """End-to-end: script -> TTS -> images -> slideshow -> output."""
    slug, kw, gen = topic["slug"], topic["kw"], topic["gen"]

    print(f"  [{slug}] script...")
    text = gen()

    print(f"  [{slug}] TTS...")
    audio_path = TMP / f"{slug}.mp3"
    await tts(text, audio_path)

    print(f"  [{slug}] images...")
    urls = search_images(kw)
    if not urls:
        urls = search_images("soccer football stadium", IMG_COUNT)

    images = []
    for i, url in enumerate(urls[:IMG_COUNT]):
        path = download(url, TMP / f"{slug}_{i}.jpg")
        if path:
            images.append(path)

    if not images:
        fallback = ROOT / "test.jpg"
        if fallback.exists():
            images = [fallback] * IMG_COUNT
        else:
            print(f"    [{slug}] SKIP - no images")
            return None

    print(f"  [{slug}] render ({len(images)} imgs)...")
    output_path = OUT / f"{slug}.mp4"
    build_slideshow(images, audio_path, output_path)
    print(f"  [{slug}] -> {output_path}")
    return output_path


async def main():
    print("=" * 50)
    print(f"World Cup 5-Video Pipeline - {datetime.now():%Y-%m-%d}")
    print("=" * 50)

    # fast topics first (no scrape), then data-dependent
    order = [2, 3, 1, 0, 4]  # prediction, star, trivia, review, top5
    results = []
    for i in order:
        results.append(await process_topic(TOPICS[i]))

    print()
    print("=" * 50)
    print("DONE. Upload info saved to output/upload.txt")
    print("=" * 50)
    with open(OUT / "upload.txt", "w", encoding="utf-8") as f:
        for topic in TOPICS:
            f.write(f"{topic['slug']}.mp4\n")
            f.write(f"  Title: {topic['title']}\n")
            f.write(f"  Desc:  {topic['desc']}\n\n")
            print(f"  {topic['slug']}.mp4  [{topic['slug'].split('-',1)[1]}]")


if __name__ == "__main__":
    asyncio.run(main())
