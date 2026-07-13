"""
YouTube Shorts Uploader — OAuth 2.0 via refresh token
======================================================
Reads GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN
from environment variables.  Uploads MP4 files as YouTube Shorts
with auto-generated titles, descriptions, and hashtags.

Usage:
  python uploader.py <video.mp4> [--title "Custom Title"]

Env vars required:
  GOOGLE_CLIENT_ID       — from Google Cloud Console > APIs & Services > Credentials
  GOOGLE_CLIENT_SECRET   — from same OAuth 2.0 client
  GOOGLE_REFRESH_TOKEN   — obtained once via OAuth playground or auth flow
"""

import os, sys, argparse
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


def _get_authenticated_service():
    """Build and return an authorized YouTube API service using refresh token."""
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    return build("youtube", "v3", credentials=creds)


def upload_short(video_path, title=None, description=None, tags=None,
                 category_id="17", privacy="public"):
    """
    Upload an MP4 to YouTube as a Short (vertical ≤60s, #Shorts in title).

    Args:
      video_path:  path to .mp4 file
      title:       video title (auto-generated if None)
      description: video description
      tags:        list of keyword tags
      category_id: 17 = Sports
      privacy:     'public', 'unlisted', or 'private'
    Returns:
      YouTube video ID string, or None on failure.
    """
    video_path = Path(video_path)
    if not video_path.exists():
        print(f"ERROR: file not found: {video_path}")
        return None

    title = title or f"⚽ Ultimate Football Highlights 🔥 #Shorts"
    if "#Shorts" not in title and "#shorts" not in title:
        title += " #Shorts"

    description = description or (
        "🔥 Pure football highlights with trending music.\n"
        "🏆 Best goals, skills & moments.\n"
        "#Football #Soccer #Highlights #WorldCup #Shorts #Sports"
    )
    tags = tags or ["football", "soccer", "highlights", "goals", "skills",
                    "shorts", "sports", "world cup", "football shorts"]

    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": tags[:30],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    try:
        youtube = _get_authenticated_service()
        media = MediaFileUpload(
            str(video_path), mimetype="video/mp4",
            chunksize=1024 * 1024 * 5, resumable=True,
        )
        request = youtube.videos().insert(
            part="snippet,status", body=body, media_body=media,
        )
        print(f"Uploading: {video_path.name} ({video_path.stat().st_size / 1e6:.1f} MB)")
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"  {int(status.progress() * 100)}%", end="\r")
        video_id = response["id"]
        print(f"\n  Published: https://youtube.com/shorts/{video_id}")
        return video_id
    except Exception as e:
        print(f"ERROR uploading: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload MP4 as YouTube Short")
    parser.add_argument("video", help="Path to .mp4 file")
    parser.add_argument("--title", help="Custom video title", default=None)
    parser.add_argument("--privacy", default="public",
                        choices=["public", "unlisted", "private"])
    args = parser.parse_args()

    required = ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN"]
    missing = [v for v in required if v not in os.environ]
    if missing:
        print(f"ERROR: Missing env vars: {', '.join(missing)}")
        print("Set them via GitHub Secrets or export in your shell.")
        sys.exit(1)

    video_id = upload_short(args.video, title=args.title, privacy=args.privacy)
    if video_id:
        print(f"SUCCESS: {video_id}")
    else:
        sys.exit(1)
