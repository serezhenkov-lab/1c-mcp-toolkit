param([string[]]$Routes=@('http','file','embedded'),[switch]$ChecksOnly,
      [string]$RunRoot='.local/queue1-acceptance',[switch]$RequireInterrupted,[switch]$SkipContract)
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$standRoot=(Resolve-Path -LiteralPath (Join-Path $root $RunRoot)).Path
if (-not $standRoot.StartsWith($root+'\.local\')) { throw 'Only disposable stands allowed' }
$env:TOOLKIT_QUEUE1_ROOT=$standRoot
$python='C:/1C/tools/ai/mcp/1c-mcp-toolkit/.venv/Scripts/python.exe'
$exe='C:/Program Files/1cv8/8.5.1.1529/bin/1cv8c.exe'
foreach ($route in $Routes) {
    if ($route -notin @('http','file','embedded')) { throw 'Unknown route' }
    $run=Join-Path $standRoot $route
    $db=Join-Path $run 'db'
    $proxy=$null
    try {
        foreach ($name in @('ready.txt','control.json')) {
            $path=Join-Path $run $name
            if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path }
        }
        if ($route -ne 'embedded') {
            $proxy=Start-Process $python -ArgumentList @('-B',"$root/tests/test_client/serve_queue1_acceptance.py",$route) -WindowStyle Hidden -PassThru -RedirectStandardOutput "$run/proxy.out" -RedirectStandardError "$run/proxy.err"
        }
        $manager=Start-Process $exe -ArgumentList @('ENTERPRISE','/F',('"'+$db+'"'),'/N','ApiProbe','/TESTMANAGER','/Execute',('"'+$run+'/probe.epf"'),'/DisableStartupDialogs','/Out',('"'+$run+'/manager.log"')) -WindowStyle Hidden -PassThru
        if (-not $ChecksOnly) {
            $probeArgs=@($route)
            if ($RequireInterrupted) { $probeArgs+='--require-interrupted' }
            & $python -B "$root/tests/test_client/run_queue1_acceptance.py" @probeArgs
            if ($LASTEXITCODE -ne 0) { throw "Acceptance failed: $route" }
        } else { Start-Sleep -Seconds 8 }
        $env:TOOLKIT_STAND_DIR=$run
        $env:TOOLKIT_STAND_URL='http://127.0.0.1:'+(@{http=17665;file=17666;embedded=17667}[$route])
        if (-not $ChecksOnly -and -not $SkipContract) {
            & $python -B "$root/tests/test_client/run_embedded_contract.py"
            if ($LASTEXITCODE -ne 0) { throw "Contract failed: $route" }
        }
        & $python -B "$root/tests/test_client/run_queue1_retention.py" $route
        if ($LASTEXITCODE -ne 0) { throw "Retention failed: $route" }
    } finally {
        # Only managers whose command line names this exact disposable EPF/base.
        $owned=@(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq '1cv8c.exe' -and $_.CommandLine.Replace('/','\').Contains($db) -and $_.CommandLine.Replace('/','\').Contains($run+'\probe.epf') })
        foreach ($p in $owned) { $null=$p | Invoke-CimMethod -MethodName Terminate }
        $receiptPath=Join-Path $run 'receipt.json'
        if (Test-Path $receiptPath) {
            $receipt=Get-Content $receiptPath -Raw -Encoding UTF8 | ConvertFrom-Json
            $p=Get-CimInstance Win32_Process -Filter ('ProcessId='+$receipt.pid)
            if ($p -and $p.CommandLine.Contains('toolkit-test-'+$receipt.token) -and $p.CreationDate.ToString('yyyyMMddHHmmss.ffffff') -eq $receipt.created.Substring(0,21)) {
                $null=$p | Invoke-CimMethod -MethodName Terminate
            }
        }
        if ($proxy -and -not $proxy.HasExited) { Stop-Process -Id $proxy.Id }
        @{route=$route;ended=(Get-Date).ToString('o');manager_ids=@($owned.ProcessId)} | ConvertTo-Json | Set-Content "$run/cleanup.json" -Encoding utf8
    }
}
