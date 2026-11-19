param([string[]]$Cases = @('bounds','appendlocked','renameblocked','over64','keys9999','keys1000','keys10000','near60','over60','near64'), [string]$Epf='probe.epf', [string]$RunDirectory='.local/lifecycle-limits', [switch]$ProbeAllReads)
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$run=Join-Path $root $RunDirectory
$exe='C:/Program Files/1cv8/8.5.1.1529/bin/1cv8c.exe'
$python='C:/1C/tools/ai/mcp/1c-mcp-toolkit/.venv/Scripts/python.exe'
function Invoke-Limit([string]$Name,[string]$Action,[string]$Journal) {
    if (Test-Path -LiteralPath (Join-Path $run ($Name+'.json'))) { throw "Preserve prior report $Name" }
    @{name=$Name;action=$Action;journal=$Journal} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $run 'case.json') -Encoding utf8
    $proc=Start-Process -FilePath $exe -ArgumentList @('ENTERPRISE','/F',('"'+$run+'/db"'),'/N','ApiProbe','/TESTMANAGER','/Execute',('"'+$run+'/'+$Epf+'"'),'/DisableStartupDialogs') -WindowStyle Hidden -PassThru
    $proc.Id | Add-Content -LiteralPath (Join-Path $run 'owned-pids.txt')
    $deadline=(Get-Date).AddMinutes(15)
    $measured=$false
    try {
        while (-not $proc.WaitForExit(1000)) {
            if ((Get-Date) -gt $deadline) { throw "Timeout $Name" }
            $report=Join-Path $run ($Name+'.json')
            if ($Action -in @('benchmark','initializing') -and -not $measured -and (Test-Path -LiteralPath $report)) {
                try { $value=Get-Content -LiteralPath $report -Raw | ConvertFrom-Json } catch { continue }
                if ($value.ready) {
                    $measured=$true
                    $measureArgs=@($Name,$run)
                    if ($ProbeAllReads) { $measureArgs+='--all-reads' }
                    & $python -B (Join-Path $PSScriptRoot 'measure_limits_http.py') @measureArgs
                    if ($LASTEXITCODE -ne 0) { throw "HTTP measurement failed $Name" }
                }
            }
        }
        $v=Get-Content -LiteralPath (Join-Path $run ($Name+'.json')) -Raw | ConvertFrom-Json
        Write-Output "$Name startup_ms=$($v.startup_ms) count=$($v.count) bytes=$($v.bytes) error=$($v.error)"
    } finally {
        if (-not $proc.HasExited) { Stop-Process -Id $proc.Id }
    }
}
foreach ($case in $Cases) {
    $action=if ($case -in @('bounds','appendlocked','renameblocked','active','initializing')) { $case } elseif ($case -eq 'over64' -or $case -eq 'keys9999') { 'quota' } else { 'benchmark' }
    Invoke-Limit $case $action $case
    if ($case -in @('appendlocked','renameblocked')) { Invoke-Limit ($case+'-recovered') 'recover' $case }
}
