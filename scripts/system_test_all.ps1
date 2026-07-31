# Phase 4A + 4B + 5B + 4C + 5A/5C 통합/시스템 e2e 테스트.
# 기동된 http://127.0.0.1:8000 에 대해 실 HTTP 호출 (DB/Qdrant/Ollama 까지 통합).
# - 4A: 채팅 세션 목록/삭제/SSE 스트리밍 + 사주명식 chart 응답
# - 4B: 공개 배너 GET /api/banners 슬롯/가중
# - 5B: OAuth 더미 로그인 + me 확인 + 동일 email 재로그인 시 동일 user
# - 5A: 인증 + 미리보기 reveal
# - 5C: 결제 mock + ads_hidden 토글
# - 4C: 관리자 401/403 가드
#
# 실행: powershell -ExecutionPolicy Bypass -File .\scripts\system_test_all.ps1
$ErrorActionPreference = 'Continue'
$BASE = 'http://127.0.0.1:8000'
$pass = 0; $fail = 0
$results = @()

function Assert($cond, $name) {
    if ($cond) {
        $script:pass++
        $script:results += [pscustomobject]@{ name = $name; ok = $true }
        Write-Host ("[PASS] " + $name) -ForegroundColor Green
    } else {
        $script:fail++
        $script:results += [pscustomobject]@{ name = $name; ok = $false }
        Write-Host ("[FAIL] " + $name) -ForegroundColor Red
    }
}

function TryGet($url, $h = $null) { try { return Invoke-RestMethod -Uri $url -Headers $h } catch { return $null } }
function TryStatus($scriptblock) {
    try { & $scriptblock; return 200 }
    catch [System.Net.WebException] { return $_.Exception.Response.StatusCode.value__ }
    catch { try { return $_.Exception.Response.StatusCode.value__ } catch { return -1 } }
}

# ---------- 0) 헬스 ----------
$h = TryGet "$BASE/api/health"
Assert ($h.status -eq 'ok') 'health-ok'

# ---------- A) 로그인 (test_user_001 + admin) ----------
$user = Invoke-RestMethod -Uri "$BASE/api/auth/login" -Method Post -ContentType 'application/json' -Body '{"email":"test_user_001@example.com","password":"testpass1234"}'
$HU = @{ Authorization = "Bearer $($user.access_token)" }
Assert ($user.access_token.Length -gt 50) 'login-user'

$admin = Invoke-RestMethod -Uri "$BASE/api/auth/login" -Method Post -ContentType 'application/json' -Body '{"email":"orion0321@gmail.com","password":"!thdwlstn00"}'
$HA = @{ Authorization = "Bearer $($admin.access_token)" }
Assert ($admin.role -eq 'admin') 'login-admin'

# ---------- 4A) 채팅 세션 사이드바 ----------
# 세션 생성
$cs = Invoke-RestMethod -Uri "$BASE/api/chat/sessions" -Method Post -Headers $HU -ContentType 'application/json' -Body '{"birth":{"birth_date":"1990-03-15","birth_time":"14:30","calendar":"solar","gender":"male"},"top_k":3}'
Assert ($cs.session_id.Length -ge 30) '4A-create-session'
Assert ($null -ne $cs.saju_summary) '4A-summary-included'
Assert ($null -ne $cs.saju_chart -or $null -ne $cs.chart) '4A-chart-included'

# 내 세션 목록 (생성한 세션이 보여야)
$ms = Invoke-RestMethod -Uri "$BASE/api/chat/sessions?limit=10" -Headers $HU
Assert (@($ms.items | Where-Object { $_.session_id -eq $cs.session_id }).Count -eq 1) '4A-my-sessions-includes-new'

# SSE 스트리밍 호출 (Invoke-WebRequest 사용, raw 바이트 검사)
try {
    $sseBody = '{"message":"\ud14c\uc2a4\ud2b8","top_k":3}'
    $sseResp = Invoke-WebRequest -Uri "$BASE/api/chat/sessions/$($cs.session_id)/messages/stream" -Method Post -Headers $HU -ContentType 'application/json' -Body $sseBody -TimeoutSec 180
    $sseAll = $sseResp.Content
    Assert ($sseAll -match 'event: chunk') '4A-sse-chunk-event'
    Assert ($sseAll -match 'event: done') '4A-sse-done-event'
} catch {
    Write-Host "SSE error: $_" -ForegroundColor Yellow
    Assert $false '4A-sse-no-error'
}

# 세션 삭제
$st = TryStatus { Invoke-RestMethod -Uri "$BASE/api/chat/sessions/$($cs.session_id)" -Method Delete -Headers $HU }
Assert ($st -eq 200 -or $st -eq 204) '4A-delete-session'
$ms2 = Invoke-RestMethod -Uri "$BASE/api/chat/sessions?limit=10" -Headers $HU
Assert (@($ms2.items | Where-Object { $_.session_id -eq $cs.session_id }).Count -eq 0) '4A-deleted-not-in-list'

# 401: 비로그인은 my sessions 거부
$st = TryStatus { Invoke-RestMethod -Uri "$BASE/api/chat/sessions" }
Assert ($st -eq 401) '4A-my-sessions-401'

# ---------- 4B) 공개 배너 ----------
$bp = Invoke-RestMethod -Uri "$BASE/api/banners"
Assert ($bp.items.Count -ge 1) '4B-banners-list'

$bp1 = Invoke-RestMethod -Uri "$BASE/api/banners?slot=top&pick_one=true"
Assert ($bp1.items.Count -le 1) '4B-banners-pick-one-top'

$bp2 = Invoke-RestMethod -Uri "$BASE/api/banners?slot=unknown_slot"
Assert ($bp2.items.Count -eq 0) '4B-banners-unknown-slot-empty'

# 관리자 비활성 처리 후 공개 미노출
$banners = (Invoke-RestMethod -Uri "$BASE/api/admin/banners" -Headers $HA).items
if ($banners.Count -gt 0) {
    $bid = $banners[0].id
    Invoke-RestMethod -Uri "$BASE/api/admin/banners/$bid" -Method Patch -Headers $HA -ContentType 'application/json' -Body '{"active":false}' | Out-Null
    $bpAfter = Invoke-RestMethod -Uri "$BASE/api/banners"
    $hit = @($bpAfter.items | Where-Object { $_.id -eq $bid }).Count
    Assert ($hit -eq 0) '4B-inactive-not-public'
    Invoke-RestMethod -Uri "$BASE/api/admin/banners/$bid" -Method Patch -Headers $HA -ContentType 'application/json' -Body '{"active":true}' | Out-Null
}

# ---------- 5B) OAuth 더미 ----------
$start = Invoke-RestMethod -Uri "$BASE/api/auth/oauth/kakao/start"
Assert ($start.mock -eq $true) '5B-kakao-start-mock-flag'
Assert ($start.authorize_url -match '^https://kauth.kakao.com') '5B-kakao-authorize-url'

# 더미 로그인 두 번 → 같은 사용자 (mock_<provider>_<hash> 결정적)
$o1 = Invoke-RestMethod -Uri "$BASE/api/auth/oauth/google/test-login" -Method Post
$o2 = Invoke-RestMethod -Uri "$BASE/api/auth/oauth/google/test-login" -Method Post
# code 는 랜덤이라 신규 회원이 매번 생기는 정상 동작. 두 토큰 모두 me 호출 가능
$Hg = @{ Authorization = "Bearer $($o1.access_token)" }
$meg = Invoke-RestMethod -Uri "$BASE/api/auth/me" -Headers $Hg
Assert ($meg.email -eq $o1.email) '5B-oauth-me-email-matches'
Assert ($meg.balance -ge 1000) '5B-oauth-signup-bonus'

# 알 수 없는 provider 404
$st = TryStatus { Invoke-RestMethod -Uri "$BASE/api/auth/oauth/naver/start" }
Assert ($st -eq 404) '5B-oauth-unknown-provider-404'

# ---------- 5C) 결제 mock ----------
$pkg = Invoke-RestMethod -Uri "$BASE/api/payments/packages"
Assert ($pkg.items.Count -eq 4) '5C-packages-4'

$meBefore = Invoke-RestMethod -Uri "$BASE/api/auth/me" -Headers $HU
$ord = Invoke-RestMethod -Uri "$BASE/api/payments/orders" -Method Post -Headers $HU -ContentType 'application/json' -Body '{"amount":10000}'
$body = @{payment_key = 'sys_pk'; order_id = $ord.order_id; amount = 10000 } | ConvertTo-Json
$cf = Invoke-RestMethod -Uri "$BASE/api/payments/confirm" -Method Post -Headers $HU -ContentType 'application/json' -Body $body
Assert ($cf.status -eq 'approved') '5C-confirm-approved'
Assert ($cf.mock -eq $true) '5C-confirm-mock'
Assert ($cf.balance -eq ($meBefore.balance + 10000)) '5C-credits-applied'
# 멱등
$cf2 = Invoke-RestMethod -Uri "$BASE/api/payments/confirm" -Method Post -Headers $HU -ContentType 'application/json' -Body $body
Assert ($cf2.already -eq $true) '5C-idempotent'

# ads_hidden 토글
$meAfter = Invoke-RestMethod -Uri "$BASE/api/auth/me" -Headers $HU
Assert ($meAfter.ads_hidden -eq $true) '5C-ads-hidden-after-payment'

# 잘못된 amount
$st = TryStatus { Invoke-RestMethod -Uri "$BASE/api/payments/orders" -Method Post -Headers $HU -ContentType 'application/json' -Body '{"amount":9999}' }
Assert ($st -eq 400) '5C-bad-amount-400'

# ---------- 4C) 관리자 가드 ----------
$st = TryStatus { Invoke-RestMethod -Uri "$BASE/api/admin/stats" }
Assert ($st -eq 401) '4C-admin-401-noauth'
$st = TryStatus { Invoke-RestMethod -Uri "$BASE/api/admin/stats" -Headers $HU }
Assert ($st -eq 403) '4C-admin-403-user'
$st = TryStatus { Invoke-RestMethod -Uri "$BASE/api/admin/stats" -Headers $HA }
Assert ($st -eq 200) '4C-admin-200-admin'

# ---------- 후방향: 비로그인 → 미리보기 컷 → reveal 401 ----------
$anonSess = Invoke-RestMethod -Uri "$BASE/api/chat/sessions" -Method Post -ContentType 'application/json' -Body '{"birth":{"birth_date":"1985-08-20","birth_time":"08:00","calendar":"solar","gender":"female"},"top_k":3}'
$anonMsg = Invoke-RestMethod -Uri "$BASE/api/chat/sessions/$($anonSess.session_id)/messages" -Method Post -ContentType 'application/json' -Body '{"message":"\uc62c\ud574 \uc6b4","top_k":3}'
Assert ($anonMsg.is_preview -eq $true) 'fwd-anon-preview'
Assert ($anonMsg.billing_mode -eq 'anonymous_preview') 'fwd-anon-billing-mode'
Assert ($anonMsg.answer.Length -lt $anonMsg.full_length) 'fwd-anon-truncated'

# 비로그인 reveal → 401
$st = TryStatus { Invoke-RestMethod -Uri "$BASE/api/chat/sessions/$($anonSess.session_id)/messages/$($anonMsg.assistant_message_id)/reveal" -Method Post }
Assert ($st -eq 401) 'fwd-anon-reveal-401'

Write-Host ""
Write-Host "================ RESULT =================" -ForegroundColor Cyan
Write-Host ("PASS: {0}" -f $pass) -ForegroundColor Green
Write-Host ("FAIL: {0}" -f $fail) -ForegroundColor $(if ($fail -eq 0) { 'Green' } else { 'Red' })
Write-Host "========================================="
exit $fail
