<#
Start een Windows Sandbox (kale Windows, fabrieksinstellingen) met deze repo als C:\e3-setup (alleen lezen) en een
logmap als C:\e3-log. In de sandbox opent PowerShell met start.ps1; staat, rapport en logboek komen in sandbox\log\<tijd>.
Vereist de optionele Windows-functie "Windows Sandbox" (Windows 11 Pro).
#>
param([switch]$Droog)
$repo = Split-Path -Parent $PSScriptRoot
$log = Join-Path $PSScriptRoot ("log\" + (Get-Date -Format "yyMMdd HHmm"))
New-Item -ItemType Directory -Force -Path $log | Out-Null
$wsb = Join-Path $PSScriptRoot "e3-setup.wsb"
@"
<Configuration>
  <Networking>Enable</Networking>
  <vGPU>Enable</vGPU>
  <ClipboardRedirection>Enable</ClipboardRedirection>
  <MemoryInMB>8192</MemoryInMB>
  <MappedFolders>
    <MappedFolder><HostFolder>$repo</HostFolder><SandboxFolder>C:\e3-setup</SandboxFolder><ReadOnly>true</ReadOnly></MappedFolder>
    <MappedFolder><HostFolder>$log</HostFolder><SandboxFolder>C:\e3-log</SandboxFolder><ReadOnly>false</ReadOnly></MappedFolder>
  </MappedFolders>
  <LogonCommand><Command>powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\e3-setup\sandbox\in-sandbox.ps1</Command></LogonCommand>
</Configuration>
"@ | Set-Content -Path $wsb -Encoding UTF8
Write-Host "Config: $wsb"
Write-Host "Logmap: $log"
if (-not $Droog) {
    $exe = Join-Path $env:windir "System32\WindowsSandbox.exe"
    if (-not (Test-Path $exe)) { Write-Host "Windows Sandbox staat niet aan: Enable-WindowsOptionalFeature -Online -FeatureName Containers-DisposableClientVM -All (als administrator, daarna herstarten)"; exit 1 }
    Start-Process $wsb
}
