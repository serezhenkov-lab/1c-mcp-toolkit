param([Parameter(Mandatory)][int]$ManagerId, [Parameter(Mandatory)][string]$OutputPath)
$ErrorActionPreference = 'Stop'
if (-not ('CaptureWindowProbe' -as [type])) {
    Add-Type @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public class CaptureWindowRow {
 public long hwnd, parent, owner; public uint pid; public bool visible, minimized;
 public int width,height; public string className;
}
public static class CaptureWindowProbe {
 delegate bool Callback(IntPtr h, IntPtr data);
 [DllImport("user32.dll")] static extern bool EnumWindows(Callback cb, IntPtr data);
 [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
 [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
 [DllImport("user32.dll")] static extern bool IsIconic(IntPtr h);
 [DllImport("user32.dll")] static extern IntPtr GetParent(IntPtr h);
 [DllImport("user32.dll")] static extern IntPtr GetWindow(IntPtr h, uint cmd);
 [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr h,StringBuilder s,int n);
 [StructLayout(LayoutKind.Sequential)] struct Rect {public int left,top,right,bottom;}
 [DllImport("user32.dll")] static extern bool GetClientRect(IntPtr h,out Rect r);
 public static CaptureWindowRow[] Read(uint[] ids) {
  var rows=new List<CaptureWindowRow>(); var wanted=new HashSet<uint>(ids);
  EnumWindows((h,data)=>{uint pid; GetWindowThreadProcessId(h,out pid); if(!wanted.Contains(pid))return true;
   Rect r;GetClientRect(h,out r);var s=new StringBuilder(256);GetClassName(h,s,256);
   rows.Add(new CaptureWindowRow{hwnd=h.ToInt64(),pid=pid,visible=IsWindowVisible(h),minimized=IsIconic(h),
    parent=GetParent(h).ToInt64(),owner=GetWindow(h,4).ToInt64(),width=r.right-r.left,height=r.bottom-r.top,className=s.ToString()});return true;
  },IntPtr.Zero); return rows.ToArray();
 }
}
'@
}
$processes = @(Get-CimInstance Win32_Process)
$ids = [System.Collections.Generic.HashSet[uint32]]::new()
$null = $ids.Add([uint32]$ManagerId)
do {
    $added = $false
    foreach ($item in $processes) {
        if ($ids.Contains([uint32]$item.ParentProcessId) -and $ids.Add([uint32]$item.ProcessId)) { $added = $true }
    }
} while ($added)
$selected = @($processes | Where-Object { $ids.Contains([uint32]$_.ProcessId) })
$modules = @()
foreach ($item in $selected) {
    try {
        $modules += @(Get-Process -Id $item.ProcessId -Module | Where-Object {
            $_.FileName -match 'Temp|ScreenCapture|AddIn'
        } | Select-Object @{n='pid';e={$item.ProcessId}},ModuleName,FileName)
    } catch { $modules += @{pid=$item.ProcessId;error='module_inventory_unavailable'} }
}
@{ manager_pid=$ManagerId; processes=@($selected | Select-Object ProcessId,ParentProcessId,Name);
   windows=@([CaptureWindowProbe]::Read([uint32[]]$ids)); modules=$modules } |
    ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $OutputPath -Encoding utf8
