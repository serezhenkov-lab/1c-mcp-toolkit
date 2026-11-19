param([string[]]$Routes=@('embedded','http','file'))
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$stand=Join-Path $root '.local/lost-response'
$python='C:/1C/tools/ai/mcp/1c-mcp-toolkit/.venv/Scripts/python.exe'
$exe='C:/Program Files/1cv8/8.5.1.1529/bin/1cv8c.exe'
foreach($route in $Routes) {
    if($route -notin @('embedded','http','file')) {throw 'Unknown route'}
    $run=Join-Path $stand $route
    if(Test-Path (Join-Path $run 'results.json')) {throw 'Preserve previous evidence before rerun'}
    $db=Join-Path $run 'db'
    $port=@{http=17669;file=17670;embedded=17671}[$route]
    foreach($checkPort in @($port,16549,17672)) {
        if(Get-NetTCPConnection -LocalPort $checkPort -State Listen -ErrorAction SilentlyContinue) {throw "Port in use: $checkPort"}
    }
    $owned=@()
    try {
        if($route -ne 'embedded') {
            $proxy=Start-Process $python -ArgumentList @('-B',"$root/tests/test_client/serve_lost_response.py",$route) -WindowStyle Hidden -PassThru -RedirectStandardOutput "$run/proxy.out" -RedirectStandardError "$run/proxy.err"
            $owned+=$proxy
        }
        $client=Start-Process $exe -ArgumentList @('ENTERPRISE','/IBConnectionString',('"File=""'+$db+'"";"'),'/TESTCLIENT','-TPort16549','/N','ApiProbe','/Execute',('"'+$stand+'/Fixture.epf"'),'/C',('toolkit-loss-'+$route),'/DisableStartupDialogs','/DisableStartupMessages','/Out',('"'+$run+'/client.log"')) -WindowStyle Hidden -PassThru
        $owned+=$client
        $readyDeadline=(Get-Date).AddSeconds(60)
        while(-not (Get-NetTCPConnection -LocalPort 16549 -State Listen -ErrorAction SilentlyContinue)) {
            if($client.HasExited -or (Get-Date) -gt $readyDeadline) {throw 'TESTCLIENT port not ready'}
            Start-Sleep -Milliseconds 500
        }
        if($route -eq 'embedded') {$startup='startup;mode=embedded;port=17671;url=127.0.0.1;auth=password;pwd=;danger_confirm=false'}
        else {
            $url=if($route -eq 'http'){"http://127.0.0.1:$port"}else{'file://'+($run.Replace('\','/'))+'/bridge/queue1'}
            $startup="startup;mode=proxy;url=$url;channel=queue1;auth=password;pwd=;danger_confirm=false"
        }
        $manager=Start-Process $exe -ArgumentList @('ENTERPRISE','/F',('"'+$db+'"'),'/N','ApiProbe','/TESTMANAGER','/Execute',('"'+$stand+'/Toolkit.epf"'),'/C',('"'+$startup+'"'),'/DisableStartupDialogs','/Out',('"'+$run+'/manager.log"')) -WindowStyle Hidden -PassThru
        $owned+=$manager
        $owned | Select-Object Id,StartTime,Path | ConvertTo-Json | Set-Content "$run/processes.json"
        & $python -B "$root/tests/test_client/run_lost_response.py" $route *> "$run/probe.log"
        if($LASTEXITCODE -ne 0){Get-Content "$run/probe.log" -Tail 20; throw "Failed: $route"}
        Get-Content "$run/probe.log" -Tail 1
    } finally {
        foreach($p in $owned) {
            if(-not $p.HasExited) {
                $now=Get-Process -Id $p.Id -ErrorAction SilentlyContinue
                if($now -and $now.StartTime -eq $p.StartTime) {Stop-Process -Id $p.Id}
            }
        }
        $left=@(Get-CimInstance Win32_Process | Where-Object {$_.Name -eq '1cv8c.exe' -and $_.CommandLine -and $_.CommandLine.Replace('/','\').Contains($db)})
        @{route=$route;remaining=$left.Count;ended=(Get-Date).ToString('o')} | ConvertTo-Json | Set-Content "$run/cleanup.json"
        if($left.Count){throw 'Test processes remain'}
    }
}
