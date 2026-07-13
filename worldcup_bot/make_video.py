import asyncio, re
from datetime import datetime
from moviepy import AudioFileClip, ImageClip
import edge_tts, requests

VOICE = "zh-CN-YunjianNeural"

# -- Step 1: scrape results from free sources ------------------------

def fetch_json_api():
    """Try free JSON APIs (no key needed)."""
    try:
        r = requests.get("https://worldcupjson.net/matches", timeout=10)
        if r.status_code == 200 and "2026" in r.text[:2000]:
            return r.json()
    except Exception:
        pass
    return None

def scrape_gma():
    """Scrape GMA News World Cup results page for match scores."""
    try:
        r = requests.get(
            "https://www.gmanetwork.com/news/sports/football/991493/"
            "2026-fifa-world-cup-updates-and-results-june-15-2026/story/",
            timeout=15, headers={"User-Agent": "Mozilla/5.0"}
        )
        # find "Team X–Y Team" patterns (en-dash or hyphen between digits)
        matches = re.findall(
            r"([A-Z][\w\s&\.'-]+?)\s+(\d+)\s*[–\-]\s*(\d+)\s+([A-Z][\w\s&\.'-]+?)(?:<|\.|,|\n)",
            r.text
        )
        seen = set()
        items = []
        for h, hg, ag, a in matches:
            h, a = h.strip(), a.strip()
            # skip obvious non-team sentences
            if len(h) > 30 or len(a) > 30:
                continue
            key = (h, a)
            if key not in seen:
                seen.add(key)
                items.append({
                    "home_team": {"name": h}, "away_team": {"name": a},
                    "home_score": int(hg), "away_score": int(ag),
                })
        return items or None
    except Exception:
        return None

# -- Step 2: build Chinese summary -----------------------------------

def build_text(data):
    """Turn match list/dict into a passionate Chinese summary."""
    if not data:
        return None
    lines = ["2026世界杯最新战报！"]
    today = datetime.now().strftime("%m月%d日")
    lines.append(f"{today}，比赛结果如下：")
    matches = data if isinstance(data, list) else data
    for m in matches[:8]:
        if isinstance(m, dict):
            h = m.get("home_team", {}).get("name", m.get("home_team_country", "?"))
            a = m.get("away_team", {}).get("name", m.get("away_team_country", "?"))
            hg = m.get("home_team", {}).get("goals", m.get("home_score", "?"))
            ag = m.get("away_team", {}).get("goals", m.get("away_score", "?"))
            lines.append(f"{h} {hg} 比 {ag} {a}！")
    lines.append("精彩绝伦，让我们继续关注下一场比赛！")
    return "。".join(lines)

# -- Step 3: TTS -----------------------------------------------------

async def tts(text, out="test.mp3"):
    c = edge_tts.Communicate(text, VOICE)
    await c.save(out)

# -- Main ------------------------------------------------------------

data = fetch_json_api() or scrape_gma()
text = build_text(data)

if not text:
    print("[WARN] No live data found, using fallback.")
    text = "2026世界杯最新战报！今天的比赛精彩绝伦，让我们继续关注下一场比赛！"

asyncio.run(tts(text))

audio = AudioFileClip("test.mp3")
clip = ImageClip("test.jpg", duration=audio.duration).with_audio(audio)

# 9:16 vertical — scale to fill, center-crop
clip = clip.resized(height=1920, width=1080)

clip.write_videofile("output.mp4", fps=24, logger=None)
