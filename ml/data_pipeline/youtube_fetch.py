"""YouTube 채널 → 영상 메타 + 자막 텍스트 수집.

흐름:
  1) yt-dlp로 채널의 전체 영상 ID/메타 수집 → channel.jsonl
  2) 각 영상에 대해 자막 시도 (한글 → 영어 → 자동생성 순)
       있으면 정규화 텍스트 저장
       없으면 transcribe_queue.txt 에 추가 (whisper STT 대상)
  3) 출력:
       data/raw/youtube/<channel>/index.jsonl       (메타 한 줄 = 영상 하나)
       data/raw/youtube/<channel>/captions/<id>.txt (자막 수집 본)
       data/raw/youtube/<channel>/transcribe_queue.txt
       data/processed/youtube/<channel>/<id>.txt    (RAG 인제스트용 정규화 본)

사용:
  python -m ml.data_pipeline.youtube_fetch --list-only        # 메타만
  python -m ml.data_pipeline.youtube_fetch                    # 전체 수집
  python -m ml.data_pipeline.youtube_fetch --limit 5          # 채널당 N개만
  python -m ml.data_pipeline.youtube_fetch --channel hyunmyung
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 채널 정의. label = 폴더명, handle = @핸들, name_ko = 표시명
CHANNELS = [
    {
        "label": "cheonsewon",
        "name_ko": "천세원 명리교실",
        "url": "https://www.youtube.com/@慈勇천세원명리교실/videos",
    },
    {
        "label": "hyunmyung",
        "name_ko": "현명역술원",
        "url": "https://www.youtube.com/@hyunmyung/videos",
    },
    {
        "label": "haengun",
        "name_ko": "행운사주철학관",
        "url": "https://www.youtube.com/@행운사주철학관/videos",
    },
]


def list_channel_videos(channel_url: str, limit: int | None) -> list[dict]:
    """yt-dlp로 채널 동영상 메타 추출 (다운로드 없이)."""
    from yt_dlp import YoutubeDL

    opts = {
        "extract_flat": True,
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "playlistend": limit,
    }
    if _IMPERSONATE:
        opts["impersonate"] = _IMPERSONATE
    if _PROXY:
        opts["proxy"] = _PROXY
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)
    entries = info.get("entries") or []
    out = []
    for e in entries:
        if not e or not e.get("id"):
            continue
        out.append(
            {
                "video_id": e["id"],
                "title": (e.get("title") or "").strip(),
                "duration": e.get("duration"),
                "url": e.get("url") or f"https://www.youtube.com/watch?v={e['id']}",
            }
        )
    return out


def _parse_vtt(text: str) -> str:
    """VTT → 평문. 타임스탬프/큐 ID/태그 제거."""
    out: list[str] = []
    seen_in_cue: set[str] = set()
    prev_line: str | None = None
    for line in text.splitlines():
        s = line.strip()
        if not s:
            seen_in_cue.clear()
            prev_line = None
            continue
        if s.startswith(("WEBVTT", "NOTE", "Kind:", "Language:", "STYLE")):
            continue
        if "-->" in s:
            seen_in_cue.clear()
            prev_line = None
            continue
        # cue identifier (digits) 등은 다음 행이 텍스트면 자연스럽게 처리됨
        # 인라인 태그 제거: <c>, <00:00:01.000> 등
        s = re.sub(r"<[^>]+>", "", s)
        s = re.sub(r"&nbsp;", " ", s)
        s = re.sub(r"&amp;", "&", s)
        s = re.sub(r"&lt;", "<", s)
        s = re.sub(r"&gt;", ">", s)
        s = s.strip()
        if not s:
            continue
        # 자동 자막은 같은 줄을 연속 큐에 중복 출력 → 같은 cue 내 중복만 제거
        if s == prev_line:
            continue
        if s in seen_in_cue:
            continue
        seen_in_cue.add(s)
        out.append(s)
        prev_line = s
    return " ".join(out)


def _parse_json3(text: str) -> str:
    """YouTube json3 자막 포맷 → 평문."""
    try:
        data = json.loads(text)
    except Exception:
        return ""
    parts: list[str] = []
    for ev in data.get("events") or []:
        segs = ev.get("segs") or []
        for seg in segs:
            t = (seg.get("utf8") or "").strip()
            if t:
                parts.append(t)
    return " ".join(parts)


_SUB_EXTS = ("vtt", "srv3", "srv2", "srv1", "json3", "ttml")
_LANG_PREF = ("ko", "ko-KR", "ko-orig", "en", "en-US", "en-orig")


def _find_sub_file(tmp_root: Path, video_id: str) -> tuple[Path, str] | None:
    """우선 언어 → 확장자 순으로 다운로드된 자막 파일 찾기."""
    # 정확한 언어 매칭 우선
    for lang in _LANG_PREF:
        for ext in _SUB_EXTS:
            p = tmp_root / f"{video_id}.{lang}.{ext}"
            if p.exists() and p.stat().st_size > 0:
                return p, lang
    # 와일드카드 (예: ko-anything)
    for prefix in ("ko", "en"):
        for ext in _SUB_EXTS:
            for p in tmp_root.glob(f"{video_id}.{prefix}*.{ext}"):
                if p.stat().st_size > 0:
                    lang = p.stem.split(".", 1)[1] if "." in p.stem else prefix
                    return p, lang
    # 무엇이든
    for ext in _SUB_EXTS:
        for p in tmp_root.glob(f"{video_id}.*.{ext}"):
            if p.stat().st_size > 0:
                lang = p.stem.split(".", 1)[1] if "." in p.stem else "?"
                return p, lang
    return None


class RateLimited(Exception):
    """YouTube가 IP를 일시 차단하자 떨어진 예외 — 패스를 즉시 중단하도록 신호."""


_COOKIES_FROM_BROWSER: tuple | None = None  # 예: ('edge',) or ('chrome',)
_IMPERSONATE = None  # ImpersonateTarget 인스턴스
_PROXY: str | None = None  # 예: 'socks5://127.0.0.1:1080', 'http://user:pass@host:port'


def set_proxy(proxy: str | None) -> None:
    """yt-dlp 프록시 설정(IP 우회). None이면 직접 연결."""
    global _PROXY
    _PROXY = proxy or None


def set_cookies_from_browser(browser: str | None) -> None:
    global _COOKIES_FROM_BROWSER
    _COOKIES_FROM_BROWSER = (browser,) if browser else None


def set_impersonate(target: str | None) -> None:
    """target 예: 'chrome', 'chrome-120', 'safari'."""
    global _IMPERSONATE
    if not target:
        _IMPERSONATE = None
        return
    from yt_dlp.networking.impersonate import ImpersonateTarget
    _IMPERSONATE = ImpersonateTarget.from_str(target)


def fetch_caption(video_id: str) -> tuple[str | None, str | None]:
    """yt-dlp로 자막 다운로드 → 평문 추출. 반환: (text, lang) 또는 (None, None)."""
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError

    url = f"https://www.youtube.com/watch?v={video_id}"
    with tempfile.TemporaryDirectory(prefix="ytcap_") as tmp:
        tmp_root = Path(tmp)
        opts = {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["ko", "ko-KR", "ko-orig", "en", "en-US", "en-orig"],
            "subtitlesformat": "vtt/srv3/json3/srv1/best",
            "outtmpl": str(tmp_root / "%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": False,
            "retries": 3,
            "fragment_retries": 3,
            # yt-dlp wiki 권장: guest 한도 ~300 영상/시간. 자막 호출은 추가 페이싱 필요.
            "sleep_interval_subtitles": 5,
            # web+tv 조합: web 은 메타데이터 수집에 안정, tv 는 자막 fallback. android 제외로 요청수 감소.
            "extractor_args": {"youtube": {"player_client": ["web", "tv"]}},
        }
        if _COOKIES_FROM_BROWSER:
            opts["cookiesfrombrowser"] = _COOKIES_FROM_BROWSER
        if _IMPERSONATE:
            opts["impersonate"] = _IMPERSONATE
        if _PROXY:
            opts["proxy"] = _PROXY
        try:
            with YoutubeDL(opts) as ydl:
                ydl.download([url])
        except DownloadError as e:
            msg = str(e)
            if "429" in msg or "too many requests" in msg.lower():
                raise RateLimited(msg) from e
            if "members" in msg.lower() or "private" in msg.lower():
                return None, None
            print(f"  [yt-dlp 실패] {video_id}: {msg[:120]}", file=sys.stderr)
            return None, None
        except Exception as e:
            print(f"  [yt-dlp 예외] {video_id}: {e}", file=sys.stderr)
            return None, None

        found = _find_sub_file(tmp_root, video_id)
        if not found:
            return None, None
        sub_path, lang = found
        raw = sub_path.read_text(encoding="utf-8", errors="replace")
        ext = sub_path.suffix.lstrip(".").lower()
        if ext == "json3":
            text = _parse_json3(raw)
        else:
            text = _parse_vtt(raw)
        text = text.strip()
        if not text:
            return None, None
        return text, lang


def normalize_caption(raw: str) -> str:
    """자막 텍스트 정규화 — 음악 마커, 다중 공백 제거, 문장 결합."""
    s = raw.replace("\u200b", "")
    s = re.sub(r"\[음악\]|\[Music\]|\[박수\]|\[웃음\]|\[Applause\]", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def collect_channel(
    channel: dict,
    limit: int | None,
    list_only: bool,
    force: bool,
    batch_size: int = 0,
    batch_sleep_sec: int = 0,
) -> dict:
    label = channel["label"]
    raw_dir = PROJECT_ROOT / "data" / "raw" / "youtube" / label
    cap_dir = raw_dir / "captions"
    proc_dir = PROJECT_ROOT / "data" / "processed" / "youtube" / label
    raw_dir.mkdir(parents=True, exist_ok=True)
    cap_dir.mkdir(parents=True, exist_ok=True)
    proc_dir.mkdir(parents=True, exist_ok=True)

    index_path = raw_dir / "index.jsonl"
    queue_path = raw_dir / "transcribe_queue.txt"

    print(f"\n=== {channel['name_ko']} ({label}) ===")
    print(f"채널 URL: {channel['url']}")

    print("[1] 영상 목록 수집...")
    t0 = time.time()
    videos = list_channel_videos(channel["url"], limit)
    print(f"    {len(videos)}개 영상 (소요 {time.time()-t0:.1f}s)")

    # index 저장 (덮어쓰기)
    with index_path.open("w", encoding="utf-8") as f:
        for v in videos:
            v_out = dict(v, channel_label=label, channel_name=channel["name_ko"])
            f.write(json.dumps(v_out, ensure_ascii=False) + "\n")
    print(f"    → {index_path.relative_to(PROJECT_ROOT)}")

    stats = {"total": len(videos), "captioned": 0, "queued": 0, "skipped": 0, "failed": 0}
    if list_only:
        return stats

    print("[2] 자막 수집...")
    if batch_size:
        print(f"    [batch] 신규 {batch_size}개 수집마다 {batch_sleep_sec//60}분 휴식 (차단 방지)")
    queue_lines: list[str] = []
    rate_limited = False
    new_in_batch = 0  # 이번 배치에서 신규로 받은 자막 수
    for i, v in enumerate(videos, 1):
        vid = v["video_id"]
        cap_file = cap_dir / f"{vid}.txt"
        proc_file = proc_dir / f"{vid}.txt"
        if cap_file.exists() and proc_file.exists() and not force:
            stats["skipped"] += 1
            continue

        try:
            text, lang = fetch_caption(vid)
        except RateLimited as e:
            print(f"  [   {i:4d}/{len(videos)}] ! {vid}  429 RATE LIMIT — 패스 중단", file=sys.stderr)
            rate_limited = True
            break
        if text:
            cap_file.write_text(text, encoding="utf-8")
            norm = normalize_caption(text)
            header = f"# {v['title']}\n# 출처: {channel['name_ko']} | https://www.youtube.com/watch?v={vid}\n# 자막 언어: {lang}\n\n"
            proc_file.write_text(header + norm, encoding="utf-8")
            stats["captioned"] += 1
            new_in_batch += 1
            mark = "K" if (lang or "").startswith("ko") else "E"
            print(f"  [{i:4d}/{len(videos)}] {mark} {vid}  {v['title'][:50]}  ({len(norm):,}자)")
        else:
            queue_lines.append(f"{vid}\t{v['title']}")
            stats["queued"] += 1
            print(f"  [{i:4d}/{len(videos)}] - {vid}  {v['title'][:50]}  (자막 없음 → STT 대기)")

        # yt-dlp wiki 권장: 다운로드 간 5~10초. 한도(guest ~300/h) 초과 시 429+장기차단.
        time.sleep(random.uniform(6.0, 10.0))

        # 배치 페이싱: 신규 batch_size개 받을 때마다 장기 휴식 → 시간당 요청량을 한도 이하로 억제
        if batch_size and new_in_batch >= batch_size:
            from datetime import datetime as _dt
            print(
                f"    [batch] 신규 {new_in_batch}개 수집 완료 → {batch_sleep_sec//60}분 휴식 "
                f"(재개 예정 {_dt.fromtimestamp(time.time()+batch_sleep_sec):%H:%M})",
                flush=True,
            )
            time.sleep(batch_sleep_sec)
            new_in_batch = 0

    # 기존 queue와 합자 (스킵된 것도 포함 안 됨 — 이번 패스 머리만 기록)
    if queue_lines:
        queue_path.write_text("\n".join(queue_lines), encoding="utf-8")
        print(f"    STT 대기 큐: {queue_path.relative_to(PROJECT_ROOT)} ({len(queue_lines)}개)")

    print(f"[요약] 자막수집 {stats['captioned']} / STT대기 {stats['queued']} / 스킵 {stats['skipped']}")
    stats["rate_limited"] = rate_limited
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", help="특정 label만 처리 (cheonsewon/hyunmyung/haengun)")
    ap.add_argument("--list-only", action="store_true", help="영상 목록만 추출")
    ap.add_argument("--limit", type=int, default=None, help="채널당 최대 N개")
    ap.add_argument("--force", action="store_true", help="이미 받은 파일도 재수집")
    ap.add_argument("--max-passes", type=int, default=5, help="진행이 멈출 때까지 자동 재실행 (기본 5회)")
    ap.add_argument("--cookies-from-browser", default=None, help="YouTube 쿠키 로드 (edge/chrome/firefox 등) — 429 회피용")
    ap.add_argument("--impersonate", default="chrome", help="브라우저 fingerprint 임퍼소네이션 (기본 chrome, 끄려면 빈 문자열)")
    ap.add_argument("--proxy", default=None, help="IP 우회 프록시 (예: socks5://127.0.0.1:1080, http://host:port)")
    ap.add_argument("--batch-size", type=int, default=10, help="신규 N개 수집마다 휴식 (차단방지, 기본 10, 0=끔)")
    ap.add_argument("--batch-sleep-min", type=int, default=10, help="배치 사이 휴식(분, 기본 10)")
    ap.add_argument("--cooldown", type=int, default=60, help="429 등으로 종료된 패스 사이 대기(초)")
    args = ap.parse_args()

    if args.cookies_from_browser:
        set_cookies_from_browser(args.cookies_from_browser)
        print(f"[cookies] browser={args.cookies_from_browser}")
    if args.impersonate:
        set_impersonate(args.impersonate)
        print(f"[impersonate] {args.impersonate}")
    if args.proxy:
        set_proxy(args.proxy)
        print(f"[proxy] {args.proxy}")

    targets: Iterable[dict]
    if args.channel:
        targets = [c for c in CHANNELS if c["label"] == args.channel]
        if not targets:
            print(f"[ERR] unknown channel: {args.channel}", file=sys.stderr)
            return 2
    else:
        targets = CHANNELS

    last_captioned = -1
    for pass_no in range(1, args.max_passes + 1):
        print(f"\n##### PASS {pass_no}/{args.max_passes} #####")
        grand = {"total": 0, "captioned": 0, "queued": 0, "skipped": 0, "failed": 0}
        for ch in targets:
            try:
                s = collect_channel(
                    ch, args.limit, args.list_only, args.force,
                    batch_size=args.batch_size,
                    batch_sleep_sec=args.batch_sleep_min * 60,
                )
                for k, v in s.items():
                    grand[k] = grand.get(k, 0) + v
            except KeyboardInterrupt:
                print("\n[중단됨]")
                return 130
            except Exception as e:
                print(f"[ERR] {ch['label']}: {e}", file=sys.stderr)
                grand["failed"] += 1

        print("\n" + "=" * 60)
        print(
            f"[PASS {pass_no}] 영상 {grand['total']}  자막 {grand['captioned']}  "
            f"STT대기 {grand['queued']}  스킵 {grand['skipped']}  실패 {grand['failed']}"
        )

        if args.list_only:
            return 0
        # 이번 패스에 신규 자막 0건이면 종료 (이미 다 모았거나 더는 못 가져옴)
        if grand["captioned"] == 0:
            print("[DONE] 이번 패스에 신규 자막 0건 → 종료")
            return 0
        if grand["captioned"] == last_captioned:
            print("[DONE] 진행 없음 → 종료")
            return 0
        last_captioned = grand["captioned"]
        # 다음 패스 전 쿨다운
        print(f"[cooldown] {args.cooldown}s 대기 후 다음 패스")
        time.sleep(args.cooldown)

    print(f"[STOP] max-passes({args.max_passes}) 도달")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
