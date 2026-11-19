param([Parameter(Mandatory)][string]$RunDir, [switch]$WithoutManager, [switch]$WindowDiagnostics,
    [switch]$VisibleManager,
    [string]$PlatformVersion = '8.5.1.1529', [string]$DatabasePath = '', [int]$TimeoutSeconds = 120)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$run = (Resolve-Path -LiteralPath $RunDir).Path
if (-not $run.StartsWith((Join-Path $repo '.local') + '\')) { throw 'Only disposable .local runs are allowed' }
$db = Join-Path $repo '.local/test-client-preflight/20261112/controlled85'
if ($DatabasePath) {
    $db = (Resolve-Path -LiteralPath $DatabasePath).Path
    if (-not $db.StartsWith((Join-Path $repo '.local') + '\')) { throw 'Only disposable .local databases are allowed' }
}
$exe = 'C:\Program Files\1cv8\' + $PlatformVersion + '\bin\1cv8c.exe'
if (Get-NetTCPConnection -LocalPort 16538 -State Listen -ErrorAction SilentlyContinue) { throw 'Port is occupied before test' }
$reportName = if ($WithoutManager) { 'result-normal.json' } else { 'result.json' }
if (Test-Path (Join-Path $run $reportName)) { throw 'Use a fresh run directory' }
$mode = if ($WithoutManager) { '' } else { ' /TESTMANAGER' }
$arguments = 'ENTERPRISE /F "' + $db + '" /N ApiProbe' + $mode + ' /Execute "' +
    (Join-Path $run 'Toolkit-test.epf') + '" /DisableStartupDialogs /DisableStartupMessages /Out "' + (Join-Path $run 'manager.log') + '"'
if ($WithoutManager) { $arguments += ' /C normal' }
# Screenshot acceptance needs a visible frame. Opt in only when showing the test
# manager has been explicitly authorized; ordinary background tests stay hidden.
$managerWindowStyle = if ($VisibleManager) { 'Normal' } else { 'Hidden' }
$manager = Start-Process -FilePath $exe -ArgumentList $arguments -WindowStyle $managerWindowStyle -PassThru
try {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $windowsInspected = $false
    while (-not $manager.HasExited -and (Get-Date) -lt $deadline) {
        if ($WindowDiagnostics -and -not $windowsInspected -and (Test-Path (Join-Path $run 'capture-ready.json'))) {
            & (Join-Path $PSScriptRoot 'inspect_capture_windows.ps1') -ManagerId $manager.Id -OutputPath (Join-Path $run 'windows.json')
            $windowsInspected = $true
        }
        Start-Sleep -Milliseconds 500
    }
    if (-not $manager.HasExited) { throw 'Manager test timeout' }
    $report = Join-Path $run $reportName
    if (-not (Test-Path $report) -or (Get-Item $report).LastWriteTime -lt $manager.StartTime) { throw 'No fresh report' }
    $result = Get-Content $report -Raw -Encoding UTF8 | ConvertFrom-Json
    $result | Select-Object name,ok | Format-Table
    if (@($result | Where-Object { -not $_.ok }).Count) {
        $result | Where-Object { -not $_.ok } | ConvertTo-Json -Depth 10
        throw 'Runtime assertions failed'
    }
    if (-not $WithoutManager -and (Test-Path (Join-Path $run 'old-session.txt'))) {
        $manager = Start-Process -FilePath $exe -ArgumentList ($arguments + ' /C recover') -WindowStyle $managerWindowStyle -PassThru
        $deadline = (Get-Date).AddSeconds(90)
        while (-not $manager.HasExited -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500 }
        if (-not $manager.HasExited) { throw 'Recovery timeout' }
        $report = Join-Path $run 'result-recover.json'
        if (-not (Test-Path $report) -or (Get-Item $report).LastWriteTime -lt $manager.StartTime) { throw 'No fresh recovery report' }
        $result = Get-Content $report -Raw -Encoding UTF8 | ConvertFrom-Json
        $result | Select-Object name,ok | Format-Table
        if (@($result | Where-Object { -not $_.ok }).Count) {
            $result | Where-Object { -not $_.ok } | ConvertTo-Json -Depth 10
            throw 'Recovery assertions failed'
        }
    }
} finally {
    # The harness may clean up only its own launcher and a matching run receipt.
    if (-not $manager.HasExited) { $manager.Kill(); $manager.WaitForExit() }
    $receiptPath = Join-Path $run 'receipt.json'
    if (Test-Path $receiptPath) {
        $receipt = Get-Content $receiptPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($receipt.pid -gt 0) {
            $owned = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $receipt.pid)
            if ($owned -and $owned.CommandLine.Contains('toolkit-test-' + $receipt.token) -and
                $owned.CreationDate.ToString('yyyyMMddHHmmss.ffffff') -eq $receipt.created.Substring(0,21)) {
                $null = $owned | Invoke-CimMethod -MethodName Terminate
                Wait-Process -Id $receipt.pid -Timeout 10 -ErrorAction SilentlyContinue
            }
        }
    }
}
