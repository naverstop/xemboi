# Saju Agent 운영 배포 가이드

> 도메인: **saju.songstock.art** (Cloudflare)
> 호스트: Windows 11 네이티브, 24/7

## 아키텍처

```
사용자 브라우저 (HTTPS)
        │
        ▼
   Cloudflare Edge (TLS 종단, WAF, 캐싱)
        │
        ▼ (cf-tunnel, 아웃바운드 only — 포트포워딩 불필요)
   cloudflared (NSSM 서비스 SajuCloudflared)
        │
        ▼ HTTP :8080
   Caddy (NSSM 서비스 SajuCaddy)
        ├── /api/*  → uvicorn :8000 (NSSM 서비스 SajuBackend)
        └── /*      → 빌드된 React 정적 파일 (C:\sajufe\dist)
```

## 설치 절차 (1회)

### 1) 인프라
```powershell
# Docker Desktop (Qdrant + Redis)
docker compose -f infra\docker\docker-compose.yml up -d

# PostgreSQL 16 (Windows 네이티브 서비스 — 이미 설치/실행 중)
# Ollama (Windows 앱 — 이미 설치, 자동 기동)
```

### 2) 백엔드 / 프론트엔드 빌드
```powershell
# 백엔드
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000   # 동작 검증
# 프론트
cd C:\sajufe
$env:PATH="$env:LOCALAPPDATA\nodejs;$env:PATH"
npx vite build   # → C:\sajufe\dist
```

### 3) 에지 도구 설치
```powershell
winget install --id Caddy.Caddy                       # 또는 caddyserver.com/download → C:\caddy\caddy.exe
winget install --id Cloudflare.cloudflared            # cloudflared.exe
winget install --id NSSM.NSSM                          # nssm.exe
```

### 4) Cloudflare Tunnel 생성
```powershell
cloudflared tunnel login                              # 브라우저 인증
cloudflared tunnel create saju-agent                  # → UUID 출력
cloudflared tunnel route dns saju-agent saju.songstock.art
# infra\cloudflared\config.yml 의 REPLACE_WITH_TUNNEL_UUID 두 곳을 위 UUID 로 치환
```

### 5) NSSM 서비스 등록
```powershell
# 관리자 PowerShell
powershell -ExecutionPolicy Bypass -File infra\nssm\install_services.ps1
Start-Service SajuBackend, SajuCaddy, SajuCloudflared, SajuFrontend
Get-Service Saju*
```

### 6) `.env` 운영 키 입력
- `toss_client_key` / `toss_secret_key` — 토스페이먼츠 실키 (DUMMY 문자열 제거)
- `kakao_client_id` / `kakao_client_secret` / `kakao_redirect_uri` — 카카오 디벨로퍼스
- `google_client_id` / `google_client_secret` / `google_redirect_uri` — Google Cloud Console
- `jwt_secret` — 임의 32+자 무작위 문자열
- `database_url` — 운영 비번으로 변경

> 실키 입력 후 `Restart-Service SajuBackend` 만 하면 즉시 활성화 (코드 변경 불필요).

## 일상 운영

| 작업 | 명령 |
|---|---|
| 전체 기동 | `start.bat` (개발용 — 빠른 로컬 검증) |
| 운영 기동 | NSSM 서비스 자동 (재부팅 시 자동 시작) |
| 로그 확인 | `Get-Content logs\backend.err.log -Tail 100 -Wait` |
| 백엔드 재기동 | `Restart-Service SajuBackend` |
| 프론트 재배포 | `cd C:\sajufe; npx vite build; Restart-Service SajuFrontend` |
| 서비스 해제 | `infra\nssm\install_services.ps1 -Uninstall` |

## 헬스체크
- 외부: `https://saju.songstock.art/api/health`
- 내부: `http://127.0.0.1:8000/api/health`, `http://127.0.0.1:8080/healthz`

## 백업 (수동)
```powershell
# Postgres dump
& 'C:\Program Files\PostgreSQL\16\bin\pg_dump.exe' -h 127.0.0.1 -U saju saju_db `
   -F c -f "backup\saju_db_$(Get-Date -Format yyyyMMdd_HHmm).dump"
# Qdrant snapshot
curl -X POST http://127.0.0.1:6333/collections/saju_corpus/snapshots
```

## 알려진 운영 주의사항
- Cloudflare 무료 플랜: 단일 도메인 100 요청/일 제한 없음(WAF 챌린지만 적용). DDoS 시 Cloudflare가 1차 방어.
- cloudflared 는 IPv4/IPv6 모두 outbound 443 만 사용. 방화벽 인바운드 오픈 불필요.
- Caddy `auto_https off`: TLS 는 Cloudflare 가 종단 — origin 인증서 불필요.
- 백엔드는 항상 127.0.0.1 만 바인딩. 외부 직접 접근 차단.
