param([string]$Name='',[string]$Type='Edit',[ValidateSet('read','click')][string]$Action='read')
$ErrorActionPreference='Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$run=Join-Path $root '.local/profile-runtime'
$pidValue=[int](Get-Content (Join-Path $run 'manager-pid.txt'))
$window=[System.Windows.Automation.AutomationElement]::RootElement.FindFirst([System.Windows.Automation.TreeScope]::Children,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,$pidValue)))
if (-not $window) { throw 'No stand window' }
Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public class ProfileWindow { [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h); }'
if ($Action -ne 'read') {
    if (-not [ProfileWindow]::SetForegroundWindow([IntPtr]$window.Current.NativeWindowHandle)) { throw 'Cannot activate stand window' }
    Start-Sleep -Milliseconds 300
}
$items=$window.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
if ($Name) {
    $targets=@($items | Where-Object { $_.Current.Name -eq $Name -and $_.Current.ControlType.ProgrammaticName -eq ('ControlType.'+$Type) })
    if ($targets.Count -ne 1) { throw "Ambiguous/missing UI control: $Name" }
    $target=$targets[0]
    switch ($Action) {
        'click' {
            Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public class ProfileMouse { [DllImport("user32.dll")] public static extern bool SetCursorPos(int x,int y); [DllImport("user32.dll")] public static extern void mouse_event(uint f,uint x,uint y,uint d,UIntPtr e); }'
            $point=$target.GetClickablePoint()
            if ([System.Windows.Automation.AutomationElement]::FromPoint($point).Current.ProcessId -ne $pidValue) { throw 'Stand control is obscured by another process' }
            [ProfileMouse]::SetCursorPos([int]$point.X,[int]$point.Y) | Out-Null
            [ProfileMouse]::mouse_event(2,0,0,0,[UIntPtr]::Zero)
            [ProfileMouse]::mouse_event(4,0,0,0,[UIntPtr]::Zero)
        }
    }
}
$snapshot=@($items | Where-Object { $_.Current.Name -and $_.Current.ControlType.ProgrammaticName -in @('ControlType.Edit','ControlType.CheckBox','ControlType.RadioButton','ControlType.Button') } | ForEach-Object {
    $entry=[ordered]@{name=$_.Current.Name;type=$_.Current.ControlType.ProgrammaticName;enabled=$_.Current.IsEnabled}
    if ($_.Current.ControlType.ProgrammaticName -eq 'ControlType.CheckBox') {
        try { $entry.checked=$_.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern).Current.ToggleState.ToString() } catch {}
    }
    if ($_.Current.ControlType.ProgrammaticName -eq 'ControlType.Edit' -and -not $_.Current.IsPassword -and $_.Current.Name -notmatch 'ключ') {
        try { $entry.value=$_.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value } catch {}
    }
    [PSCustomObject]$entry
})
$snapshot | ConvertTo-Json -Depth 4
