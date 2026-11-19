param([string[]]$Cases = @('normal','prepared','committed','old_removed','installed','legacy','quota','growth'), [switch]$Negative, [string]$RunDirectory='.local/lifecycle-compaction')
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$run = Join-Path $root $RunDirectory
$exe = 'C:/Program Files/1cv8/8.5.1.1529/bin/1cv8c.exe'
function Invoke-Probe([string]$Action, [string]$Journal, [string]$Report) {
    @{action=$Action; journal=$Journal; report=$Report} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $run 'case.json') -Encoding utf8
    $proc = Start-Process -FilePath $exe -ArgumentList @('ENTERPRISE','/F',('"'+$run+'/db"'),'/N','ApiProbe','/TESTMANAGER','/Execute',('"'+$run+'/probe.epf"'),'/DisableStartupDialogs') -WindowStyle Hidden -PassThru
    $proc.Id | Add-Content -LiteralPath (Join-Path $run 'owned-pids.txt')
    if ((-not $proc.WaitForExit(60000)) -and (-not $proc.WaitForExit(60000))) {
        Stop-Process -Id $proc.Id
        throw "Probe timed out: $Report"
    }
    $result = Get-Content -LiteralPath (Join-Path $run ($Report+'.json')) -Raw | ConvertFrom-Json
    Write-Output "$Report checks=$($result.checks.Count) error=$($result.error)"
}
if ($Negative) {
    foreach ($case in @('badmarker','badnext','orphan')) {
        $journal = 'journal-'+$case
        $target = Join-Path $run $journal
        if (Test-Path -LiteralPath $target) { throw "Preserve existing case: $case" }
        New-Item -ItemType Directory -Path $target | Out-Null
        $source = Join-Path $run $(if ($case -eq 'orphan') { 'stage-prepared' } else { 'stage-committed' })
        Get-ChildItem -LiteralPath $source -Filter 'operations.jsonl*' | Copy-Item -Destination $target
        if ($case -eq 'badmarker') {
            '{"count":' | Set-Content -LiteralPath (Join-Path $target 'operations.jsonl.commit') -Encoding utf8
        } else {
            '{"payload":' | Add-Content -LiteralPath (Join-Path $target 'operations.jsonl.next') -Encoding utf8
        }
        Invoke-Probe 'recover' $journal $case
    }
}
foreach ($case in $Cases) {
    if ($case -notmatch '^[a-z_]+$') { throw 'Invalid case name' }
    $journal = 'journal-'+$case
    if (Test-Path -LiteralPath (Join-Path $run $journal)) { throw "Preserve existing case: $case" }
    Invoke-Probe $case $journal $case
    $evidence = Join-Path $run ('stage-'+$case)
    New-Item -ItemType Directory -Path $evidence | Out-Null
    Get-ChildItem -LiteralPath (Join-Path $run $journal) -Filter 'operations.jsonl*' | Copy-Item -Destination $evidence
    if ($case -notin @('quota','growth')) { Invoke-Probe 'recover' $journal ($case+'-recovered') }
}
