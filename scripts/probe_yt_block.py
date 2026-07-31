"""현재 IP에서 YouTube 자막 차단 회복 여부 단발 검증."""
from __future__ import annotations
import time, urllib.request, sys, os, tempfile
from pathlib import Path

# 1) 단순 page ping
t = time.time()
try:
    req = urllib.request.Request('https://www.youtube.com/robots.txt',
                                 headers={'User-Agent': 'Mozilla/5.0'})
    r = urllib.request.urlopen(req, timeout=10)
    print(f'[1] robots.txt status={r.status} rtt={time.time()-t:.2f}s')
except Exception as e:
    print(f'[1] robots.txt ERR: {e}')

# 2) yt-dlp 단일 자막 호출
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

VID = sys.argv[1] if len(sys.argv) > 1 else 'KJmV_cWCgLs'
with tempfile.TemporaryDirectory() as tmp:
    opts = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["ko", "ko-KR", "en"],
        "subtitlesformat": "vtt/json3/best",
        "outtmpl": os.path.join(tmp, "%(id)s.%(ext)s"),
        "quiet": True, "no_warnings": True, "ignoreerrors": False,
        "extractor_args": {"youtube": {"player_client": ["web", "tv", "android_vr"]}},
    }
    t = time.time()
    try:
        with YoutubeDL(opts) as ydl:
            ydl.download([f'https://www.youtube.com/watch?v={VID}'])
        files = sorted(Path(tmp).iterdir())
        print(f'[2] SUB OK {VID} in {time.time()-t:.1f}s, files={[f.name for f in files]}')
    except DownloadError as e:
        msg = str(e)
        flag = '429/RATE-LIMITED' if ('429' in msg or 'too many requests' in msg.lower()) else 'OTHER'
        print(f'[2] SUB ERR [{flag}]: {msg[:400]}')
    except Exception as e:
        print(f'[2] SUB EXC: {type(e).__name__}: {e}')
