# Draait in de sandbox bij het aanmelden: opent een zichtbaar PowerShell-venster met start.ps1 van de gemapte repo.
[Environment]::SetEnvironmentVariable("E3_SETUP_SPIEGEL", "C:\e3-log", "User")
$env:E3_SETUP_SPIEGEL = "C:\e3-log"
"{0:HH:mm:ss} sandbox aangemeld als {1}" -f (Get-Date), $env:USERNAME | Add-Content C:\e3-log\sandbox.log
Start-Process powershell.exe -ArgumentList @("-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "C:\e3-setup\start.ps1",
    "-Bron", "C:\e3-setup", "-Log", "C:\e3-log")
