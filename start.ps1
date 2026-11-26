<#
E3 setup, stap 0. Zet een kale Windows-pc klaar voor de setup-wizard, zonder Claude.

    Een regel in PowerShell:
    irm https://raw.githubusercontent.com/EqualsThree-Git/e3-setup/main/start.ps1 | iex

Installeert wat ontbreekt (Python, Git, Node, GitHub CLI, Claude Code, de Claude-app, Google Drive voor desktop),
laat de gebruiker aanmelden bij GitHub, zet de E3-marketplaces en -plugins klaar en opent de checklist.
Daarna gaat de gebruiker verder in de Claude-app met /setup:setup.

Herneembaar: wat al in orde is, wordt overgeslagen. Wachtwoorden en codes typt enkel de gebruiker zelf.

    -Droog   toont enkel wat het zou doen
    -Bron    lokale map van e3-setup in plaats van GitHub (test, sandbox)
    -Log     extra map waar het logboek en de stand naartoe gaan (sandbox)
#>
param([switch]$Droog, [string]$Bron = "", [string]$Log = "", [switch]$GeenChecklist)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Org = "EqualsThree-Git"
$Markten = [ordered]@{ "e3-setup" = "$Org/e3-setup"; "e3-shared" = "$Org/e3-finance-skills"; "e3-dossync" = "$Org/e3-dossync" }
$Plugins = @("setup@e3-setup", "tools@e3-shared", "deliverables@e3-shared", "dossync@e3-dossync")
$PriveRepos = @("$Org/e3-finance-skills", "$Org/e3-dossync")

$Map = Join-Path $env:USERPROFILE ".claude\e3-setup"
New-Item -ItemType Directory -Force -Path $Map | Out-Null
if ($Log) { New-Item -ItemType Directory -Force -Path $Log | Out-Null }
$LogBestand = Join-Path $Map "start.log"
$Stand = [ordered]@{}

function Schrijf([string]$tekst) {
    $r = "{0:HH:mm:ss} {1}" -f (Get-Date), $tekst
    Write-Host $r
    Add-Content -Path $LogBestand -Value $r -Encoding UTF8
    Spiegel-Log
}

function Spiegel-Log {
    # Add-Content op een gedeelde sandboxmap faalt na de eerste regel: kopieer het hele logboek.
    if ($Log) { try { Copy-Item -Path $LogBestand -Destination (Join-Path $Log "start.log") -Force -ErrorAction Stop } catch {} }
}

function Gebruiker([string]$tekst) {
    Write-Host ""
    Write-Host ">> JIJ: $tekst" -ForegroundColor Yellow
    Add-Content -Path $LogBestand -Value ("{0:HH:mm:ss} GEBRUIKER: {1}" -f (Get-Date), $tekst) -Encoding UTF8
    Spiegel-Log
}

function Noteer([string]$wat, [string]$uitslag, [string]$detail) {
    $Stand[$wat] = [ordered]@{ uitslag = $uitslag; detail = $detail }
    Schrijf ("[{0}] {1}: {2}" -f $uitslag, $wat, $detail)
    $json = $Stand | ConvertTo-Json -Depth 4
    Set-Content -Path (Join-Path $Map "start-stand.json") -Value $json -Encoding UTF8
    if ($Log) { Set-Content -Path (Join-Path $Log "start-stand.json") -Value $json -Encoding UTF8 }
}

function Ververs-Pad {
    $delen = @([Environment]::GetEnvironmentVariable("Path", "Machine"), [Environment]::GetEnvironmentVariable("Path", "User"),
               (Join-Path $env:USERPROFILE ".local\bin"), (Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps"))
    $env:Path = ($delen | Where-Object { $_ }) -join ";"
}

function Is-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    return (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# ---------- wat er moet staan ----------

function Python-Pad {
    foreach ($k in @((Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"), (Join-Path $env:ProgramFiles "Python312\python.exe"))) {
        if (Test-Path $k) { return $k }
    }
    $c = Get-Command python -ErrorAction SilentlyContinue | Where-Object { $_.Source -notlike "*WindowsApps*" } | Select-Object -First 1
    if ($c) { return $c.Source }
    return $null
}

function Test-Python {
    $p = Python-Pad
    if (-not $p) { return $false }
    $v = & $p -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
    return ($v -match '^3\.(1[0-9])$')
}
function Test-Cmd([string]$naam) { return [bool](Get-Command $naam -ErrorAction SilentlyContinue) }
function Test-ClaudeApp {
    if (Get-AppxPackage -Name "Claude" -ErrorAction SilentlyContinue) { return $true }
    return (Test-Path (Join-Path $env:LOCALAPPDATA "AnthropicClaude\claude.exe"))
}
function Test-Browser {
    foreach ($k in @("${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe", "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
                     "$env:ProgramFiles\Google\Chrome\Application\chrome.exe", "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe")) {
        if (Test-Path $k) { return $true }
    }
    return $false
}
function Test-VCRedist {
    $k = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" -ErrorAction SilentlyContinue
    return [bool]($k -and $k.Installed -eq 1)
}
function Test-WebView2 {
    # Google Drive voor desktop vraagt de WebView2-runtime; zonder Edge (bv. Windows Sandbox) ontbreekt ze
    foreach ($k in @("HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
                     "HKCU:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}")) {
        $v = (Get-ItemProperty $k -ErrorAction SilentlyContinue).pv
        if ($v -and $v -ne "0.0.0.0") { return $true }
    }
    return $false
}
function Test-Drive { return [bool](Get-ChildItem (Join-Path $env:ProgramFiles "Google\Drive File Stream\*\GoogleDriveFS.exe") -ErrorAction SilentlyContinue) }

$Programmas = @(
    @{ naam = "Browser (Chrome als er geen Edge is)"; id = "Google.Chrome"; test = { Test-Browser } },
    @{ naam = "Python 3.12"; id = "Python.Python.3.12"; test = { Test-Python } },
    @{ naam = "Visual C++-runtime (lokaal uitschrijven)"; id = "Microsoft.VCRedist.2015+.x64"; test = { Test-VCRedist } },
    @{ naam = "Git"; id = "Git.Git"; test = { Test-Cmd "git" } },
    @{ naam = "Node.js"; id = "OpenJS.NodeJS.LTS"; test = { Test-Cmd "node" } },
    @{ naam = "GitHub CLI"; id = "GitHub.cli"; test = { Test-Cmd "gh" } },
    @{ naam = "Claude Code"; id = "Anthropic.ClaudeCode"; test = { Test-Cmd "claude" } },
    @{ naam = "Claude-app"; id = "Anthropic.Claude"; test = { Test-ClaudeApp } },
    @{ naam = "WebView2-runtime (voor Google Drive)"; id = "Microsoft.EdgeWebView2Runtime"; test = { Test-WebView2 } },
    @{ naam = "Google Drive voor desktop"; id = "Google.GoogleDrive"; test = { Test-Drive } }
)

# ---------- 1. winget ----------

function Zorg-Winget {
    if (Test-Cmd "winget") { Noteer "winget" "ok" "aanwezig"; return $true }
    if ($Droog) { Noteer "winget" "zou" "winget installeren via Microsoft.WinGet.Client"; return $false }
    Schrijf "winget ontbreekt: installeren via de PowerShell Gallery (Microsoft.WinGet.Client)"
    try {
        Install-PackageProvider -Name NuGet -MinimumVersion 2.8.5.201 -Force -Scope CurrentUser | Out-Null
        Set-PSRepository -Name PSGallery -InstallationPolicy Trusted -ErrorAction SilentlyContinue
        Install-Module -Name Microsoft.WinGet.Client -Force -Scope CurrentUser -Repository PSGallery -AllowClobber | Out-Null
        Import-Module Microsoft.WinGet.Client -Force
        if (Is-Admin) { Repair-WinGetPackageManager -AllUsers -Latest -Force | Out-Null } else { Repair-WinGetPackageManager -Latest -Force | Out-Null }
    } catch { Schrijf ("winget installeren gaf een fout: " + $_.Exception.Message) }
    Ververs-Pad
    if (Test-Cmd "winget") { Noteer "winget" "ok" "geinstalleerd"; return $true }
    Noteer "winget" "fout" "winget kon niet geinstalleerd worden; installeer 'App Installer' uit de Microsoft Store en start opnieuw"
    return $false
}

# ---------- 2. programma's ----------

function Laatste([string]$tekst) {
    # de laatste zinvolle regels van winget, zonder voortgangsbalken
    $balk = "[" + [char]0x2588 + [char]0x2592 + "]"
    $r = @($tekst -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ -and $_ -notmatch $balk -and $_ -notmatch '^[-\|/ ]+$' })
    return (($r | Select-Object -Last 3) -join " | ")
}

function Installeer([hashtable]$p) {
    if (& $p.test) { Noteer $p.naam "ok" "al aanwezig"; return }
    if ($Droog) { Noteer $p.naam "zou" "winget install $($p.id)"; return }
    Schrijf "$($p.naam) installeren ($($p.id))"
    $basis = @("install", "-e", "--id", $p.id, "--source", "winget", "--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity", "--silent")
    & winget @basis --scope user 2>&1 | Tee-Object -Variable t | Out-Host
    $rc = $LASTEXITCODE; $uit = ($t | Out-String)
    Ververs-Pad
    if (-not (& $p.test)) {
        Schrijf ("$($p.naam) per gebruiker: winget {0}: {1}" -f $rc, (Laatste $uit))
        Schrijf "$($p.naam): probeer voor de hele pc (Windows kan om toestemming vragen: klik Ja)"
        for ($poging = 1; $poging -le 8; $poging++) {
            & winget @basis 2>&1 | Tee-Object -Variable t | Out-Host
            $rc = $LASTEXITCODE; $uit = ($t | Out-String)
            if ($uit -notmatch "1618|Another installation is already in progress") { break }
            Schrijf "$($p.naam): Windows installeert nog iets anders, opnieuw over 30 seconden ($poging/8)"
            Start-Sleep -Seconds 30
        }
        Ververs-Pad
        if (-not (& $p.test)) { Schrijf ("$($p.naam) voor de hele pc: winget {0}: {1}" -f $rc, (Laatste $uit)) }
    }
    if ($p.id -eq "Anthropic.ClaudeCode" -and -not (& $p.test)) {
        Schrijf "Claude Code via het installatiescript van Anthropic"
        # in een apart proces: het installatiescript eindigt met exit en zou dit script mee afsluiten
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "irm https://claude.ai/install.ps1 | iex"
        Ververs-Pad
    }
    if (& $p.test) { Noteer $p.naam "ok" "geinstalleerd" } else { Noteer $p.naam "fout" "installeren mislukt (zie start.log)" }
}

# ---------- 3. GitHub ----------

function Heeft-Toegang {
    foreach ($r in $PriveRepos) {
        & gh api "repos/$r" --silent 2>$null
        if ($LASTEXITCODE -ne 0) { return $r }
    }
    return $null
}

function Zorg-GitHub {
    if (-not (Test-Cmd "gh")) { Noteer "GitHub" "fout" "GitHub CLI ontbreekt"; return $false }
    & gh auth status --hostname github.com 2>$null | Out-Null
    $aangemeld = ($LASTEXITCODE -eq 0)
    if (-not $aangemeld) {
        if ($Droog) { Noteer "GitHub" "zou" "gh auth login --web (de gebruiker meldt aan)"; return $false }
        Gebruiker "Meld je aan bij GitHub met je eigen account. Hieronder verschijnt een code van 8 tekens: druk op Enter, de browser opent, plak de code en klik Authorize. Opent er geen browser: open Edge, ga naar https://github.com/login/device en typ de code daar."
        & gh auth login --hostname github.com --git-protocol https --web
        & gh auth status --hostname github.com 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) { Noteer "GitHub" "gebruiker" "niet aangemeld bij GitHub: start dit script opnieuw"; return $false }
    }
    & gh auth setup-git --hostname github.com 2>$null | Out-Null
    $wie = (& gh api user --jq .login 2>$null)
    for ($i = 0; $i -lt 3; $i++) {
        $mist = Heeft-Toegang
        if (-not $mist) { Noteer "GitHub" "ok" "aangemeld als $wie, toegang tot de E3-repo's"; return $true }
        if ($Droog -or $i -eq 2) { break }
        Gebruiker "Je GitHub-account $wie heeft nog geen toegang tot $mist. Vraag de beheerder van $Org om een uitnodiging, aanvaard ze in de mail van GitHub en druk dan op Enter."
        [void](Read-Host "Enter om opnieuw te proberen")
    }
    Noteer "GitHub" "gebruiker" "aangemeld als $wie, maar geen toegang tot $mist (uitnodiging van de beheerder nodig)"
    return $false
}

# ---------- 4. marketplaces en plugins ----------

function Zorg-Plugins([bool]$github) {
    if (-not (Test-Cmd "claude")) { Noteer "plugins" "fout" "Claude Code ontbreekt"; return }
    $lijst = (& claude plugin marketplace list 2>$null) -join "`n"
    foreach ($naam in $Markten.Keys) {
        $src = $Markten[$naam]
        if ($naam -eq "e3-setup" -and $Bron) { $src = $Bron }
        if ($naam -ne "e3-setup" -and -not $github) { Noteer "marketplace $naam" "wacht" "eerst toegang tot GitHub"; continue }
        if ($lijst -match [regex]::Escape($naam)) {
            if (-not $Droog) { & claude plugin marketplace update $naam 2>&1 | Out-Null }
            Noteer "marketplace $naam" "ok" "al toegevoegd"
            continue
        }
        if ($Droog) { Noteer "marketplace $naam" "zou" "claude plugin marketplace add $src"; continue }
        $uit = (& claude plugin marketplace add $src 2>&1) -join " "
        if ($LASTEXITCODE -eq 0) { Noteer "marketplace $naam" "ok" "toegevoegd ($src)" } else { Noteer "marketplace $naam" "fout" $uit.Substring(0, [Math]::Min(200, $uit.Length)) }
    }
    $inst = Join-Path $env:USERPROFILE ".claude\plugins\installed_plugins.json"
    foreach ($p in $Plugins) {
        $al = (Test-Path $inst) -and ((Get-Content $inst -Raw) -match [regex]::Escape('"' + $p + '"'))
        if ($al) {
            if (-not $Droog) { & claude plugin update $p 2>&1 | Out-Null }
            Noteer "plugin $p" "ok" "al geinstalleerd"; continue
        }
        if ($p -ne "setup@e3-setup" -and -not $github) { Noteer "plugin $p" "wacht" "eerst toegang tot GitHub"; continue }
        if ($Droog) { Noteer "plugin $p" "zou" "claude plugin install $p"; continue }
        $uit = (& claude plugin install $p 2>&1) -join " "
        if ($LASTEXITCODE -eq 0) { Noteer "plugin $p" "ok" "geinstalleerd" } else { Noteer "plugin $p" "fout" $uit.Substring(0, [Math]::Min(200, $uit.Length)) }
    }
}

# ---------- 5. checklist ----------

function Wizard-Pad {
    if ($Bron) {
        $k = Join-Path $Bron "setup\skills\setup\scripts\wizard.py"
        if (Test-Path $k) { return $k }
    }
    $k = Get-ChildItem -Path (Join-Path $env:USERPROFILE ".claude\plugins\cache\*\setup\*\skills\setup\scripts\wizard.py") -ErrorAction SilentlyContinue |
         Sort-Object FullName | Select-Object -Last 1
    if ($k) { return $k.FullName }
    return $null
}

# ---------- uitvoeren ----------

Ververs-Pad
Schrijf ("E3 setup, stap 0 " + ($(if ($Droog) { "(droge run)" } else { "" })) + " op $env:COMPUTERNAME als $env:USERNAME")
$wg = Zorg-Winget
foreach ($p in $Programmas) {
    if ($wg -or (& $p.test)) { Installeer $p } else { Noteer $p.naam "fout" "geen winget" }
}
Ververs-Pad
if (-not $Droog -and (Test-Drive) -and -not (Get-Process -Name GoogleDriveFS -ErrorAction SilentlyContinue)) {
    $exe = Get-ChildItem (Join-Path $env:ProgramFiles "Google\Drive File Stream\*\GoogleDriveFS.exe") -ErrorAction SilentlyContinue | Select-Object -Last 1
    if ($exe) { Start-Process $exe.FullName }
    Gebruiker "Google Drive opent: meld je aan met je werkadres (@equalsthree.be). Het synchroniseren loopt verder op de achtergrond."
}
$gh = Zorg-GitHub
Zorg-Plugins $gh

$wiz = Wizard-Pad
$py = Python-Pad
if ($GeenChecklist) {
    Noteer "checklist" "overgeslagen" "-GeenChecklist"
} elseif (-not $wiz -or -not $py) {
    Noteer "checklist" "fout" "wizard of Python niet gevonden"
} elseif ($Droog) {
    Noteer "checklist" "zou" "$py $wiz checklist"
} else {
    Gebruiker "De checklist opent in de browser: vul in wie je bent en wat je gebruikt, en klik Bewaren."
    # stderr niet opvangen: daar staat het adres van de checklist, de gebruiker moet het zien
    $uit = ((& $py $wiz checklist) | Out-String)
    if ($uit -match '"ok": true') { Noteer "checklist" "ok" "bewaard" } else { Noteer "checklist" "fout" $uit.Substring(0, [Math]::Min(200, $uit.Length)) }
}

$fout = @($Stand.Keys | Where-Object { $Stand[$_].uitslag -in @("fout", "gebruiker", "wacht") })
Write-Host ""
if ($fout.Count -eq 0 -and -not $Droog) {
    Schrijf "Stap 0 klaar."
    Gebruiker "Open de Claude-app (Start > Claude), meld je aan met je werkadres (Team-plan van Equals Three), kies het tabblad Code en typ: /setup:setup"
    try { Start-Process "shell:AppsFolder\Claude_pzs8sxrjxfjjc!Claude" -ErrorAction Stop } catch {}
} elseif (-not $Droog) {
    Schrijf ("Nog niet in orde: " + ($fout -join ", ") + ". Los op wat hierboven bij JIJ staat en start dit script opnieuw; het slaat over wat klopt.")
}
