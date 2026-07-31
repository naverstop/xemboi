"""영상 작업 오케스트레이션 + 과금(부록 C-3/C-8).

create_job: 활성중복검사 → 즉시 차감(실패402) → insert → commit (원자적).
run_job  : source→scenario→TTS→render→compose→finalize. 실패 시 status=failed + 멱등 환불.
refund   : UPDATE...WHERE refunded=false rowcount==1 일 때만(이중환불=무결제크레딧 차단).
"""
from __future__ import annotations

import re
import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.repositories.auth_models import User
from backend.app.repositories.models import SajuVideoJob
from backend.app.services import auth_service, settings_service
from backend.app.services.video import compose as _compose
from backend.app.services.video import scenario as _scenario
from backend.app.services.video import tts as _tts
from backend.app.services.video import renderer as _renderer
from backend.app.services.video.renderer import build_watermark_overlay, get_renderer
from backend.app.services.video.source import (
    VideoSourceError,
    fetch_saju_video_source,
)

_ROOT = Path(__file__).resolve().parents[4]          # D:\saju_agent
_VIDEO_BASE = _ROOT / "data" / "video"               # master/delivery 저장 루트
_WORK_BASE = _ROOT / "data" / "video" / "_work"

_STAGE_PCT = {"scenario": 15, "tts": 35, "compose": 70, "encode": 90, "finalize": 95}

# 분위기 → BGM 트랙(사장님 자작 라이브러리). 시나리오 무드로 자동 선택.
_BGM_BY_FAMILY = {"reflective": "reflective_warm.mp3", "hopeful": "hopeful_smooth.mp3", "calm": "calm_lofi.mp3"}


_STAGE_FAMILY = {"초년": "reflective", "유년": "hopeful", "청년": "hopeful", "장년": "reflective", "노년": "reflective"}


def _pick_bgm_name(scenes: list[dict]) -> str:
    """영상 분위기에 맞는 BGM 선택. 명시 무드(emotion/bgm_mood)가 강하면 그걸로,
    없으면 단계 기반(사주=1인칭 회상 자서전이라 reflective/따뜻함이 기본). 동률은 reflective 우선."""
    fam = {"reflective": 0, "hopeful": 0, "calm": 0}
    for sc in scenes:
        bm = (sc.get("bgm_mood") or "").lower()
        emo = sc.get("emotion") or ""
        mood = sc.get("mood") or ""
        if bm == "reflective" or emo in ("회상", "아쉬움", "평온") or mood == "회상":
            fam["reflective"] += 2
        elif bm in ("hopeful", "playful") or emo in ("희망", "기쁨", "설렘", "벅참", "위트") or mood in ("밝음", "희망"):
            fam["hopeful"] += 2
        elif mood == "차분":          # 'calm'은 파서 기본값이라 무시; 명시 '차분'만 반영
            fam["calm"] += 1
        fam[_STAGE_FAMILY.get(sc.get("stage", ""), "reflective")] += 1   # 무드신호 약해도 단계로 보강
    return _BGM_BY_FAMILY[max(("reflective", "hopeful", "calm"), key=lambda k: fam[k])]


class PaywallError(Exception):
    """잔액 부족 → 402."""


class JobConflict(Exception):
    """동일 답변 활성 작업 존재 → 409."""


def _abs(rel: str | None) -> Path | None:
    return (_VIDEO_BASE / rel) if rel else None


def _resolve_title(db: Session, job: SajuVideoJob) -> str:
    """영상 제목 = "{SNS 닉네임}님의 사주영상". 닉네임 없으면 '회원'."""
    nick = "회원"
    if job.user_id is not None:
        u = db.get(User, job.user_id)
        if u and (u.nickname or "").strip():
            nick = u.nickname.strip()
    nick = re.sub(r'[\\/:*?"<>|]', "", nick)[:20] or "회원"
    return f"{nick}님의 사주영상"


def _set_stage(db: Session, job: SajuVideoJob, stage: str, detail: str = "") -> None:
    job.stage = stage
    job.progress_pct = _STAGE_PCT.get(stage, job.progress_pct)
    if detail:
        job.detail = detail
    db.commit()


# ───────────────────────── 발행(과금) ─────────────────────────
def create_job(db: Session, message_id: int, requester, is_admin: bool = False) -> SajuVideoJob:
    # 1. 소스/권한 검증(읽기) — assistant·소유·익명정책
    src = fetch_saju_video_source(db, message_id, requester=requester, is_admin=is_admin)

    # 2. 활성 중복(이중 차감) 사전 차단
    existing = (
        db.query(SajuVideoJob)
        .filter(SajuVideoJob.message_id == message_id, SajuVideoJob.status.in_(("queued", "running")))
        .first()
    )
    if existing is not None:
        raise JobConflict(existing.job_token)

    uid = getattr(requester, "id", None)
    cost = settings_service.get_int(db, "video_gen_cost", 20000)
    aspect = settings_service.get(db, "shorts_aspect", "9x16")
    retention_h = settings_service.get_int(db, "shorts_retention_hours", 48)
    token = uuid.uuid4().hex

    # 3. 즉시 차감(원자적). 잔액부족 → 402
    charged = 0
    if uid is not None and cost > 0 and not is_admin:
        try:
            auth_service.adjust_credit(db, uid, -cost, reason="video_gen", ref_id=token)
            charged = cost
        except ValueError:
            db.rollback()
            raise PaywallError("insufficient_credits")

    # 4. job insert + commit (차감과 같은 트랜잭션)
    job = SajuVideoJob(
        job_token=token, session_id=src.session_id, message_id=message_id, user_id=uid,
        status="queued", aspect=aspect, credits_charged=charged,
        created_at=datetime.utcnow(), expires_at=datetime.utcnow() + timedelta(hours=retention_h),
    )
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        # 부분유니크(동시 발행) 경합 → 차감·insert가 같은 트랜잭션이라 rollback이 차감도 무효화.
        # (별도 보상환불 금지: 차감 자체가 사라졌으므로 +환불하면 무결제 크레딧 발행됨)
        db.rollback()
        existing = (
            db.query(SajuVideoJob)
            .filter(SajuVideoJob.message_id == message_id, SajuVideoJob.status.in_(("queued", "running")))
            .first()
        )
        raise JobConflict(existing.job_token if existing else token)
    db.refresh(job)
    return job


# ───────────────────────── 환불(멱등) ─────────────────────────
def refund_job(db: Session, job: SajuVideoJob) -> bool:
    if not job.credits_charged or job.user_id is None:
        return False
    # status='failed' + refunded=false 일 때만(납품 done 환불 차단 + 이중환불 차단)
    res = db.execute(
        update(SajuVideoJob)
        .where(
            SajuVideoJob.id == job.id,
            SajuVideoJob.refunded.is_(False),
            SajuVideoJob.status == "failed",
        )
        .values(refunded=True)
    )
    if res.rowcount != 1:
        db.rollback()
        return False  # 이미 환불됨 / done(납품) → 환불 안 함
    auth_service.adjust_credit(db, job.user_id, +job.credits_charged,
                               reason="video_gen_refund", ref_id=job.job_token)
    db.commit()
    return True


# ───────────────────────── 실행(렌더) ─────────────────────────
def run_job(db: Session, job: SajuVideoJob) -> SajuVideoJob:
    job.status = "running"
    _set_stage(db, job, "scenario", "이야기를 구성하고 있어요")
    work = _WORK_BASE / job.job_token
    try:
        seconds = min(
            settings_service.get_int(db, "shorts_video_seconds", 60),
            settings_service.get_int(db, "shorts_video_seconds_max", 60),
        )
        src = fetch_saju_video_source(db, job.message_id, is_admin=True)  # 워커=신뢰 컨텍스트
        scn = _scenario.generate_scenario(src, seconds=seconds)
        scn["title"] = _resolve_title(db, job)   # "{닉네임}님의 사주영상"
        job.scenario_json = scn
        db.commit()

        _set_stage(db, job, "tts", "내레이션을 만들고 있어요")
        engine = settings_service.get(db, "shorts_tts_engine", "openai")
        rkind = settings_service.get(db, "shorts_renderer", "talk").lower()
        W, H = (1080, 1920) if job.aspect == "9x16" else (1920, 1080)
        work.mkdir(parents=True, exist_ok=True)

        scenes = scn["scenes"]
        character = scn.get("character", {})
        zodiac = character.get("zodiac") or getattr(src, "zodiac", "") or ""
        # 말하는 캐릭터(flap): 해당 띠가 베이크돼 있고 렌더러가 talk면. 아니면 기존(code/flux)
        talking = rkind in ("talk", "auto") and _renderer.talking_available(zodiac)
        renderer = None if talking else get_renderer(rkind)

        if talking:
            # 단계는 시나리오 JSON '키'(초년~노년)에서 확정 → 신뢰. 안전하게 시간순 정렬만(누락 시 위치 보정).
            _order = ["초년", "유년", "청년", "장년", "노년"]
            _rank = {s: i for i, s in enumerate(_order)}
            _n = len(scenes)
            for _idx, sc in enumerate(scenes):
                if sc.get("stage") not in _rank:
                    sc["stage"] = _order[min(4, round((_idx / (_n - 1) if _n > 1 else 0) * 4))]
            scenes.sort(key=lambda sc: _rank[sc["stage"]])
            scn["scenes"] = scenes

        for i, sc in enumerate(scenes):
            # 성별·생애단계·감정선별 최적 음성 더빙(감정 이입, 애기=피치업)
            sc["wav"] = _tts.synth(
                engine, sc["line"], str(work / f"v{i}.wav"),
                gender=src.gender, stage=sc.get("stage", ""), emotion=sc.get("emotion", ""),
            )
            if talking:
                pair = _renderer.talking_stills(zodiac, sc.get("stage", ""), W, H, str(work), i)
                sc["closed"], sc["open"] = pair          # closed=정지 입(현재 사용), open=립싱크 복원용 보존
                # 입 움직임 비활성화(2026-06-29): 비세메 로딩 주석 처리. 다른 엔진 도입 시 해제.
                # sc["viseme"] = _renderer.viseme_shapes(zodiac, sc.get("stage", ""), W, H, str(work), i)  # 비세메(있으면 립싱크)
                sc["sub"] = _renderer.render_subtitle_overlay(sc["line"], W, H, str(work / f"sub{i}.png"))
            else:
                sc["frame"] = renderer.render_scene(sc, character, W, H, str(work / f"f{i}.png"))

        _set_stage(db, job, "compose", "영상을 합성하고 있어요")
        rel = f"master/{job.job_token}.mp4"
        out = _abs(rel)
        out.parent.mkdir(parents=True, exist_ok=True)
        # 고정 워터마크(직인+브랜드)+타이틀 오버레이(4K). 실패해도 영상은 생성.
        UW, UH = (2160, 3840) if job.aspect == "9x16" else (3840, 2160)
        _credit = settings_service.get(db, "shorts_credit", "orion0321@gmail.com")
        overlay: str | None = str(work / "overlay.png")
        try:
            build_watermark_overlay(scn.get("title", ""), UW, UH, overlay, credit=_credit)
        except Exception:
            overlay = None
        _enc_mode = settings_service.get(db, "shorts_encoder_mode", "cpu")
        _cq = settings_service.get_int(db, "shorts_master_cq", 20)
        _gate = settings_service.get_int(db, "shorts_nvenc_vram_gate_mb", 3000)
        _gpu = settings_service.get_int(db, "shorts_gpu_index", 1)  # 사주 자원=GPU1(+CPU). GPU0은 타 서비스용
        # BGM(배경음악): assets/bgm/{설정파일}. 'none'이면 무음.
        _bgm_name = settings_service.get(db, "shorts_bgm", "auto")
        if _bgm_name.lower() == "auto":          # 분위기 자동 매칭
            _bgm_name = _pick_bgm_name(scenes)
        _bgm_file = Path(__file__).resolve().parent.parent / "assets" / "bgm" / _bgm_name
        _bgm = str(_bgm_file) if (_bgm_name.lower() != "none" and _bgm_file.exists()) else None
        if talking:
            _, used, fb = _compose.compose_talking(
                scenes, job.aspect, str(out), str(work),
                encoder_mode=_enc_mode, cq=_cq, vram_gate_mb=_gate, overlay_png=overlay, bgm_path=_bgm,
                credit=_credit, gpu_index=_gpu,
            )
        else:
            _, used, fb = _compose.compose(
                scenes, job.aspect, str(out), str(work),
                encoder_mode=_enc_mode, cq=_cq, vram_gate_mb=_gate, overlay_png=overlay, gpu_index=_gpu,
            )

        _set_stage(db, job, "finalize")
        # done 전이는 status='running'일 때만(다중워커 회수 경합 시 납품+환불 동시 차단).
        res = db.execute(
            update(SajuVideoJob)
            .where(SajuVideoJob.id == job.id, SajuVideoJob.status == "running")
            .values(master_path=rel, delivery_path=rel, encoder_used=used, gpu_gate_fallback=fb,
                    status="done", progress_pct=100, detail="완료", completed_at=datetime.utcnow())
        )
        db.commit()
        if res.rowcount != 1:
            # 이미 회수/실패로 전이됨 → done 미부여, 산출물 파기(고아 파일 방지)
            try:
                if out.exists():
                    out.unlink()
            except OSError:
                pass
            return db.get(SajuVideoJob, job.id)
    except Exception as e:  # noqa: BLE001
        import logging
        logging.getLogger("saju.video").exception("run_job failed: %s", job.job_token)
        db.rollback()
        job = db.get(SajuVideoJob, job.id)
        job.status = "failed"
        code = e.code if isinstance(e, VideoSourceError) else type(e).__name__
        job.detail = f"생성 실패({code})"
        db.commit()
        try:
            refund_job(db, job)        # 실패 → 자동 환불(멱등, status='failed' 가드)
        except Exception:              # 환불 실패는 _recover 고아보정이 재시도(관측 로그)
            import logging
            logging.getLogger("saju.video").warning("refund failed for job %s", job.job_token)
        # 부분 산출물 파기(디스크 누수 방지)
        p = _abs(f"master/{job.job_token}.mp4")
        try:
            if p and p.exists():
                p.unlink()
        except OSError:
            pass
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return job


# ───────────────────────── 보관/삭제(48h) ─────────────────────────
def expire_due(db: Session) -> int:
    """expires_at 지난 done 작업의 파일 삭제 + status=expired. 반환=처리건수."""
    now = datetime.utcnow()
    rows = (
        db.query(SajuVideoJob)
        .filter(SajuVideoJob.status == "done", SajuVideoJob.expires_at < now)
        .all()
    )
    n = 0
    for job in rows:
        for rel in (job.master_path, job.delivery_path):
            p = _abs(rel)
            if p and p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass
        job.status = "expired"
        job.detail = "보관기간 만료(삭제됨)"
        n += 1
    if n:
        db.commit()
    return n
