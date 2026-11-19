# Проверка стека Autello (часть 3) для Windows (PowerShell 5.1+ / 7+) → reports\check_report.md
#   powershell -ExecutionPolicy Bypass -File scripts\check.ps1
# Логика та же, что в scripts/check.sh. Нужны Docker Desktop и curl.exe (есть в Windows 10+).
# Все HTTP-запросы — через curl.exe -k: самоподписанный сертификат (make certs) PowerShell 5.1 иначе не примет.
$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path .env)) { Write-Error 'Нет .env — выполните: Copy-Item example.env .env'; exit 1 }
$envs = @{}
Get-Content .env -Encoding UTF8 | Where-Object { $_ -match '^\s*[^#\s][^=]*=' } | ForEach-Object {
    $k, $v = $_ -split '=', 2; $envs[$k.Trim()] = $v.Trim()
}
function Env([string]$Name, [string]$Default) { if ($envs[$Name]) { $envs[$Name] } else { $Default } }

$HttpPort  = Env 'HTTP_PORT' '80'
$HttpsPort = Env 'HTTPS_PORT' '443'
$HttpBase  = if ($HttpPort -eq '80') { 'http://localhost' } else { "http://localhost:$HttpPort" }
$HttpsBase = if ($HttpsPort -eq '443') { 'https://localhost' } else { "https://localhost:$HttpsPort" }
$Base = $HttpsBase
$AdminUser = Env 'DEMO_ADMIN_USER' 'admin'
$AdminPass = Env 'DEMO_ADMIN_PASSWORD' 'change_me_demo'
$PgUser = Env 'POSTGRES_USER' 'autello'
$PgDb   = Env 'POSTGRES_DB' 'autello'
$NginxMode = ((docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' nginx 2>$null) | Where-Object { $_ -like 'NGINX_MODE=*' }) -replace 'NGINX_MODE=', ''
if (-not $NginxMode) { $NginxMode = 'неизвестен' }

$script:Rows = New-Object System.Collections.Generic.List[string]
$script:Pass = 0; $script:Fail = 0; $script:Skip = 0; $script:Section = ''
$TmpBody = Join-Path ([System.IO.Path]::GetTempPath()) 'autello_check_body.json'

function Section([string]$Name) { $script:Section = $Name; Write-Host "`n=== $Name ===" }
function Add-Result([bool]$Ok, [string]$Name, [string]$Detail) {
    $Detail = ($Detail -replace '\|', '/' -replace "`r?`n", ' ')
    if ($Detail.Length -gt 200) { $Detail = $Detail.Substring(0, 200) + '…' }
    if ($Ok) { $script:Pass++; $icon = '✅'; $color = 'Green' } else { $script:Fail++; $icon = '❌'; $color = 'Red' }
    $script:Rows.Add("| $icon | $($script:Section) | $Name | $Detail |")
    Write-Host "$icon $Name — $Detail" -ForegroundColor $color
}
function Add-Skip([string]$Name, [string]$Detail) {
    $script:Skip++; $script:Rows.Add("| ⏭ | $($script:Section) | $Name | $Detail |"); Write-Host "⏭ $Name — $Detail" -ForegroundColor Yellow
}
# HTTP-код ответа
function Get-Code([string]$Url, [string[]]$Extra = @()) {
    $a = @('-sk', '-o', 'NUL', '-w', '%{http_code}', '--max-time', '10') + $Extra
    (& curl.exe @a $Url) 2>$null
}
# Тело ответа как объект (JSON) или $null. JSON-тело передаём файлом — так кавычки не ломаются в PowerShell 5.1
function Invoke-Api([string]$Method, [string]$Path, $Body = $null, [string]$Token = '', [hashtable]$Form = $null) {
    $a = @('-sk', '--max-time', '15', '-X', $Method)
    if ($Token) { $a += @('-H', "Authorization: Bearer $Token") }
    if ($Form) { foreach ($k in $Form.Keys) { $a += @('--data-urlencode', "$k=$($Form[$k])") } }
    elseif ($null -ne $Body) {
        [System.IO.File]::WriteAllText($TmpBody, ($Body | ConvertTo-Json -Compress -Depth 5), (New-Object System.Text.UTF8Encoding $false))
        $a += @('-H', 'Content-Type: application/json', '--data-binary', "@$TmpBody")
    }
    $raw = (& curl.exe @a "$Base$Path") -join "`n"
    try { $raw | ConvertFrom-Json } catch { $null }
}
function Psql([string]$Sql) { ((docker compose exec -T postgres psql -U $PgUser -d $PgDb -tAc $Sql) -join '').Trim() }
Write-Host "Режим nginx: $NginxMode · API: $Base"

# =====================================================================
Section 'Контейнеры'
$composePs = (docker compose --profile admin-tools ps --format 'table {{.Name}}\t{{.Service}}\t{{.Status}}\t{{.Ports}}') -join "`n"
$dockerPs  = (docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}') -join "`n"
Write-Host $composePs
foreach ($svc in 'backend', 'postgres', 'nginx') {
    $cid = docker compose ps -q $svc
    if (-not $cid) { Add-Result $false "$svc запущен" 'контейнер не найден'; continue }
    $st = docker inspect -f '{{.State.Status}}{{if .State.Health}}/{{.State.Health.Status}}{{end}}' $cid
    Add-Result ($st -eq 'running/healthy' -or $st -eq 'running') "${svc}: running/healthy" $st
}

# =====================================================================
Section 'Авторизация (п.1)'
$chk = Invoke-Api GET '/api/auth/check'
Add-Result ($chk.has_admins -eq $true) 'GET /api/auth/check' "has_admins=$($chk.has_admins)"
$login = Invoke-Api POST '/api/auth/login' -Form @{ username = $AdminUser; password = $AdminPass }
$Token = $login.access_token
Add-Result ([bool]$Token) 'POST /api/auth/login (form-data) → JWT' $(if ($Token) { "длина $($Token.Length)" } else { 'нет токена' })
$authH = @('-H', "Authorization: Bearer $Token")
$c = Get-Code "$Base/api/auth/me" $authH;                                   Add-Result ($c -eq '200') 'GET /api/auth/me с токеном' "HTTP $c"
$c = Get-Code "$Base/api/admin-settings/1" @('-X', 'DELETE');               Add-Result ($c -eq '401') 'DELETE /api/admin-settings/1 без токена' "HTTP $c (ожидается 401)"
$c = Get-Code "$Base/api/applications/ranked";                              Add-Result ($c -eq '401') 'GET /api/applications/ranked без токена' "HTTP $c (ожидается 401)"

# =====================================================================
Section 'Услуги (п.2)'
$services = @(Invoke-Api GET '/api/admin-settings?only_active=true')
Add-Result ($services.Count -ge 5) 'GET /api/admin-settings — массив, ≥5 активных услуг' "$($services.Count) шт.: $(($services | ForEach-Object { $_.services }) -join ', ')"
$name = "check.ps1 услуга $(Get-Date -Format HHmmss)"
$created = Invoke-Api POST '/api/admin-settings' @{ services = $name; budget_min = 1000; budget_max = 5000 } $Token
$sid = $created.id
$put = Invoke-Api PUT "/api/admin-settings/$sid" @{ budget_max = 7000 } $Token
$del = Get-Code "$Base/api/admin-settings/$sid" (@('-X', 'DELETE') + $authH)
$gone = -not (@(Invoke-Api GET '/api/admin-settings?only_active=true') | Where-Object { $_.id -eq $sid })
Add-Result ($sid -and $put.budget_max -eq 7000 -and $del -eq '204' -and $gone) 'CRUD-цикл услуги с токеном' "POST → id $sid, PUT → budget_max $($put.budget_max), DELETE → $del, исчезла: $gone"

# =====================================================================
Section 'Метрики (п.3)'
if (Test-Path reports\visitor_activity.json) {
    $va = Get-Content reports\visitor_activity.json -Raw -Encoding UTF8 | ConvertFrom-Json
    $r = $va.metrics_rows
    Add-Result ($r.during_12s -gt $r.before -and $r.after -ge $r.before + 3) 'count(*) behavior_metrics растёт во время visitor_activity (e2e)' "до: $($r.before), через 12 с: $($r.during_12s), после: $($r.after); долгий визит $($va.visits[0].time_on_page) с"
} else { Add-Result $false 'count(*) behavior_metrics растёт во время visitor_activity (e2e)' 'нет reports\visitor_activity.json — запустите e2e' }
$n0 = [int](Psql 'SELECT count(*) FROM behavior_metrics')
$sess = "check-ps-$(Get-Date -Format HHmmss)"
foreach ($t in 1..3) {
    $null = Invoke-Api POST '/api/behavior-metrics' @{ application_id = 0; time_on_page = $t; buttons_clicked = '{"submit":1}'; cursor_positions = '[{"x":0.4,"y":0.3}]'; return_frequency = 0; session_id = $sess }
    Start-Sleep -Seconds 1
}
$n1 = [int](Psql 'SELECT count(*) FROM behavior_metrics')
Add-Result ($n1 - $n0 -eq 1) '3 снимка одного визита → 1 строка (upsert)' "строк было $n0, стало $n1"
$stats = Invoke-Api GET '/api/behavior-metrics/stats' $null $Token
$hasPeriods = $stats.periods.day -and $stats.periods.week -and $stats.periods.month
Add-Result ($hasPeriods -and $stats.heatmap.Count -gt 0) 'GET /api/behavior-metrics/stats: 3 периода + heatmap' "месяц: ср. $($stats.periods.month.avg_sec) с, макс. $($stats.periods.month.max_sec) с, сессий $($stats.periods.month.sessions); heatmap $($stats.heatmap.Count) ячеек"

# =====================================================================
Section 'Приоритизация (п.4)'
$ranked = @(Invoke-Api GET '/api/applications/ranked' $null $Token)
$test10 = @($ranked | Where-Object { $_.comment -like '`[тест-SQL`]*' })
$dist = '{0}/{1}/{2}' -f @($test10 | Where-Object { $_.scoring.temperature -eq 'hot' }).Count, @($test10 | Where-Object { $_.scoring.temperature -eq 'warm' }).Count, @($test10 | Where-Object { $_.scoring.temperature -eq 'cold' }).Count
Add-Result ($dist -eq '4/3/3') '/ranked: 10 тестовых заявок → 🔥/🌤/❄️' "$dist (ожидается 4/3/3)"
$sorted = $true; for ($i = 0; $i -lt $ranked.Count - 1; $i++) { if ($ranked[$i].scoring.score -lt $ranked[$i + 1].scoring.score) { $sorted = $false } }
Add-Result $sorted '/ranked отсортирован по score' "первые: $(($ranked | Select-Object -First 4 | ForEach-Object { "$($_.last_name) $($_.scoring.score)" }) -join ', ')"
$pytest = (docker compose run --rm --no-deps -T backend python -m pytest -q -p no:cacheprovider tests 2>&1 | Select-Object -Last 1) -as [string]
Add-Result ($pytest -match '\d+ passed' -and $pytest -notmatch 'failed|error') 'pytest tests/test_lead_scoring.py' $pytest

# =====================================================================
Section 'Безопасность (п.5)'
if ($NginxMode -eq 'secure') {
    $c = Get-Code "$HttpsBase/";                                   Add-Result ($c -eq '200') "curl -k $HttpsBase" "HTTP $c"
    $redir = (& curl.exe -s -o NUL -w '%{http_code} %{redirect_url}' --max-time 10 "$HttpBase/admin") 2>$null
    Add-Result ($redir -like '301 https://*') "curl $HttpBase → 301 на https" $redir
    foreach ($p in @((Env 'STUB_BACKEND_PORT' '8000'), (Env 'STUB_POSTGRES_PORT' '5432'))) {
        $c = (& curl.exe -s -o NUL -w '%{http_code}' --max-time 5 "http://localhost:$p/") 2>$null
        Add-Result ($c -eq '403') "curl http://localhost:$p → 403" "HTTP $c (заглушка nginx)"
    }
    foreach ($p in @((Env 'PGADMIN_PORT' '5050'), (Env 'REGISTRY_PORT' '5000'), (Env 'REGISTRY_UI_PORT' '8080'))) {
        & curl.exe -s -o NUL --max-time 5 "http://localhost:$p/" 2>$null; $rc = $LASTEXITCODE
        Add-Result ($rc -eq 7) "localhost:$p — соединение отклонено" "curl exit $rc"
    }
    $published = @(docker compose ps -q | ForEach-Object { if (docker port $_ 2>$null) { (docker inspect -f '{{.Name}}' $_).TrimStart('/') } }) | Sort-Object -Unique
    Add-Result (($published -join ',') -eq 'nginx') 'docker ps: порты опубликованы только у nginx' "с портами: $($published -join ', ')"
    $c1 = Get-Code "$HttpsBase/docs"; $c2 = Get-Code "$HttpsBase/openapi.json"
    Add-Result ($c1 -eq '404' -and $c2 -eq '404') '/docs и /openapi.json закрыты' "HTTP $c1 / $c2"
} else {
    foreach ($item in 'https://localhost = 200', 'http://localhost = 301', ':8000 и :5432 = 403', ':5050/:5000/:8080 закрыты', 'порты только у nginx', '/docs = 404') {
        Add-Skip $item "режим $NginxMode — запустите secure-режим и проверку ещё раз"
    }
}

Section 'Логи (п.6)'
$logs = (docker logs --tail 50 backend 2>&1) -join "`n"
Add-Result ($logs -notmatch 'Traceback') 'Последние 50 строк docker logs backend без Traceback' 'проверено'

# ---------- Отчёт ----------
$total = $script:Pass + $script:Fail
$summary = if ($script:Fail -eq 0) { "✅ Все проверки пройдены: $($script:Pass) из $total" } else { "❌ Провалено проверок: $($script:Fail) из $total" }
if ($script:Skip -gt 0) { $summary += " (пропущено в режиме ${NginxMode}: $($script:Skip))" }
New-Item -ItemType Directory -Force reports | Out-Null
$report = @(
    '# Отчёт проверки стека Autello — часть 3 (PowerShell)', '',
    "- Дата: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')",
    "- Режим nginx: **$NginxMode**", "- Адрес API в проверках: $Base", '',
    '## Итог', '', "**$summary**", '',
    '## Проверки', '', '| | Раздел | Проверка | Результат |', '|---|---|---|---|'
) + $script:Rows + @('', '## docker compose ps', '', '```', $composePs, '```', '', '## docker ps', '', '```', $dockerPs, '```', '', '## docker logs --tail 50 backend', '', '```', $logs, '```')
[System.IO.File]::WriteAllLines((Join-Path $Root 'reports\check_report.md'), $report, (New-Object System.Text.UTF8Encoding $false))
Remove-Item $TmpBody -ErrorAction SilentlyContinue
Write-Host "`n$summary"
Write-Host 'Отчёт: reports\check_report.md'
if ($script:Fail -gt 0) { exit 1 }
