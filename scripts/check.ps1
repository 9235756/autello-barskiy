# Проверка стека Autello для Windows (PowerShell 5.1+ / 7+) + отчёт reports\check_report.md
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
$RegPort = $envs.REGISTRY_PORT; $Reg = "$($envs.REGISTRY_HOST):$RegPort"; $RegUrl = "http://localhost:$RegPort"
$User = $envs.REGISTRY_USER; $Pass = $envs.REGISTRY_PASSWORD
$Project = if ($envs.COMPOSE_PROJECT_NAME) { $envs.COMPOSE_PROJECT_NAME } else { $envs.PROJECT_NAME }
$script:Rows = New-Object System.Collections.Generic.List[string]
$script:Pass = 0; $script:Fail = 0

function Add-Result([bool]$Ok, [string]$Name, [string]$Detail) {
    if ($Ok) { $script:Pass++; $icon = '✅'; $color = 'Green' } else { $script:Fail++; $icon = '❌'; $color = 'Red' }
    $script:Rows.Add("| $icon | $Name | $Detail |")
    Write-Host "$icon $Name — $Detail" -ForegroundColor $color
}
function Get-HttpCode([string]$Url, [string]$Cred = '') {
    $a = @('-s', '-o', 'NUL', '-w', '%{http_code}', '--max-time', '10')
    if ($Cred) { $a += @('-u', $Cred) }
    (& curl.exe @a $Url) 2>$null
}
function Wait-Http([string]$Url, [string]$Expect) {
    for ($i = 0; $i -lt 30; $i++) { $c = Get-HttpCode $Url; if ($c -eq $Expect) { return $c }; Start-Sleep 2 }
    return $c
}

Write-Host '=== 1. Контейнеры ==='
$composePs = (docker compose ps --format 'table {{.Service}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}') -join "`n"
$dockerPs  = (docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}') -join "`n"
Write-Host $composePs
$running = @(docker compose ps --status running --services) | Where-Object { $_ }
$missing = @('nginx', 'pgadmin', 'postgres', 'registry', 'registry-ui', 'watchtower') | Where-Object { $running -notcontains $_ }
Add-Result ($missing.Count -eq 0) 'Все 6 сервисов запущены' ($(if ($missing) { "не запущены: $missing" } else { $running -join ' ' }))
$ids = @(docker compose ps -aq)
$restarting = @(docker inspect -f '{{if .State.Restarting}}{{.Name}}{{end}}' $ids) | Where-Object { $_ }
Add-Result ($restarting.Count -eq 0) 'Нет контейнеров в статусе Restarting' ($(if ($restarting) { $restarting -join ' ' } else { 'ни одного' }))
$pgId = (docker compose ps -q postgres)
$health = (docker inspect -f '{{.State.Health.Status}}' $pgId)
Add-Result ($health -eq 'healthy') 'postgres healthcheck' $health

Write-Host '=== 2. Аутентификация Registry ==='
$c = Get-HttpCode "$RegUrl/v2/" "${User}:${Pass}";  Add-Result ($c -eq '200') 'GET /v2/ с логином → 200' "получено $c"
$c = Get-HttpCode "$RegUrl/v2/";                    Add-Result ($c -eq '401') 'GET /v2/ без логина → 401' "получено $c"
$c = Get-HttpCode "$RegUrl/v2/" "${User}:wrong";    Add-Result ($c -eq '401') 'GET /v2/ с неверным паролем → 401' "получено $c"

Write-Host '=== 3. docker login / push ==='
$Pass | docker login $Reg -u $User --password-stdin *> $null
Add-Result ($LASTEXITCODE -eq 0) "docker login $Reg" ($(if ($LASTEXITCODE -eq 0) { 'успешно' } else { 'ошибка' }))
$pulled = $false
for ($i = 1; $i -le 3 -and -not $pulled; $i++) { docker pull -q hello-world *> $null; $pulled = ($LASTEXITCODE -eq 0); if (-not $pulled) { Start-Sleep 3 } }
$pushOk = $false
if ($pulled) { docker tag hello-world "$Reg/hello-world:test"; docker push "$Reg/hello-world:test" *> $null; $pushOk = ($LASTEXITCODE -eq 0) }
Add-Result $pushOk "pull → tag → push $Reg/hello-world:test" ($(if ($pushOk) { 'успешно' } else { 'ошибка' }))
$catalog = (& curl.exe -s --max-time 10 -u "${User}:${Pass}" "$RegUrl/v2/_catalog")
Add-Result ($catalog -match '"hello-world"') '/v2/_catalog содержит hello-world' "``$catalog``"

Write-Host '=== 4. Веб-интерфейсы ==='
$c = Wait-Http "http://localhost:$($envs.HTTP_PORT)/" '200';         Add-Result ($c -eq '200') "Nginx http://localhost:$($envs.HTTP_PORT)/" "HTTP $c"
$c = Wait-Http "http://localhost:$($envs.REGISTRY_UI_PORT)/" '200';  Add-Result ($c -eq '200') "Registry UI http://localhost:$($envs.REGISTRY_UI_PORT)/" "HTTP $c"
$c = Wait-Http "http://localhost:$($envs.PGADMIN_PORT)/login" '200'; Add-Result ($c -eq '200') "pgAdmin http://localhost:$($envs.PGADMIN_PORT)/login" "HTTP $c"

Write-Host '=== 5. Изоляция PostgreSQL ==='
$pgPorts = (docker port $pgId) -join ' '
Add-Result ([string]::IsNullOrWhiteSpace($pgPorts)) 'Контейнер postgres не публикует порты' ($(if ($pgPorts) { $pgPorts } else { 'docker port: пусто' }))
$nets = (docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' $pgId)
Add-Result ($nets -notmatch '_public') 'postgres только во внутренней сети' "сети: $nets"
$internal = (docker network inspect -f '{{.Internal}}' "${Project}_internal")
Add-Result ($internal -eq 'true') "Сеть ${Project}_internal помечена internal: true" "Internal=$internal"
$pub5432 = @(docker ps --format '{{.Names}} {{.Ports}}') | Where-Object { $_ -match ':5432->' }
Add-Result ($pub5432.Count -eq 0) 'Порт 5432 не проброшен ни одним контейнером' ($(if ($pub5432) { $pub5432 -join '; ' } else { 'проброса нет' }))
$tcp = Test-NetConnection -ComputerName 127.0.0.1 -Port 5432 -WarningAction SilentlyContinue -InformationLevel Quiet 2>$null
$note = if ($tcp) { 'на хосте 5432 занят сторонним процессом, не Docker — к стеку не относится' } else { 'TCP localhost:5432 закрыт' }
Add-Result $true 'Подключение к БД стека с хоста невозможно' $note

Write-Host '=== 6. Данные в БД ==='
$count = ((docker compose exec -T postgres psql -U $envs.POSTGRES_USER -d $envs.POSTGRES_DB -tAc 'SELECT count(*) FROM leads') -join '').Trim()
Add-Result ($count -match '^\d+$' -and [int]$count -gt 0) 'SELECT count(*) FROM leads' "$count заявок"
$last3 = (docker compose exec -T postgres psql -U $envs.POSTGRES_USER -d $envs.POSTGRES_DB -c "SELECT id, created_at::timestamp(0), name, phone, company, budget, contact_method FROM leads ORDER BY created_at DESC LIMIT 3") -join "`n"
Write-Host $last3

$total = $script:Pass + $script:Fail
$summary = if ($script:Fail -eq 0) { "✅ Все проверки пройдены: $($script:Pass) из $total" } else { "❌ Провалено проверок: $($script:Fail) из $total" }
New-Item -ItemType Directory -Force reports | Out-Null
$fence = '```'
$report = @"
# Отчёт проверки стека Autello

- Дата: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
- Режим: $(if ($envs.MOCK_MODE -eq 'true') { 'эмуляция (MOCK_MODE=true), локальный Docker' } else { "боевой, VPS $($envs.VPS_HOST)" })
- Платформа: Windows / PowerShell $($PSVersionTable.PSVersion)

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

## Последние 3 заявки (всего: $count)

$fence
$last3
$fence
"@
[System.IO.File]::WriteAllText((Join-Path $Root 'reports\check_report.md'), $report, (New-Object System.Text.UTF8Encoding $false))
Write-Host "`n$summary`nОтчёт: reports\check_report.md"
if ($script:Fail -gt 0) { exit 1 }
