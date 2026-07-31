$ErrorActionPreference='Continue'
$base='http://127.0.0.1:8000'
function L($email,$pw){
  try { return Invoke-RestMethod -Uri "$base/api/auth/login" -Method Post -ContentType 'application/json' -Body (@{email=$email;password=$pw}|ConvertTo-Json) } catch { return $null }
}
$u = L 'test_user_001@example.com' 'testpass1234'
if(-not $u){ $u = L 'test_user_001@example.com' 'password1234' }
if(-not $u){
  # 새 유저 생성
  $em="pay_$(Get-Random)@ex.com"
  Invoke-RestMethod -Uri "$base/api/auth/register" -Method Post -ContentType 'application/json' -Body (@{email=$em;password='testpass1234';nickname='pay'}|ConvertTo-Json) | Out-Null
  $u = L $em 'testpass1234'
  Write-Host "Created $em"
}
$H=@{Authorization="Bearer $($u.access_token)"}
Write-Host "=== 1 packages ==="
(Invoke-RestMethod -Uri "$base/api/payments/packages").items | Format-Table
Write-Host "=== 2 me before ==="
$me=Invoke-RestMethod -Uri "$base/api/auth/me" -Headers $H
"balance=$($me.balance) ads_hidden=$($me.ads_hidden)"
Write-Host "=== 3 create order 30000 ==="
$o=Invoke-RestMethod -Uri "$base/api/payments/orders" -Method Post -Headers $H -ContentType 'application/json' -Body '{"amount":30000}'
$o | ConvertTo-Json -Depth 4
Write-Host "=== 4 confirm (mock) ==="
$body=@{payment_key='mock_pk_test';order_id=$o.order_id;amount=$o.amount}|ConvertTo-Json
$c=Invoke-RestMethod -Uri "$base/api/payments/confirm" -Method Post -Headers $H -ContentType 'application/json' -Body $body
$c | ConvertTo-Json -Depth 4
Write-Host "=== 5 confirm again (idempotent) ==="
$c2=Invoke-RestMethod -Uri "$base/api/payments/confirm" -Method Post -Headers $H -ContentType 'application/json' -Body $body
"already=$($c2.already) balance=$($c2.balance)"
Write-Host "=== 6 me after ==="
$me2=Invoke-RestMethod -Uri "$base/api/auth/me" -Headers $H
"balance=$($me2.balance) ads_hidden=$($me2.ads_hidden)"
Write-Host "=== 7 history ==="
(Invoke-RestMethod -Uri "$base/api/payments/me" -Headers $H).items | Select order_id,amount,credit_granted,status | Format-Table
Write-Host "=== 8 bad amount 400 ==="
try { Invoke-RestMethod -Uri "$base/api/payments/orders" -Method Post -Headers $H -ContentType 'application/json' -Body '{"amount":7777}' } catch { "status=$($_.Exception.Response.StatusCode.value__)" }
Write-Host "=== 9 amount mismatch 400 ==="
$o2=Invoke-RestMethod -Uri "$base/api/payments/orders" -Method Post -Headers $H -ContentType 'application/json' -Body '{"amount":10000}'
$bad=@{payment_key='m';order_id=$o2.order_id;amount=99999}|ConvertTo-Json
try { Invoke-RestMethod -Uri "$base/api/payments/confirm" -Method Post -Headers $H -ContentType 'application/json' -Body $bad } catch { "status=$($_.Exception.Response.StatusCode.value__)" }
Write-Host "=== 10 no auth 401 ==="
try { Invoke-RestMethod -Uri "$base/api/payments/orders" -Method Post -ContentType 'application/json' -Body '{"amount":10000}' } catch { "status=$($_.Exception.Response.StatusCode.value__)" }
Write-Host "=== 11 webhook CANCELED ==="
$wb=@{eventType='PAYMENT_STATUS_CHANGED';data=@{orderId=$o.order_id;status='CANCELED'}}|ConvertTo-Json -Depth 4
Invoke-RestMethod -Uri "$base/api/payments/webhook" -Method Post -ContentType 'application/json' -Body $wb | ConvertTo-Json -Depth 4
