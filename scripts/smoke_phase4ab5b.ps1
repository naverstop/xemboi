$ErrorActionPreference='Continue'
$base='http://127.0.0.1:8000'
$u=Invoke-RestMethod -Uri "$base/api/auth/login" -Method Post -ContentType 'application/json' -Body '{"email":"test_user_001@example.com","password":"testpass1234"}'
$H=@{Authorization="Bearer $($u.access_token)"}
Write-Host "=== my sessions"
$ms=Invoke-RestMethod -Uri "$base/api/chat/sessions?limit=5" -Headers $H
$ms | ConvertTo-Json -Depth 4
Write-Host "=== oauth kakao start"
$ks=Invoke-RestMethod -Uri "$base/api/auth/oauth/kakao/start"
$ks | ConvertTo-Json
Write-Host "=== oauth kakao test-login (dummy)"
$kt=Invoke-RestMethod -Uri "$base/api/auth/oauth/kakao/test-login" -Method Post
$kt | ConvertTo-Json
Write-Host "=== oauth google test-login (dummy)"
$gt=Invoke-RestMethod -Uri "$base/api/auth/oauth/google/test-login" -Method Post
$gt | ConvertTo-Json
Write-Host "=== verify oauth user (me)"
$H2=@{Authorization="Bearer $($gt.access_token)"}
(Invoke-RestMethod -Uri "$base/api/auth/me" -Headers $H2) | ConvertTo-Json
Write-Host "=== banners public"
(Invoke-RestMethod -Uri "$base/api/banners") | ConvertTo-Json -Depth 4
Write-Host "=== banners pick_one"
(Invoke-RestMethod -Uri "$base/api/banners?pick_one=true") | ConvertTo-Json -Depth 4
Write-Host "=== admin create banner top"
$adm=Invoke-RestMethod -Uri "$base/api/auth/login" -Method Post -ContentType 'application/json' -Body '{"email":"orion0321@gmail.com","password":"!thdwlstn00"}'
$HA=@{Authorization="Bearer $($adm.access_token)"}
Invoke-RestMethod -Uri "$base/api/admin/banners" -Method Post -Headers $HA -ContentType 'application/json' -Body '{"slot":"top","image_url":"https://placehold.co/728x90?text=SAJU","link_url":"https://saju.songstock.art","title":"오늘의 운세","weight":50}' | ConvertTo-Json
Invoke-RestMethod -Uri "$base/api/admin/banners" -Method Post -Headers $HA -ContentType 'application/json' -Body '{"slot":"chat_top_1","image_url":"https://placehold.co/600x90?text=ChatTop","weight":30}' | ConvertTo-Json
Invoke-RestMethod -Uri "$base/api/admin/banners" -Method Post -Headers $HA -ContentType 'application/json' -Body '{"slot":"side_1","image_url":"https://placehold.co/200x600?text=Side1","weight":20}' | ConvertTo-Json
Invoke-RestMethod -Uri "$base/api/admin/banners" -Method Post -Headers $HA -ContentType 'application/json' -Body '{"slot":"answer_bottom","image_url":"https://placehold.co/728x90?text=AnswerBottom","weight":15}' | ConvertTo-Json
Write-Host "=== banners after"
(Invoke-RestMethod -Uri "$base/api/banners?pick_one=true") | ConvertTo-Json -Depth 4
