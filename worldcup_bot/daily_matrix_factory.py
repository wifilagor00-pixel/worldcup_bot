"""
Daily Matrix Factory — Pure Football Highlights + Trending Music
================================================================
Zero voiceover.  Zero subtitles.  Hyper-fast 1.5-2.5s highlight cuts
synced to auto-downloaded viral music.  Built for global viral reach.

Usage:
  python daily_matrix_factory.py          # single run
  python daily_matrix_factory.py --loop   # daily scheduler at 8 AM
"""

import json, os, random, re, ssl, subprocess, sys, time, traceback
from datetime import datetime
from pathlib import Path

# -- corporate SSL bypass ----------------------------------------------
if hasattr(ssl, "_create_unverified_context"):
    ssl.create_default_context = ssl._create_unverified_context
    ssl._create_default_https_context = ssl._create_unverified_context
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from moviepy import (AudioFileClip, ColorClip, CompositeAudioClip,
                      CompositeVideoClip, TextClip, VideoFileClip,
                      concatenate_audioclips, concatenate_videoclips, vfx)

# ═══════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════

ROOT      = Path(__file__).parent
TMP       = ROOT / "tmp";  TMP.mkdir(exist_ok=True)
OUT       = ROOT / "output"
W, H, FPS = 1080, 1920, 24
DURATION  = 58                                    # perfect Shorts loop length
FONT_PATH = "C:/Windows/Fonts/simhei.ttf"

# music search queries (rotated for variety)
MUSIC_QUERIES = [
    "trending tiktok background music no copyright instrumental",
    "epic football edm hype track no copyright",
    "viral sports highlight music no copyright instrumental",
    "high energy motivational background track no copyright",
    "addictive tiktok viral sound no copyright instrumental",
]

# football footage queries (rotated per video)
FOOTY_QUERIES = [
    "messi dribbling skills highlights",
    "ronaldo goals skills compilation",
    "mbappe speed dribble highlights",
    "world cup best goals moments",
    "football skills tricks highlights",
    "soccer best goals ever",
    "neymar skills dribbling compilation",
    "haaland goals highlights",
]

# ═══════════════════════════════════════════════════════════════════════
# YT-DLP  (search + download)
# ═══════════════════════════════════════════════════════════════════════

def _yt_search(query, max_results=5, min_dur=30, max_dur=600):
    """Search YouTube, return [{id, title, duration}]. Filter by duration."""
    try:
        cmd = [
            "yt-dlp", f"ytsearch{max_results}:{query}",
            "--flat-playlist", "--dump-json", "--no-playlist",
            "--no-check-certificates",
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, text=True, timeout=30)
        results = []
        for line in proc.stdout.strip().split("\n"):
            if not line:
                continue
            v = json.loads(line)
            dur = v.get("duration") or 0
            if dur and min_dur <= dur <= max_dur:
                results.append({"id": v["id"], "title": v.get("title", ""), "duration": dur})
        return results[:max_results]
    except Exception:
        return []


def _yt_download(video_id, output_path, audio_only=False):
    """Download a YouTube video/audio to output_path. Returns path or None."""
    try:
        output_path = Path(output_path)
        fmt = "bestaudio[ext=m4a]/bestaudio" if audio_only else \
              "best[ext=mp4][vcodec^=avc1]/best[ext=mp4]/best"
        cmd = [
            "yt-dlp", f"https://youtube.com/watch?v={video_id}",
            "-f", fmt, "-o", str(output_path),
            "--no-playlist", "--no-check-certificates",
            "--socket-timeout", "30", "--retries", "3",
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE,
                       stderr=subprocess.DEVNULL, text=True, timeout=120)
        if output_path.exists() and output_path.stat().st_size > 1000:
            return output_path
        for alt in output_path.parent.glob(output_path.stem + ".*"):
            if alt.stat().st_size > 1000:
                return alt
        return None
    except Exception:
        return None

# ═══════════════════════════════════════════════════════════════════════
# MUSIC PIPELINE  (auto-viral trending track)
# ═══════════════════════════════════════════════════════════════════════

def _clean_title(title):
    """Strip tags/noise from YouTube music title for watermark display."""
    for tag in ["(Official", "[Official", "no copyright", "No Copyright",
                "NCS", "royalty free", "Royalty Free", "#shorts", "|", "Audio"]:
        title = title.split(tag)[0]
    title = re.sub(r"\s+", " ", title).strip()
    return title[:60]


def acquire_music():
    """
    Download a trending background track via yt-dlp.
    Tries local bgm.mp3 first, then each music query in order.
    Returns (audio_path, display_title) or (None, None).
    """
    local = ROOT / "bgm.mp3"
    if local.exists():
        return local, "Trending Music"

    for query in MUSIC_QUERIES:
        results = _yt_search(query, max_results=3, min_dur=90, max_dur=360)
        if not results:
            continue
        for r in results:
            path = _yt_download(r["id"], TMP / "bgm_audio", audio_only=True)
            if path:
                cached = ROOT / ("bgm" + path.suffix)
                if cached.exists():
                    cached.unlink()
                path.rename(cached)
                return cached, _clean_title(r["title"])
    return None, None

# ═══════════════════════════════════════════════════════════════════════
# VIDEO LAYOUT  (anti-copyright + darkened-blur portrait)
# ═══════════════════════════════════════════════════════════════════════

def _blur_clip(clip):
    tiny = clip.resized(width=max(20, clip.w // 24))
    return tiny.resized((W, H))


def _darken(clip, factor=0.65):
    """Darken clip by scaling RGB values (0.65 = 35% darker)."""
    return clip * factor


def _anti_copyright(clip):
    """1.1x zoom to shift pixel fingerprint."""
    return clip.resized(1.1).resized(clip.size)


def _has_motion(src, start_t, end_t, threshold=8.0):
    """Quick motion check: sample two frames, return True if scene has action.
    Low mean-absolute-difference → static logo/transition → discard."""
    try:
        t_mid = (start_t + end_t) / 2
        f1 = src.get_frame(start_t + 0.3)
        f2 = src.get_frame(t_mid)
        mad = abs(f1.astype("float32") - f2.astype("float32")).mean()
        return mad > threshold
    except Exception:
        return True  # if check fails, keep the clip — better than discarding all


def _portrait_layout(clip):
    """Sharp layer at 48% height, darkened-blur bars behind."""
    sharp_h = int(H * 0.48)
    sharp   = clip.resized(height=sharp_h)
    blur_bg = _blur_clip(clip)
    blur_bg = _darken(blur_bg)
    return CompositeVideoClip([
        blur_bg.with_position("center"),
        sharp.with_position(("center", "center")),
    ], size=(W, H))

# ═══════════════════════════════════════════════════════════════════════
# MONTAGE BUILDER  (hyper-fast cuts + watermark)
# ═══════════════════════════════════════════════════════════════════════

def build_highlight_montage(yt_videos, music_path, music_title, output_path):
    """
    Download multiple YouTube football sources, slice into rapid 1.5-2.5s
    clips, shuffle, apply anti-copyright zoom, darkened-blur layout,
    overlay music watermark, composite audio, and export at 58s.
    """
    # 1. download football footage sources
    sources = []
    for v in yt_videos:
        p = _yt_download(v["id"], TMP / f"footy_{v['id'][:8]}.mp4")
        if p:
            sources.append(p)
    if not sources:
        return None

    # 2. adaptive replay slicing: skip first 30s (logos/intros), motion-filter
    #    every candidate window, retry forward on static/black frames.
    INTRO_BAN = 30.0
    subclips = []
    for src_path in sources:
        src = VideoFileClip(str(src_path)).without_audio()
        sd  = src.duration
        pos = INTRO_BAN
        while pos < sd - 5:
            is_replay = random.random() < 0.33           # 1-in-3: extended replay
            clip_len = random.uniform(6.0, 7.5) if is_replay else 4.5
            end_t = min(pos + clip_len, sd)
            # motion gate: retry forward if static/logo/black frame
            retries = 0
            while retries < 8 and not _has_motion(src, pos, end_t):
                pos += random.uniform(2, 4)
                end_t = min(pos + clip_len, sd)
                retries += 1
            if pos >= sd - 5:
                break
            sub = src.subclipped(pos, end_t)
            sub = _anti_copyright(sub)
            sub = _portrait_layout(sub)
            subclips.append(sub)
            pos += clip_len + random.uniform(6, 10)      # skip to next action arc
        src.close()

    if not subclips:
        return None
    random.shuffle(subclips)

    # 3. dynamic consolidation: append variable-length clips until ≥ 58s,
    #    then trim the final clip to land dead-on 58.0s.
    video = None
    for c in subclips:
        video = c if video is None else concatenate_videoclips([video, c])
        if video.duration >= DURATION:
            break
    video = video.subclipped(0, DURATION)

    # 4. minimalist watermark
    watermark = (TextClip(
        text=f"Music: {music_title}",
        font=FONT_PATH, font_size=38,
        color="white", stroke_color="black", stroke_width=3,
        duration=DURATION,
    ).with_position(("center", H - 120)))
    video = CompositeVideoClip([video, watermark])

    # 5. audio: music track clipped to exactly DURATION
    music = AudioFileClip(str(music_path))
    if music.duration < DURATION:
        repeats = int(DURATION / music.duration) + 1
        music = concatenate_audioclips([music] * repeats)
    music = music.subclipped(0, DURATION)
    video = video.with_audio(music)
    video.write_videofile(str(output_path), fps=FPS, logger=None)

    # 6. cleanup temp sources
    for sp in sources:
        try:
            sp.unlink()
        except Exception:
            pass
    return output_path

# ═══════════════════════════════════════════════════════════════════════
# SINGLE-VIDEO PIPELINE
# ═══════════════════════════════════════════════════════════════════════

def make_video(slug, output_path=None):
    """One video: music + football clips -> 58s highlight montage."""
    out_dir = OUT / datetime.now().strftime("%Y-%m-%d")
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_path or (out_dir / f"{slug}.mp4")

    # 1. acquire music
    print("    music...")
    music_path, music_title = acquire_music()
    if not music_path:
        print("    FAILED: no music source")
        return None
    print(f"    music: {music_title[:60]}")

    # 2. acquire football footage
    print("    football clips...")
    query = random.choice(FOOTY_QUERIES)
    yt_videos = _yt_search(query, max_results=3, min_dur=30, max_dur=900)
    if not yt_videos:
        # fallback: broader search
        yt_videos = _yt_search("soccer football highlights goals", max_results=3, min_dur=30, max_dur=900)
    if not yt_videos:
        print("    FAILED: no football clips")
        return None
    print(f"    found {len(yt_videos)} sources")

    # 3. build montage
    print("    rendering...")
    result = build_highlight_montage(yt_videos, music_path, music_title, output_path)
    if result:
        print(f"    -> {output_path.name}")
    return output_path if result else None

# ═══════════════════════════════════════════════════════════════════════
# BATCH PIPELINE  (5 highlight videos)
# ═══════════════════════════════════════════════════════════════════════

def run_batch_pipeline():
    out_dir = OUT / datetime.now().strftime("%Y-%m-%d")
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n{'='*50}")
    print(f"Pure Highlights Pipeline — {datetime.now():%Y-%m-%d %H:%M}")
    print(f"Output: {out_dir}")
    print(f"{'='*50}")

    results = []
    for i in range(5):
        slug = f"highlight-{i+1:02d}"
        print(f"\n[{i+1}/5] {slug}")
        try:
            r = make_video(slug, out_dir / f"{slug}.mp4")
            if r:
                results.append(r)
                size_mb = r.stat().st_size / 1e6
                print(f"       {r.name}  ({size_mb:.1f} MB)")
        except Exception as e:
            print(f"       FAILED: {e}")
            traceback.print_exc()

    # -- auto-upload to YouTube Shorts ---------------------------------
    upload_count = 0
    if all(k in os.environ for k in
           ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN"]):
        print("\n[UPLOAD] YouTube OAuth detected — uploading...")
        try:
            from uploader import upload_short
            for r in results:
                vid = upload_short(str(r), privacy="public")
                if vid:
                    upload_count += 1
        except Exception as e:
            print(f"  upload error: {e}")
    else:
        print("\n[SKIP] Google OAuth env vars not set. Videos local only.")
        print("  Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN to enable.")

    print(f"\n{'='*50}")
    print(f"DONE.  {len(results)}/5 videos -> {out_dir}  (uploaded {upload_count})")
    print(f"{'='*50}\n")
    return len(results)

# ═══════════════════════════════════════════════════════════════════════
# SCHEDULER  (runs once daily at 8 AM)
# ═══════════════════════════════════════════════════════════════════════

LAST_RUN_DATE = None
RUN_HOUR = 8

def scheduler_loop():
    global LAST_RUN_DATE
    print(f"Highlights scheduler started (run at {RUN_HOUR:02d}:00 daily).")
    print("Press Ctrl+C to stop.\n")
    while True:
        now = datetime.now()
        today = now.date()
        if LAST_RUN_DATE != today and now.hour >= RUN_HOUR:
            print(f"[{now:%Y-%m-%d %H:%M}] Triggering daily run...")
            try:
                run_batch_pipeline()
                LAST_RUN_DATE = today
            except Exception as e:
                print(f"Pipeline CRASHED: {e}")
                traceback.print_exc()
                LAST_RUN_DATE = today
        time.sleep(60)

# ═══════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if "--loop" in sys.argv:
        scheduler_loop()
    else:
        run_batch_pipeline()
