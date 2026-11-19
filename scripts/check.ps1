# Проверка стека Autello (часть 2) для Windows (PowerShell 5.1+ / 7+) → reports\check_report.md
#   powershell -ExecutionPolicy Bypass -File scripts\check.ps1
# Логика та же, что в scripts/check.sh. Нужны Docker Desktop и curl.exe (есть в Windows 10+).
$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path .env)) { Write-Error 'Нет .env — выполните: Copy-Item example.env .env'; exit 1 }
$envs = @{}
Get-Content .env -Encoding UTF8 | Where-Object { $_ -match '^\s*[^#\s][^=]*=' } | ForEach-Object {
    $k, $v = $_ -split '=', 2; $envs[$k.Trim()] = $v.Trim()
}
$HttpPort = if ($envs.HTTP_PORT) { $envs.HTTP_PORT } else { '80' }
$Base = if ($HttpPort -eq '80') { 'http://localhost' } else { "http://localhost:$HttpPort" }
$PortInt = if ($envs.BACKEND_INTERNAL_PORT) { $envs.BACKEND_INTERNAL_PORT } else { '8000' }
$DocsEnabled = ($envs.DOCS_ENABLED -eq 'true')
$Project = if ($envs.COMPOSE_PROJECT_NAME) { $envs.COMPOSE_PROJECT_NAME } else { $envs.PROJECT_NAME }
$script:Rows = New-Object System.Collections.Generic.List[string]
$script:Pass = 0; $script:Fail = 0

function Add-Result([bool]$Ok, [string]$Name, [string]$Detail) {
    $Detail = ($Detail -replace '\|', '/' -replace "`r?`n", ' ')
    if ($Ok) { $script:Pass++; $icon = '✅'; $color = 'Green' } else { $script:Fail++; $icon = '❌'; $color = 'Red' }
    $script:Rows.Add("| $icon | $Name | $Detail |")
    Write-Host "$icon $Name — $Detail" -ForegroundColor $color
}
function Get-Code([string]$Url, [string[]]$Extra = @()) {
    $a = @('-s', '-o', 'NUL', '-w', '%{http_code}', '--max-time', '10') + $Extra
    (& curl.exe @a $Url) 2>$null
}
function Get-Body([string]$Url) { (& curl.exe -s --max-time 10 $Url) -join "`n" }
function Find-Asset([string]$Html, [string]$Attr, [string]$Ext) {
    $m = [regex]::Match($Html, "$Attr=`"?(/assets/[^`" >]+\.$Ext)")
    if ($m.Success) { $m.Groups[1].Value } else { '' }
}

Write-Host '=== 1. Контейнеры ==='
$composePs = (docker compose ps --format 'table {{.Name}}\t{{.Service}}\t{{.Status}}\t{{.Ports}}') -join "`n"
$dockerPs  = (docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}') -join "`n"
Write-Host $composePs
foreach ($svc in 'backend', 'postgres', 'nginx') {
    $cid = docker compose ps -q $svc
    if (-not $cid) { Add-Result $false "$svc запущен" 'контейнер не найден'; continue }
    $st = docker inspect -f '{{.State.Status}}{{if .State.Health}}/{{.State.Health.Status}}{{end}}' $cid
    Add-Result ($st -eq 'running/healthy' -or $st -eq 'running') "${svc}: running/healthy" $st
}
$restarting = (docker inspect -f '{{if .State.Restarting}}{{.Name}} {{end}}' (docker compose ps -aq)) -join '' -replace '/', ''
Add-Result ([string]::IsNullOrWhiteSpace($restarting)) 'Ни один контейнер не в Restarting' $(if ($restarting) { $restarting } else { 'ни одного' })

Write-Host '=== 2. backend видит БД ==='
$py = "from sqlalchemy import text`nfrom app.core.db import engine`nwith engine.connect() as c: print('db=' + c.execute(text('select current_database()')).scalar())"
$dbPing = (docker compose exec -T backend python -c $py 2>&1 | Select-Object -Last 1) -as [string]
Add-Result ($dbPing -like 'db=*') 'backend → postgres (SQLAlchemy из контейнера)' $dbPing
$health = Get-Body "$Base/api/health"
Add-Result ($health -match '"status":"ok"' -and $health -match '"db":"ok"') 'GET /api/health через nginx' $health

Write-Host '=== 3. Услуги ==='
$services = @()
try { $services = @(Invoke-RestMethod "$Base/api/admin-settings" -TimeoutSec 10) } catch {}
$names = ($services | ForEach-Object { "$($_.services) ($($_.budget_range))" }) -join ', '
Add-Result ($services.Count -ge 3) 'GET /api/admin-settings → ≥3 услуги' "$($services.Count) шт.: $names"
$c = Get-Code "$Base/api/admin-settings/"
Add-Result ($c -eq '200') 'GET /api/admin-settings/ (со слэшем) без 307' "HTTP $c"

Write-Host '=== 4. Статика ==='
$index = Get-Body "$Base/"
Add-Result ((Get-Code "$Base/") -eq '200') 'GET / (index.html)' 'HTTP 200'
$css = Find-Asset $index 'href' 'css'; $js = Find-Asset $index 'src' 'js'
$cssType = ''
try { $r = Invoke-WebRequest "$Base$css" -UseBasicParsing -TimeoutSec 10; $cssCode = [string]$r.StatusCode; $cssType = $r.Headers['Content-Type'] } catch { $cssCode = 'ошибка' }
Add-Result ($css -and $cssCode -eq '200' -and $cssType -match 'text/css') "CSS $css" "HTTP $cssCode, Content-Type: $cssType"
$c = Get-Code "$Base$js"; Add-Result ($js -and $c -eq '200') "JS $js" "HTTP $c"
$adminCss = Find-Asset (Get-Body "$Base/admin/") 'href' 'css'
$c = Get-Code "$Base$adminCss"; Add-Result ($adminCss -and $c -eq '200') '/admin подключает CSS по абсолютному пути' "$adminCss → HTTP $c"
$c = Get-Code "$Base/assets/nope.css"; Add-Result ($c -eq '404') 'Несуществующий CSS → 404, а не index.html' "HTTP $c"

Write-Host '=== 5. POST без 307/405 ==='
$svcId = if ($services.Count) { $services[0].id } else { 1 }
foreach ($path in '/api/applications', '/api/applications/') {
    $body = @{ application = @{ last_name = 'Проверкин'; first_name = 'PowerShell'; phone = '+7 900 000-00-00'; service_id = $svcId; role = 'сотрудник'; budget = '50000'; comment = 'check.ps1' }; metrics = @{ time_on_page_sec = 5; utm = @{ utm_source = 'check' } } } | ConvertTo-Json -Depth 5
    $tmp = New-TemporaryFile
    [System.IO.File]::WriteAllText($tmp, $body, (New-Object System.Text.UTF8Encoding $false))
    $c = Get-Code "$Base$path" @('-X', 'POST', '-H', 'Content-Type: application/json', '--data-binary', "@$tmp")
    Remove-Item $tmp
    Add-Result ($c -eq '201') "POST $path" "HTTP $c (ожидается 201, не 307/405)"
}

Write-Host '=== 6. Изоляция backend ==='
$bPorts = (docker port backend 2>$null) -join ' '
Add-Result ([string]::IsNullOrWhiteSpace($bPorts)) 'Контейнер backend не публикует порты' $(if ($bPorts) { $bPorts } else { 'docker port backend: пусто' })
$bNets = docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' backend
Add-Result (-not ($bNets -match '_public')) 'backend только в сети internal' "сети: $bNets"
$owner = (docker ps --format '{{.Names}} {{.Ports}}' | Where-Object { $_ -match "(0\.0\.0\.0|::|127\.0\.0\.1):$PortInt->" } | ForEach-Object { ($_ -split ' ')[0] }) -join ' '
$note = if ($owner -and $owner -notmatch '^backend$') { "localhost:$PortInt занят сторонним контейнером ($owner) — к стеку не относится" } else { "backend стека порт $PortInt не публикует" }
Add-Result ([string]::IsNullOrWhiteSpace($bPorts)) 'Backend стека недоступен с хоста напрямую' $note
$net = (docker run --rm --network "${Project}_public" alpine:3 sh -c "nc -z -w 3 backend $PortInt && echo OPEN || echo CLOSED" 2>$null) -join ''
Add-Result ($net -eq 'CLOSED') 'Из сети public backend недоступен' "nc backend:$PortInt → $net"

Write-Host '=== 7. Swagger ==='
$cd = Get-Code "$Base/docs"; $co = Get-Code "$Base/openapi.json"
if ($DocsEnabled) { Add-Result ($cd -eq '200' -and $co -eq '200') 'DOCS_ENABLED=true: /docs и /openapi.json' "HTTP $cd / $co" }
else { Add-Result ($cd -eq '404' -and $co -eq '404') 'DOCS_ENABLED=false: /docs закрыт' "HTTP $cd / $co (ожидается 404)" }

Write-Host '=== 8. Данные в БД ==='
$psql = @('compose', 'exec', '-T', 'postgres', 'psql', '-U', $envs.POSTGRES_USER, '-d', $envs.POSTGRES_DB)
$nApp = ((& docker @psql -tAc 'SELECT count(*) FROM applications') -join '').Trim()
$nMet = ((& docker @psql -tAc 'SELECT count(*) FROM behavior_metrics') -join '').Trim()
Add-Result ($nApp -match '^\d+$' -and [int]$nApp -gt 0) 'SELECT count(*) FROM applications' $nApp
Add-Result ($nApp -eq $nMet) 'applications = behavior_metrics (связь 1:1)' "$nApp = $nMet"
$last3 = (& docker @psql -c "SELECT a.id, a.last_name||' '||a.first_name AS fio, s.services AS service, a.budget, a.role, m.time_on_page_sec AS sec, m.utm->>'utm_source' AS utm FROM applications a LEFT JOIN admin_settings s ON s.id=a.service_id LEFT JOIN behavior_metrics m ON m.application_id=a.id ORDER BY a.id DESC LIMIT 3") -join "`n"
Write-Host $last3

Write-Host '=== 9. Логи backend ==='
$logs = (docker logs --tail 20 backend 2>&1) -join "`n"
Add-Result (-not ($logs -match 'Traceback')) 'Последние 20 строк docker logs backend без Traceback' 'Traceback не найден'

$total = $script:Pass + $script:Fail
$summary = if ($script:Fail -eq 0) { "✅ Все проверки пройдены: $($script:Pass) из $total" } else { "❌ Провалено проверок: $($script:Fail) из $total" }
New-Item -ItemType Directory -Force reports | Out-Null
$fence = '```'
@"
# Отчёт проверки стека Autello — часть 2 (PowerShell)

- Дата: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
- DOCS_ENABLED: $($envs.DOCS_ENABLED)

## Итог

**$summary**

## Проверки

| | Проверка | Результат |
|---|---|---|
$($script:Rows -join "`n")

## docker compose ps

$fence
$composePs
$fence

## docker ps

$fence
$dockerPs
$fence

## Последние 3 заявки (всего: $nApp)

$fence
$last3
$fence

## Адреса

- Сайт: $Base/
- Админка: $Base/admin
- Swagger: $Base/docs
- pgAdmin: http://localhost:$($envs.PGADMIN_PORT)
"@ | Set-Content -Encoding UTF8 reports\check_report.md

Write-Host ''
Write-Host $summary
Write-Host 'Отчёт: reports\check_report.md'
if ($script:Fail -ne 0) { exit 1 }
