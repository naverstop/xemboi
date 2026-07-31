"""SPA 캐치올 경로순회(Path Traversal) 차단 회귀 테스트 (Critical).

배경: _spa_catch 가 os.path.join(dist, full_path) 결과를 containment 검사 없이 FileResponse 로
서빙해, GET /..%2f..%2f.env 같은 인코딩된 ../ 로 dist 밖의 .env(JWT_SECRET·ANTHROPIC_API_KEY·
PII_AES_KEY 등)·소스코드를 유출할 수 있었다(라이브 재현됨). 수정: realpath 로 정규화한 실제 경로가
dist 경계 안일 때만 서빙(_spa_file_within_dist). 본 테스트가 그 차단을 회귀 검증한다.
"""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.main import _mount_spa, _spa_file_within_dist

_CANARY = "JWT_SECRET=TOPSECRET_LEAK_CANARY"


def _build_dist(tmp: str) -> str:
    dist = os.path.join(tmp, "frontend", "dist")
    os.makedirs(os.path.join(dist, "assets"))
    with open(os.path.join(dist, "index.html"), "w", encoding="utf-8") as f:
        f.write("<!doctype html><html><body>SPA-INDEX</body></html>")
    with open(os.path.join(dist, "assets", "app.js"), "w", encoding="utf-8") as f:
        f.write("console.log('ok')")
    # dist 밖 비밀 파일(.env 모사) — 절대 서빙되면 안 됨
    with open(os.path.join(tmp, "secret.env"), "w", encoding="utf-8") as f:
        f.write(_CANARY)
    return dist


def test_helper_contains_within_dist(tmp_path):
    dist = _build_dist(str(tmp_path))
    real = os.path.realpath(dist)
    # 정상 자산은 경로 반환
    assert _spa_file_within_dist(real, "assets/app.js") is not None
    assert _spa_file_within_dist(real, "index.html") is not None
    # 경로순회는 None(→ 호출부 SPA index 폴백)
    assert _spa_file_within_dist(real, "../secret.env") is None
    assert _spa_file_within_dist(real, "../../secret.env") is None
    assert _spa_file_within_dist(real, "assets/../../secret.env") is None
    # 빈 경로·디렉터리도 None
    assert _spa_file_within_dist(real, "") is None
    assert _spa_file_within_dist(real, "assets") is None


def test_route_encoded_traversal_never_leaks(tmp_path):
    dist = _build_dist(str(tmp_path))
    app = FastAPI()
    _mount_spa(app, dist)
    client = TestClient(app)

    # 핵심 보안 성질: 어떤 인코딩된 ../ 로도 비밀(.env)·소스가 절대 노출되지 않는다.
    # (/assets/* 는 StaticFiles 마운트가 자체적으로 404 로 막고, 캐치올은 SPA index 로 폴백 —
    #  둘 다 노출 0 이면 통과.)
    for path in (
        "/..%2f..%2fsecret.env",
        "/assets/..%2f..%2f..%2fsecret.env",
        "/..%2f..%2f..%2fbackend%2fapp%2fmain.py",
        "/secret.env",
    ):
        r = client.get(path)
        assert _CANARY not in r.text, f"비밀 유출됨: {path} (status={r.status_code})"
        assert "def _mount_spa" not in r.text, f"소스 유출됨: {path} (status={r.status_code})"

    # 캐치올(비-/assets) 경로순회·임의 경로는 SPA index(200 html)로 폴백
    for path in (
        "/..%2f..%2fsecret.env",
        "/..%2f..%2f..%2fbackend%2fapp%2fmain.py",
        "/some/client/route",
    ):
        r = client.get(path)
        assert r.status_code == 200 and "SPA-INDEX" in r.text, f"index 폴백 실패: {path}"

    # 정상 자산은 그대로 서빙(기능 보존)
    r = client.get("/assets/app.js")
    assert r.status_code == 200 and "console.log" in r.text
