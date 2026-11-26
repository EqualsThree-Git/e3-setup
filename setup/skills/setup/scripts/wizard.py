"""Setup-wizard voor een nieuwe collega op het AI-framework Finance van Equals Three.

Het script ziet de laptop; Claude ziet de connectors en de taken op claude.ai en noteert die hier.
Wat het moet aansluiten staat in ../flows.json, niet in dit script.

    python wizard.py checklist                                   eerste scherm: wie ben je en wat gebruik je (lokale pagina)
    python wizard.py controleer [--ini JDS] [--andere-pc]        stand per stap, JSON, schrijft niets
    python wizard.py doe STAP --ini JDS [--droog]                de automatische actie van een pc-stap
    python wizard.py noteer SLEUTEL JSON --ini JDS [--droog]     wat Claude vaststelde (connector, taak, antwoord, test)
    python wizard.py wacht TEKST --ini JDS [--minuten 10]        wacht tot een testbestand in de inbox staat
    python wizard.py opruimen --ini JDS [--droog]                testbestanden van INI naar _verwerkt/setup-test
    python wizard.py rapport --ini JDS [--droog] [--andere-pc] [--uit PAD]
                                                                rapport per flow, md en html

--droog  schrijft niets: niet op de laptop, niet op de drive, geen staat. Elke actie zegt enkel wat ze zou doen.
--andere-pc  de laptopcontroles gelden voor iemand anders: ze worden niet hier uitgevoerd maar als
             "na te kijken op de laptop van INI" getoond (droge run voor een collega vanaf een andere pc).

Herneembaar: controleer kijkt elke keer opnieuw na, doe slaat een stap over die al klopt, en wat Claude
noteerde blijft in ~/.claude/e3-setup/staat.json staan. Enkel standaardbibliotheek, Python 3.10+.
"""
import argparse
import datetime as dt
import glob
import html
import json
import os
import pathlib
import platform
import re
import shutil
import string
import subprocess
import sys
import time
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = pathlib.Path(__file__).resolve().parent
MANIFEST = HERE.parent / "flows.json"
HOME = pathlib.Path(os.environ.get("E3_HOME") or pathlib.Path.home())   # E3_HOME enkel voor tests
STAAT_DIR = pathlib.Path(os.environ.get("E3_SETUP_DIR") or HOME / ".claude" / "e3-setup")
STAAT = STAAT_DIR / "staat.json"
PROFIEL = HOME / ".claude" / "e3-shared.json"
PLUGINS = HOME / ".claude" / "plugins" / "installed_plugins.json"
NU = dt.datetime.now().astimezone()

MY_NAMEN = ("My Drive", "Mijn Drive")
SHARED_NAMEN = ("Shared drives", "Gedeelde drives")


# ---------- basis ----------

def config_pad(m):
    """De interne configuratie (personen, webapp, geweigerde adressen) staat op de shared drive, niet in de publieke repo."""
    if os.environ.get("E3_SETUP_CONFIG"):
        return pathlib.Path(os.environ["E3_SETUP_CONFIG"])
    _, sh = drives()
    return sh / pathlib.Path(m["paden"]["config"]) if sh and m["paden"].get("config") else None


def manifest():
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    q = config_pad(m)
    cfg = lees_json(q, None) if q else None
    m["config_gevonden"] = bool(cfg)
    for k, v in (cfg or {}).items():
        if isinstance(v, dict) and isinstance(m.get(k), dict):
            m[k] = {**m[k], **v}
        else:
            m[k] = v
    for k, v in (("personen", {}), ("geweigerd", []), ("webapp_gebruikers", []), ("webapp", ""), ("uren_nieuw", [["10:55", "15:55"]])):
        m.setdefault(k, v)
    return m


def lees_json(p, standaard=None):
    try:
        return json.loads(pathlib.Path(p).read_text(encoding="utf-8-sig"))
    except Exception:
        return standaard


def schrijf_json(p, data, droog, wat):
    if droog:
        return f"zou schrijven: {wat}"
    p = pathlib.Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)
    spiegel(p)
    return f"geschreven: {wat}"


def spiegel(p):
    """Testopstelling (sandbox): kopie van staat en rapport naar een map die de host leest."""
    doel = os.environ.get("E3_SETUP_SPIEGEL")
    if doel and pathlib.Path(p).is_file():
        try:
            pathlib.Path(doel).mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, pathlib.Path(doel) / pathlib.Path(p).name)
        except OSError:
            pass


def dic(x):
    """Een notitie die geen object is (bv. kapotte JSON uit PowerShell) telt als leeg."""
    return x if isinstance(x, dict) else {}


def staat(ini):
    return (lees_json(STAAT, {}) or {}).get(ini, {})


def bewaar_staat(ini, deel, droog):
    alles = lees_json(STAAT, {}) or {}
    alles.setdefault(ini, {}).update(deel)
    return schrijf_json(STAAT, alles, droog, "staat van de wizard")


def drives():
    """(my_drive, shared_drives) van Google Drive for desktop, of (None, None)."""
    if os.environ.get("E3_DRIVE_ROOT"):
        r = pathlib.Path(os.environ["E3_DRIVE_ROOT"])
        return (next((r / n for n in MY_NAMEN if (r / n).is_dir()), None),
                next((r / n for n in SHARED_NAMEN if (r / n).is_dir()), None))
    for letter in string.ascii_uppercase[2:]:
        r = pathlib.Path(f"{letter}:\\")
        try:
            my = next((r / n for n in MY_NAMEN if (r / n).is_dir()), None)
            sh = next((r / n for n in SHARED_NAMEN if (r / n).is_dir()), None)
        except OSError:
            continue
        if my or sh:
            return my, sh
    return None, None


def pad(m, sleutel):
    _, sh = drives()
    if not sh:
        return None
    return sh / pathlib.Path(m["paden"][sleutel])


def iso(s):
    try:
        t = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return t if t.tzinfo else t.astimezone()
    except Exception:
        return None


def persoon(m, ini, st):
    p = dict(m["personen"].get(ini, {}))
    ck = dic(st.get("checklist"))
    for k in ("naam", "mail"):
        if ck.get(k):
            p[k] = ck[k]
    acc = dic(st.get("account"))
    if acc.get("mail"):
        p["mail"] = acc["mail"]
    for k in ("toestel", "granola", "plaud", "opnemen", "whatsapp", "rol", "eigenaar"):
        if k in st.get("antwoord", {}):
            p[k] = st["antwoord"][k]
    zetel = dic(st.get("claude_code")).get("zetel")
    if zetel:
        p["zetel"] = zetel
    if not p.get("dossync_uren"):
        bezet = {tuple(x["dossync_uren"]) for x in m["personen"].values() if x.get("dossync_uren")}
        p["dossync_uren"] = next((u for u in m["uren_nieuw"] if tuple(u) not in bezet), m["uren_nieuw"][-1])
    return p


def vul(tekst, m, ini, p, **extra):
    w = {"INI": ini, "mail": p.get("mail") or f"<werkadres van {ini}>",
         "webapp": m["webapp"] or "de webapp (de link staat in de config op E3 - Finance; eerst Google Drive voor desktop)",
         "beheerder": m["beheerder"], "uren": " en ".join(p.get("dossync_uren") or []),
         "connector": "de connector met een ✗"}
    w.update(extra)
    return re.sub(r"\{(\w+)\}", lambda x: str(w.get(x.group(1), x.group(0))), tekst or "")


def geldt(stap, p):
    g = stap["geldt"]
    if g == "altijd":
        return True
    if g in ("granola", "plaud", "opnemen", "whatsapp"):
        return p.get(g)          # True, False of None (nog te vragen)
    if g == "eigenaar":
        return bool(p.get("eigenaar"))   # enkel de eigenaar (Joëll): bv. de retro-cloudtaak
    if g in ("iphone", "android"):
        t = (p.get("toestel") or "").lower()
        return None if not t else t == g
    return True


def vrijgave(m, stap):
    """De vrijgave van de flow waar de stap bij hoort (veld flow), met de reden."""
    f = next((f for f in m["flows"] if f["id"] == stap["flow"]), None)
    return (f["vrijgave"], f.get("reden", "")) if f else ("vrij", "")


# ---------- controles van de laptop (lezen enkel) ----------

def ps(cmd, timeout=30):
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True,
                           timeout=timeout, encoding="utf-8", errors="replace")
        return r.stdout.strip()
    except Exception:
        return ""


def browser():
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"), os.environ.get("LOCALAPPDATA")):
        if base:
            for rel in (r"Google\Chrome\Application\chrome.exe", r"Microsoft\Edge\Application\msedge.exe"):
                if os.path.exists(os.path.join(base, rel)):
                    return True
    return bool(shutil.which("chrome") or shutil.which("msedge"))


def c_laptop(m, ini, p, st):
    my, sh = drives()
    fin = sh and (sh / "E3 - Finance").is_dir()
    py = sys.version_info >= (3, 10)
    delen = [f"Windows {platform.release()}" if os.name == "nt" else f"geen Windows ({platform.system()})",
             f"Python {platform.python_version()}" + ("" if py else " (te oud)"),
             f"Drive voor desktop op {my.anchor if my else (sh.anchor if sh else '-')}" if (my or sh) else "Drive voor desktop niet gevonden",
             "E3 - Finance zichtbaar" if fin else "E3 - Finance niet zichtbaar",
             "Chrome of Edge" if browser() else "geen Chrome of Edge"]
    ok = os.name == "nt" and py and bool(my) and bool(fin)
    return ok, ", ".join(delen)


def geinstalleerd():
    d = lees_json(PLUGINS, {}) or {}
    uit = {}
    for naam, lijst in (d.get("plugins") or {}).items():
        if lijst:
            uit[naam] = lijst[-1]
    return uit


def c_plugins(m, ini, p, st):
    inst = geinstalleerd()
    nodig = ["setup", "tools", "deliverables", "dossync"]
    gevonden, mist = [], []
    for n in nodig:
        k = next((k for k in inst if k.split("@")[0] == n), None)
        (gevonden.append(f"{n} {inst[k].get('version', '?')}") if k else mist.append(n))
    oud = [k for k in inst if k.split("@")[0] in ("arx", "mail", "analyst-tools")]
    detail = "aanwezig: " + (", ".join(gevonden) or "geen")
    if mist:
        detail += "; ontbreekt: " + ", ".join(mist)
    if oud:
        detail += "; verouderd, mag weg: " + ", ".join(oud)
    return not mist, detail


TI_BEGIN = "<!-- E3 teaminstructies begin -->"
TI_EINDE = "<!-- E3 teaminstructies einde -->"
CLAUDE_MD = HOME / ".claude" / "CLAUDE.md"
TI_BLOK = re.compile(re.escape(TI_BEGIN) + r".*?" + re.escape(TI_EINDE), re.S)


def teaminstructies_tekst(m):
    """(tekst onder de eerste lijn --- van Teaminstructies Claude.md, of None, en een reden)."""
    q = pad(m, "teaminstructies")
    if not q or not q.is_file():
        return None, "Teaminstructies Claude.md niet zichtbaar (E3 - Finance › Framework › 01 Framework)"
    tekst = q.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    delen = re.split(r"(?m)^---[ \t]*$", tekst, maxsplit=1)
    if len(delen) < 2 or not delen[1].strip():
        return None, "geen lijn --- met tekst eronder in Teaminstructies Claude.md"
    return delen[1].strip("\n"), ""


def c_teaminstructies(m, ini, p, st):
    bron, reden = teaminstructies_tekst(m)
    if bron is None:
        return None, reden
    huidig = CLAUDE_MD.read_bytes().decode("utf-8-sig").replace("\r\n", "\n") if CLAUDE_MD.is_file() else ""
    blok = TI_BLOK.search(huidig)
    if not blok:
        return False, "~/.claude/CLAUDE.md heeft het blok E3 teaminstructies nog niet" if huidig else "~/.claude/CLAUDE.md bestaat nog niet"
    inhoud = blok.group(0)[len(TI_BEGIN):-len(TI_EINDE)].strip("\n")
    if inhoud != bron.strip("\n"):
        return False, "het blok E3 teaminstructies in ~/.claude/CLAUDE.md is verouderd"
    return True, "~/.claude/CLAUDE.md bevat de huidige teaminstructies"


def c_rechten(m, ini, p, st):
    t = st.get("schrijftest", {})
    lees = []
    for k in ("framework", "klanten"):
        q = pad(m, k)
        lees.append(f"{k} {'leesbaar' if q and q.is_dir() else 'niet zichtbaar'}")
    if t.get("datum") == NU.date().isoformat():
        return bool(t.get("ok")), f"schrijftest vandaag: {t.get('detail')}; " + ", ".join(lees)
    return None, "schrijftest nog niet gedaan (doe A5); " + ", ".join(lees)


def c_profiel(m, ini, p, st):
    prof = lees_json(PROFIEL, {}) or {}
    ok = prof.get("initialen") == ini and prof.get("mailbox") == p.get("mail")
    return ok, f"e3-shared.json: initialen {prof.get('initialen') or '-'}, mailbox {prof.get('mailbox') or '-'}"


def c_webapp(m, ini, p, st):
    if not m.get("config_gevonden"):
        return None, "eerst Google Drive voor desktop met E3 - Finance (A2): de webapp-gebruikers staan in de config op de drive"
    if p.get("mail") and p["mail"] not in m["webapp_gebruikers"]:
        return False, (f"{p['mail']} staat niet in de gebruikerslijst van de webapp: "
                       f"{m['beheerder']} voegt het adres toe (GEBRUIKERS in webapp/Code.js) en deployt")
    my, _ = drives()
    s = lees_json(my / "Dossier-sync" / "dossync-status.json", None) if my else None
    if not s:
        return False, "geen dossync-status.json in My Drive › Dossier-sync: de webapp is nog niet geopend"
    if s.get("gebruiker") != ini:
        return False, f"dossync-status.json staat op {s.get('gebruiker')}, niet op {ini}"
    g = iso(s.get("geschreven"))
    if not g or (NU - g).total_seconds() > 1800:
        return False, f"verwerking niet actief: status laatst geschreven {s.get('geschreven')}"
    lr = s.get("laatsteRun")
    return True, f"actief (status {g:%d/%m %H:%M}); laatste run {lr or 'nog geen'}"


def c_bijlagen(m, ini, p, st):
    my, _ = drives()
    b = lees_json(my / "_Uit mail" / "bijlagen.json", None) if my else None
    if not b:
        return False, "geen _Uit mail/bijlagen.json in My Drive: de bijlagen-inname staat niet aan"
    t = iso(b.get("laatsteRun"))
    venster = 1800 if 6 <= NU.hour < 22 else 9 * 3600
    if not t or (NU - t).total_seconds() > venster:
        return False, f"bijlagen.json laatst bijgewerkt {b.get('laatsteRun')}"
    n = len(b.get("items") or [])
    wachtrij = [f for f in my.iterdir() if f.is_file()] if my else []
    oudste = min((f.stat().st_mtime for f in wachtrij), default=None)
    extra = f"; {len(wachtrij)} bestanden in de wachtrij" + (
        f", oudste {dt.datetime.fromtimestamp(oudste):%d/%m}" if oudste else "")
    return True, f"bijgewerkt {t.astimezone():%d/%m %H:%M}, {n} items{extra}"


def transcript_skill():
    kand = sorted(glob.glob(str(HOME / ".claude" / "plugins" / "cache" / "*" / "tools" / "*" / "skills" / "transcript")),
                  key=lambda x: [int(n) if n.isdigit() else 0 for n in re.findall(r"\d+", pathlib.Path(x).parent.parent.name)])
    return pathlib.Path(kand[-1]) if kand else None


def c_transcript(m, ini, p, st):
    sk = transcript_skill()
    delen, ok = [], True
    if not sk:
        return False, "transcript-skill niet gevonden (plugin tools ontbreekt)"
    heeft_inbox = (sk / "scripts" / "inbox.py").exists()
    delen.append(f"skill {sk.parent.parent.name}" + ("" if heeft_inbox else " zonder inbox.py (nog oude versie)"))
    ok &= heeft_inbox
    sysmd = HOME / ".claude" / "e3-transcript" / "systeem.md"
    delen.append("systeem.md aanwezig" if sysmd.exists() else "faster-whisper nog niet ingesteld")
    ok &= sysmd.exists()
    cfg = lees_json(HOME / ".claude" / "e3-transcript" / "config.json", {}) or {}
    root = cfg.get("root") or ""
    if "Brain" in root or "Shared drives" in root:
        delen.append(f"uitvoermap {root} ligt op de drive: moet Documents\\Transcripts zijn")
        ok = False
    for d in ("Sound Recordings", "Transcripts"):
        bestaat = (HOME / "Documents" / d).is_dir()
        delen.append(f"Documents\\{d} {'ok' if bestaat else 'ontbreekt'}")
        ok &= bestaat
    proef = st.get("proefopname")
    if proef:
        delen.append(f"proefopname: {proef.get('detail')}")
        ok &= bool(proef.get("ok"))
    else:
        delen.append("proefopname nog niet gedaan")
        ok = False
    return ok, "; ".join(delen)


WA_CACHE = str(HOME / ".claude" / "plugins" / "cache" / "*" / "tools" / "*" / "skills" / "whatsapp")
WA_DEV = HOME / "dev" / "e3-finance-skills" / "tools" / "skills" / "whatsapp"


def whatsapp_skill():
    """Nieuwste geïnstalleerde whatsapp-skill; anders een dev-checkout van de repo (beheerder)."""
    kand = sorted(glob.glob(WA_CACHE),
                  key=lambda x: [int(n) if n.isdigit() else 0 for n in re.findall(r"\d+", pathlib.Path(x).parent.parent.name)])
    if kand:
        return pathlib.Path(kand[-1])
    return WA_DEV if (WA_DEV / "scripts" / "wa_lezer.py").exists() else None


def heeft_playwright():
    r = subprocess.run([sys.executable, "-c", "import playwright"], capture_output=True)
    return r.returncode == 0


def c_whatsapp(m, ini, p, st):
    """Lezer klaar = skill aanwezig, Playwright en Chrome op de laptop, profiel gekoppeld en lijst Equals Three binnen.
    De koppeling zelf wordt niet bij elke controle opnieuw gestart (duurt een minuut): de laatste meting staat in de staat."""
    sk = whatsapp_skill()
    if not sk:
        return False, "whatsapp-skill niet gevonden (plugin tools te oud: eerst A3)"
    delen = [f"skill {sk.parent.parent.name}"]
    pw, chrome = heeft_playwright(), browser()
    delen.append("Playwright aanwezig" if pw else "Playwright ontbreekt")
    delen.append("Chrome aanwezig" if chrome else "geen Chrome")
    w = st.get("whatsapp") or {}
    if not w:
        delen.append("nog niet gekoppeld (doe W1)")
        return False, "; ".join(delen)
    delen.append(f"{w.get('detail')} ({w.get('datum')})")
    return bool(pw and chrome and w.get("ok")), "; ".join(delen)


def c_publiek(m, ini, p, st):
    if os.environ.get("E3_TEST_SNEL"):
        return True, "overgeslagen in de test"
    hosts = ["https://kbopub.economie.fgov.be/kbopub/zoeknummerform.html",
             "https://consult.cbso.nbb.be/", "https://www.ejustice.just.fgov.be/cgi_tsv/rech.pl?language=nl"]
    mis = []
    for h in hosts:
        try:
            req = urllib.request.Request(h, headers={"User-Agent": "Mozilla/5.0 e3-setup"})
            with urllib.request.urlopen(req, timeout=10) as r:
                if r.status >= 400:
                    mis.append(h.split("/")[2])
        except Exception:
            # Een kale Windows mist soms tussencertificaten die Python niet zelf ophaalt; Windows haalt ze wel op.
            code = ps(f"try {{ (Invoke-WebRequest -UseBasicParsing -Uri '{h}' -TimeoutSec 15).StatusCode }} catch {{ 0 }}", timeout=30)
            if not (code.isdigit() and 200 <= int(code) < 400):
                mis.append(h.split("/")[2])
    return not mis, "KBO, NBB en Staatsblad bereikbaar" if not mis else "niet bereikbaar: " + ", ".join(mis)


# ---------- programma's, GitHub en mappen (sinds de wizard een eigen repo is) ----------

ORG = "EqualsThree-Git"
PRIVE_REPOS = [f"{ORG}/e3-finance-skills", f"{ORG}/e3-dossync"]


def heeft(cmd):
    if shutil.which(cmd):
        return True
    return cmd == "claude" and (HOME / ".local" / "bin" / "claude.exe").exists()


def claude_app():
    if os.environ.get("E3_TEST_SNEL"):          # tests: geen PowerShell per controle
        return True
    if os.name != "nt":
        return False
    if (pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "AnthropicClaude" / "claude.exe").exists():
        return True
    return bool(ps("(Get-AppxPackage -Name Claude).Name", timeout=20))


def drive_app():
    return os.name == "nt" and bool(glob.glob(str(pathlib.Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Google" / "Drive File Stream" / "*" / "GoogleDriveFS.exe")))


def webview2():
    """Google Drive voor desktop vraagt de WebView2-runtime (zit bij Edge; ontbreekt zonder Edge)."""
    if os.environ.get("E3_TEST_SNEL") or os.name != "nt":
        return True
    import winreg
    for hive, sub in ((winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
                      (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}")):
        try:
            with winreg.OpenKey(hive, sub) as k:
                if winreg.QueryValueEx(k, "pv")[0] not in ("", "0.0.0.0"):
                    return True
        except OSError:
            continue
    return False


def vcredist():
    if os.environ.get("E3_TEST_SNEL") or os.name != "nt":
        return True
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64") as k:
            return winreg.QueryValueEx(k, "Installed")[0] == 1
    except OSError:
        return False


def programmas(p):
    """[(naam, winget-id, aanwezig)] van wat deze gebruiker nodig heeft."""
    lijst = [("Git", "Git.Git", heeft("git")), ("Node.js", "OpenJS.NodeJS.LTS", heeft("node")),
             ("GitHub CLI", "GitHub.cli", heeft("gh")), ("Claude Code", "Anthropic.ClaudeCode", heeft("claude")),
             ("Claude-app", "Anthropic.Claude", claude_app()),
             ("WebView2-runtime (voor Drive)", "Microsoft.EdgeWebView2Runtime", webview2()),
             ("Google Drive voor desktop", "Google.GoogleDrive", drive_app())]
    if p.get("opnemen") is not False:
        lijst.append(("Visual C++-runtime (faster-whisper)", "Microsoft.VCRedist.2015+.x64", vcredist()))
    if p.get("whatsapp"):
        lijst.append(("Chrome (WhatsApp-lezer)", "Google.Chrome", browser() and any(
            os.path.exists(os.path.join(b, r"Google\Chrome\Application\chrome.exe"))
            for b in (os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", ""), os.environ.get("LOCALAPPDATA", "")) if b)))
    return lijst


def c_programmas(m, ini, p, st):
    lijst = programmas(p)
    mist = [n for n, _, ok in lijst if not ok]
    py = sys.version_info >= (3, 10)
    detail = f"Python {platform.python_version()}" + ("" if py else " (te oud)") + "; " + (
        "aanwezig: " + ", ".join(n for n, _, ok in lijst if ok) if not mist else "ontbreekt: " + ", ".join(mist))
    return py and not mist, detail


def a_programmas(m, ini, p, st, droog):
    uit = []
    for naam, id_, ok in programmas(p):
        if ok:
            continue
        cmd = winget(id_)
        if droog:
            uit.append(f"zou draaien: {cmd}")
            continue
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:   # geen installatie per gebruiker: voor de hele pc (Windows vraagt toestemming)
            r = subprocess.run(cmd.replace(" --scope user", ""), shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
        uit.append(f"{naam}: {'geïnstalleerd' if r.returncode == 0 else 'mislukt (' + str(r.returncode) + ')'}")
    return uit or ["alles aanwezig"]


def gh(*args, timeout=30):
    try:
        r = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return r.returncode, (r.stdout or "").strip()
    except Exception:
        return 1, ""


def c_github(m, ini, p, st):
    if not heeft("gh"):
        return False, "GitHub CLI ontbreekt (eerst A0)"
    rc, _ = gh("auth", "status", "--hostname", "github.com")
    if rc:
        return False, "niet aangemeld bij GitHub"
    _, wie = gh("api", "user", "--jq", ".login")
    mist = [r for r in PRIVE_REPOS if gh("api", f"repos/{r}", "--silent")[0]]
    if mist:
        return False, f"aangemeld als {wie or '?'}, geen toegang tot {', '.join(mist)}"
    return True, f"aangemeld als {wie}, toegang tot {', '.join(PRIVE_REPOS)}"


def mappen(m):
    """[(label, pad, mag_maken)]: wat de flows op de drives verwachten."""
    my, _ = drives()
    uit = [(k, pad(m, s), mag) for k, s, mag in (("Dossync › inbox", "inbox", False), ("Dossync › inbox › ruw", "inbox_ruw", True),
                                                 ("Dossync › opvang", "opvang", False), ("Dossync › opvang › runs", "opvang_runs", True))]
    uit.append(("My Drive › Claude workspace", my / "Claude workspace" if my else None, True))
    return uit


def c_mappen(m, ini, p, st):
    mis = [k for k, q, _ in mappen(m) if not q or not q.is_dir()]
    my, _ = drives()
    extra = "; My Drive zelf is de wachtrij (TE VERPLAATSEN)" if my else "; My Drive niet zichtbaar"
    return (not mis and bool(my)), ("alle mappen aanwezig" if not mis else "ontbreekt: " + ", ".join(mis)) + extra


def a_mappen(m, ini, p, st, droog):
    uit = []
    for k, q, mag in mappen(m):
        if q is None:
            uit.append(f"{k}: drive niet zichtbaar (eerst A2)")
        elif q.is_dir():
            continue
        elif not mag or not q.parent.is_dir():
            uit.append(f"{k} ontbreekt: stap voor de beheerder")
        elif droog:
            uit.append(f"zou aanmaken: {k}")
        else:
            q.mkdir(exist_ok=True)
            uit.append(f"aangemaakt: {k}")
    return uit or ["alle mappen aanwezig"]


# ---------- checklist (eerste scherm) ----------

def checklist(m, wacht_min=30, open_browser=True):
    """Lokale pagina op 127.0.0.1: wie ben je en wat gebruik je. Bewaart in de staat en het profiel, en stopt dan."""
    import http.server
    import threading
    import webbrowser
    prof = lees_json(PROFIEL, {}) or {}
    oud_ini = (prof.get("initialen") or "").upper()
    oud = staat(oud_ini) if oud_ini else {}
    flows = [{"id": f["id"], "naam": f["naam"], "vrijgave": f["vrijgave"],
              "geldt": sorted({s["geldt"] for s in m["stappen"] if s["id"] in f["stappen"]})} for f in m["flows"]]
    data = {"domein": m["domein"], "geweigerd": m["geweigerd"], "flows": flows,
            "personen": [{"ini": k, "naam": v.get("naam"), "mail": v.get("mail")} for k, v in m["personen"].items()],
            "vooraf": {"ini": oud_ini, **(oud.get("checklist") or {}), **(oud.get("antwoord") or {})}}
    pagina = (HERE / "checklist.html").read_text(encoding="utf-8").replace("/*DATA*/null", json.dumps(data, ensure_ascii=False))
    klaar = {}

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _stuur(self, code, body, soort):
            b = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", soort)
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            self._stuur(200, pagina, "text/html; charset=utf-8")

        def do_POST(self):
            try:
                b = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                uit = bewaar_checklist(m, b)
            except Exception as e:
                uit = {"ok": False, "fout": str(e)}
            self._stuur(200, json.dumps(uit, ensure_ascii=False), "application/json")
            if uit.get("ok"):
                klaar.update(uit)

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    url = f"http://127.0.0.1:{srv.server_port}/"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"CHECKLIST: {url}", file=sys.stderr, flush=True)
    if open_browser:
        open_in_browser(url, webbrowser)
    einde = time.time() + wacht_min * 60
    while not klaar and time.time() < einde:
        time.sleep(0.3)
    time.sleep(0.5)
    srv.shutdown()
    return klaar or {"ok": False, "fout": f"na {wacht_min} minuten niets bewaard", "url": url}


def browser_exe():
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"), os.environ.get("LOCALAPPDATA")):
        if base:
            for rel in (r"Google\Chrome\Application\chrome.exe", r"Microsoft\Edge\Application\msedge.exe"):
                if os.path.exists(os.path.join(base, rel)):
                    return os.path.join(base, rel)
    return None


def open_in_browser(url, webbrowser):
    """Rechtstreeks in Chrome of Edge: op een kale pc (of in Windows Sandbox) is er niet altijd een standaardbrowser."""
    exe = browser_exe()
    if exe:
        try:
            subprocess.Popen([exe, url])
            return
        except OSError:
            pass
    webbrowser.open(url)


def bewaar_checklist(m, b):
    ini = re.sub(r"[^A-Za-z]", "", str(b.get("ini") or "")).upper()
    mail = str(b.get("mail") or "").strip().lower()
    naam = str(b.get("naam") or "").strip()
    if not 2 <= len(ini) <= 4:
        return {"ok": False, "fout": "initialen: twee tot vier letters"}
    if not naam:
        return {"ok": False, "fout": "naam ontbreekt"}
    fout = adres_fout(m, mail)
    if fout:
        return {"ok": False, "fout": fout}
    ja = lambda k: b.get(k) in (True, "ja", "true")
    antwoord = {"rol": b.get("rol") if b.get("rol") in ("partner", "consultant") else "consultant",
                "eigenaar": ja("eigenaar") or b.get("rol") == "eigenaar",
                "toestel": "iPhone" if str(b.get("toestel")).lower() == "iphone" else "Android",
                "granola": ja("granola"), "plaud": ja("plaud"), "opnemen": ja("opnemen"), "whatsapp": ja("whatsapp")}
    st = staat(ini)
    bewaar_staat(ini, {"checklist": {"naam": naam, "mail": mail, "tijd": NU.isoformat(timespec="minutes")},
                       "antwoord": {**dic(st.get("antwoord")), **antwoord}}, False)
    prof = lees_json(PROFIEL, {}) or {}
    if prof.get("initialen") != ini or prof.get("mailbox") != mail:
        schrijf_json(PROFIEL, {**prof, "initialen": ini, "mailbox": mail}, False, "profiel")
    return {"ok": True, "ini": ini, "mail": mail, "naam": naam, "antwoord": antwoord}


# ---------- E3CRM: teamregister op de persoonsfiche ----------

E3CRM_CFG = HOME / ".claude" / "e3crm.json"


class E3crmFout(Exception):
    pass


def e3crm_toegang():
    url, token = os.environ.get("E3CRM_URL"), os.environ.get("E3CRM_TOKEN")
    c = lees_json(E3CRM_CFG, {}) or {}
    return url or c.get("url"), token or c.get("token")


def e3crm(body):
    """POST naar de opvraagfunctie van E3CRM. Het token gaat enkel in de aanvraag, nooit naar de uitvoer."""
    url, token = e3crm_toegang()
    if not url or not token:
        raise E3crmFout("geen E3CRM-toegang op deze laptop (~/.claude/e3crm.json ontbreekt)")
    req = urllib.request.Request(url, data=json.dumps({"token": token, **body}).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            a = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        raise E3crmFout(f"E3CRM niet bereikbaar ({e.__class__.__name__})")
    if not a.get("ok"):
        raise E3crmFout(a.get("fout") or "onbekende fout")
    return a.get("data") or {}


def wie_lost_op(fout):
    f = fout or ""
    if f.startswith("Geen persoon"):
        return f + " Daarna de wizard opnieuw starten."
    if "Kolommen ontbreken" in f:
        return "De eigenaar van E3CRM moet setup() draaien na de laatste push."
    return f


def c_e3crm(m, ini, p, st):
    if not all(e3crm_toegang()):
        return False, "geen E3CRM-toegang op deze laptop (~/.claude/e3crm.json ontbreekt)"
    try:
        lijst = e3crm({"actie": "team.lijst"})
    except E3crmFout as e:
        return False, str(e)
    eigen = next((x for x in lijst.get("team", []) if x.get("initialen") == ini), None)
    if not eigen or lijst.get("bron") != "e3crm":
        extra = "" if lijst.get("bron") == "e3crm" else " (terugval: nog niemand heeft initialen in E3CRM)"
        return False, f"{ini} staat nog niet op een fiche in E3CRM{extra}"
    adressen = [a.lower() for a in eigen.get("werkadres") or []]
    if (p.get("mail") or "").lower() not in adressen:
        return False, f"fiche {eigen.get('id')} heeft werkadres {', '.join(adressen) or '-'}, niet {p.get('mail')}"
    detail = f"fiche {eigen.get('id')}: {ini}, {', '.join(adressen)}"
    v = verwerker_kent(p["mail"])
    if v is None:
        return True, detail
    if v != ini:
        return False, detail + f"; de verwerker zet {p['mail']} om naar {v or 'niemand'}, niet naar {ini}"
    return True, detail + "; de verwerker herkent het werkadres"


# ---------- Eigen E3CRM-sleutel (26/11) ----------
# E3CRM geeft elke persoon eigen sleutels (Sleutels.js): 'laptop' voor Claude Code hier, 'cloud' voor de geplande taken
# op claude.ai (mag enkel lezen, voorstellen doen en correcties melden). De sleutel gaat per mail naar het werkadres uit het
# register; de persoon plakt hem zelf in de terminal (`wizard.py sleutel`), zodat Claude hem nooit ziet.


def e3crm_zonder_sleutel(body):
    """sleutel.aanvraag: de enige actie zonder sleutel."""
    url = e3crm_toegang()[0]
    if not url:
        raise E3crmFout("het adres van E3CRM is onbekend: eerst A7")
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            a = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        raise E3crmFout(f"E3CRM niet bereikbaar ({e.__class__.__name__})")
    if not a.get("ok"):
        raise E3crmFout(a.get("fout") or "onbekende fout")
    return a.get("data") or {}


def c_sleutel(m, ini, p, st):
    c = lees_json(E3CRM_CFG, {}) or {}
    if c.get("eigen") != ini:
        return False, ("nog geen eigen E3CRM-sleutel op deze laptop (nu de gedeelde beheersleutel)" if c
                       else "geen E3CRM-toegang op deze laptop")
    try:
        e3crm({"actie": "team.lijst"})
    except E3crmFout as e:
        return False, f"de eigen sleutel werkt niet: {e}"
    return True, f"eigen laptopsleutel van {ini} werkt"


def a_sleutel(m, ini, p, st, droog, soort="laptop"):
    if not p.get("mail") or adres_fout(m, p["mail"]):
        return ["eerst A1: geen geldig werkadres"]
    if soort == "laptop":
        ok, detail = c_sleutel(m, ini, p, st)
        if ok:
            return [detail + ", niets te doen"]
    if droog:
        return [f"zou een {soort}-sleutel aanvragen voor {p['mail']} (mail van tools@ naar het werkadres uit het register)"]
    try:
        r = e3crm_zonder_sleutel({"actie": "sleutel.aanvraag", "adres": p["mail"], "soort": soort})
    except E3crmFout as e:
        return [f"aanvraag mislukt: {e}"]
    if soort == "laptop":
        return [f"sleutel verstuurd naar {r.get('naar')}",
                f'GEBRUIKER: open de mail "Je E3CRM-sleutel (laptop)", voer in een terminal uit: python "{pathlib.Path(__file__)}" '
                f"sleutel --ini {ini} en plak de sleutel (je ziet hem niet). Daarna de wizard opnieuw starten."]
    return [f"cloudsleutel verstuurd naar {r.get('naar')}",
            "GEBRUIKER: claude.ai/code > omgeving kiezen > New environment (persoonlijk, nooit gedeeld): Network access Limited "
            "met script.google.com en script.googleusercontent.com, en bij Environment variables E3CRM_URL=<adres uit de mail> en "
            "E3CRM_TOKEN=<sleutel uit de mail>. Claude vult de sleutel nooit zelf in."]


def a_sleutel_cloud(m, ini, p, st, droog):
    return a_sleutel(m, ini, p, st, droog, "cloud")


def zet_sleutel(ini):
    """Door de persoon zelf in een terminal: de sleutel uit de mail plakken. Wordt getest en pas dan bewaard."""
    import getpass
    url = e3crm_toegang()[0]
    if not url:
        return {"fout": "het adres van E3CRM is onbekend: eerst A7"}
    sleutel = getpass.getpass("Plak je E3CRM-sleutel (laptop) en druk op Enter: ").strip()
    if not re.fullmatch(r"[0-9a-f]{64}", sleutel):
        return {"fout": "dat lijkt geen sleutel (64 tekens, 0-9 en a-f). Kopieer hem opnieuw uit de mail."}
    req = urllib.request.Request(url, data=json.dumps({"token": sleutel, "actie": "team.lijst"}).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            ok = json.loads(r.read().decode("utf-8")).get("ok")
    except Exception as e:
        return {"fout": f"E3CRM niet bereikbaar ({e.__class__.__name__})"}
    if not ok:
        return {"fout": "E3CRM kent deze sleutel niet. Gebruik de nieuwste mail; een oudere sleutel is vervangen."}
    E3CRM_CFG.parent.mkdir(parents=True, exist_ok=True)
    E3CRM_CFG.write_text(json.dumps({"url": url, "token": sleutel, "eigen": ini}), encoding="utf-8")
    return {"ok": True, "detail": f"eigen laptopsleutel van {ini} bewaard in ~/.claude/e3crm.json"}


def verwerker_kent(adres):
    """Initialen die de verwerker van dossync aan dit adres geeft (veld door), of None als die skill er niet is."""
    kand = sorted(glob.glob(str(HOME / ".claude" / "plugins" / "cache" / "*" / "dossync" / "*" / "skills" / "verwerker" / "scripts")))
    if not kand:
        return None
    code = ("import sys,json; sys.path.insert(0, sys.argv[1]); import verwerker as v; "
            "t = v.team(); print(json.dumps(v.wie_is(sys.argv[2], t) if t else None))")
    try:
        r = subprocess.run([sys.executable, "-c", code, kand[-1], adres], capture_output=True, text=True, timeout=90,
                           encoding="utf-8", errors="replace")
        return json.loads(r.stdout.strip().splitlines()[-1]) or ""
    except Exception:
        return None


PC = {"programmas": c_programmas, "github": c_github, "mappen": c_mappen, "teaminstructies": c_teaminstructies, "e3crm": c_e3crm, "sleutel": c_sleutel, "laptop": c_laptop, "plugins": c_plugins, "rechten": c_rechten, "profiel": c_profiel, "webapp": c_webapp,
      "bijlagen": c_bijlagen, "transcript": c_transcript, "whatsapp": c_whatsapp, "publiek": c_publiek}


def c_notitie(stap, st):
    """Stappen die Claude nakijkt: het resultaat staat in de staat onder 'noteer'."""
    sleutel = stap.get("noteer")
    if stap["soort"] == "gebruiker":
        n = st.get("test", {}).get(stap["id"])
    elif sleutel == "connector.<naam>":
        con = st.get("connector", {})
        if not con:
            return None, "connectors nog niet nagekeken"
        fout = {k: v for k, v in con.items() if not v.get("ok")}
        return (not fout), "; ".join(f"{k}: {v.get('adres') or '-'}{'' if v.get('ok') else ' ✗ ' + (v.get('detail') or '')}"
                                     for k, v in con.items())
    elif sleutel and sleutel.startswith("taak."):
        n = st.get("taak", {}).get(sleutel.split(".", 1)[1])
    else:
        n = st.get(sleutel) if sleutel else None
    if not n:
        return None, "nog niet nagekeken"
    if not isinstance(n, dict):
        return False, f"notitie onleesbaar ({str(n)[:60]}): opnieuw noteren"
    return bool(n.get("ok")), n.get("detail") or ""


def controleer(m, ini, andere_pc=False):
    st = staat(ini)
    p = persoon(m, ini, st)
    punten, vragen = [], set()
    for s in m["stappen"]:
        g = geldt(s, p)
        v, reden = vrijgave(m, s)
        punt = {"id": s["id"], "flow": s["flow"], "titel": s["titel"], "soort": s["soort"], "vrijgave": v,
                "wie": s["wie"], "actie": vul(s.get("actie") or s.get("controle"), m, ini, p),
                "gebruiker": vul(s.get("gebruiker"), m, ini, p)}
        if s.get("aandacht") and str(p.get("zetel") or "").lower() == "standard":
            punt["aandacht"] = s["aandacht"]
        if g is None:
            vragen.add(s["geldt"])
            punt.update(status="vraag", detail=f"eerst vragen: {s['geldt']}")
        elif g is False:
            punt.update(status="nvt", detail="niet van toepassing")
        elif v == "dicht":
            punt.update(status="dicht", detail=reden)
        elif s["soort"] == "pc" and andere_pc:
            punt.update(status="op-laptop", detail=f"na te kijken op de laptop van {ini}")
        else:
            if s["soort"] == "pc":
                try:
                    ok, detail = PC[s["controle"]](m, ini, p, st)
                except Exception as e:  # een controle mag de wizard nooit laten vallen
                    ok, detail = False, f"controle faalde: {e}"
            else:
                ok, detail = c_notitie(s, st)
            status = {True: "ok", False: "fout", None: "open"}[ok]
            if s["soort"] == "taak" and v == "proef" and status != "ok":
                status, detail = "klaar-te-zetten", (reden or "flow nog in proef").rstrip(".") + "; de taak wordt voorbereid, niet ingepland"
            punt.update(status=status, detail=detail)
        punten.append(punt)
    volgende = next((x for x in punten if x["status"] in ("fout", "open", "vraag")), None)
    return {"ini": ini, "config": m.get("config_gevonden"), "persoon": {k: p.get(k) for k in ("naam", "mail", "rol", "toestel", "granola", "plaud", "opnemen", "whatsapp", "dossync_uren", "eigenaar", "zetel")},
            "vragen": sorted(vragen), "punten": punten, "volgende": volgende and volgende["id"],
            "andere_pc": andere_pc, "tijd": NU.isoformat(timespec="minutes")}


# ---------- acties ----------

def winget(id_):
    return f"winget install -e --id {id_} --source winget --scope user --accept-package-agreements --accept-source-agreements --disable-interactivity"


def a_laptop(m, ini, p, st, droog):
    uit = []
    if sys.version_info < (3, 10):
        cmd = winget("Python.Python.3.12")
        if droog:
            uit.append(f"zou draaien: {cmd}")
        else:
            ok = subprocess.run(cmd, shell=True).returncode == 0
            uit.append("Python 3.12 geïnstalleerd" if ok else "Python installeren mislukt")
    my, sh = drives()
    if not (my and sh):
        uit.append("Drive voor desktop ontbreekt: stap voor de gebruiker")
    return uit or ["niets te doen"]


# De skills komen uit de marketplaces op GitHub (EqualsThree-Git); de oude chat-skills (zips) worden niet meer geïnstalleerd.
MARKTEN = {"e3-setup": "EqualsThree-Git/e3-setup", "e3-shared": "EqualsThree-Git/e3-finance-skills", "e3-dossync": "EqualsThree-Git/e3-dossync"}
MARKT_PLUGIN = {"setup": "e3-setup", "tools": "e3-shared", "deliverables": "e3-shared", "dossync": "e3-dossync"}


def a_plugins(m, ini, p, st, droog):
    ok, detail = c_plugins(m, ini, p, st)
    if ok:
        return ["plugins in orde: " + detail]
    claude = shutil.which("claude")
    inst = {k.split("@")[0] for k in geinstalleerd()}
    mist = [n for n in MARKT_PLUGIN if n not in inst]
    bekend = (lees_json(HOME / ".claude" / "plugins" / "known_marketplaces.json", {}) or {})
    markt = {n: MARKT_PLUGIN[n] for n in mist}
    cmds = [f"claude plugin marketplace add {MARKTEN[mk]}" for mk in dict.fromkeys(markt.values()) if mk not in bekend]
    cmds += [f"claude plugin install {n}@{markt[n]}" for n in mist]
    if droog:
        return [f"zou draaien: {c}" for c in cmds] or ["niets te doen"]
    if not claude:
        return ["claude-CLI niet gevonden: de plugins komen via de organisatie (Installed by default) of met /plugin in Claude"]
    uit = []
    for c in cmds:
        r = subprocess.run(c, shell=True, capture_output=True, text=True)
        uit.append(f"{c}: {'ok' if r.returncode == 0 else (r.stderr or r.stdout).strip()[:200]}")
    return uit


def a_teaminstructies(m, ini, p, st, droog):
    """Zet het blok tussen de markeringen in ~/.claude/CLAUDE.md. De rest van het bestand blijft ongemoeid."""
    bron, reden = teaminstructies_tekst(m)
    if bron is None:
        return [reden + ": stap voor de gebruiker"]
    ruw = CLAUDE_MD.read_bytes().decode("utf-8") if CLAUDE_MD.is_file() else ""
    bom = ruw.startswith("\ufeff")
    huidig = ruw.lstrip("\ufeff")
    crlf = "\r\n" in huidig
    huidig = huidig.replace("\r\n", "\n")
    blok = TI_BEGIN + "\n" + bron.strip("\n") + "\n" + TI_EINDE
    if TI_BLOK.search(huidig):
        nieuw, wat = TI_BLOK.sub(lambda _: blok, huidig, count=1), "blok E3 teaminstructies vervangen"
    elif huidig.strip():
        nieuw, wat = huidig.rstrip("\n") + "\n\n" + blok + "\n", "blok E3 teaminstructies onderaan toegevoegd, de rest bleef staan"
    else:
        nieuw, wat = blok + "\n", "~/.claude/CLAUDE.md gemaakt met het blok E3 teaminstructies"
    if nieuw == huidig:
        return ["teaminstructies al actueel"]
    if droog:
        return [f"zou doen: {wat}"]
    CLAUDE_MD.parent.mkdir(parents=True, exist_ok=True)
    if crlf:
        nieuw = nieuw.replace("\n", "\r\n")
    CLAUDE_MD.write_bytes((("\ufeff" if bom else "") + nieuw).encode("utf-8"))
    return [wat + " (start een nieuwe sessie, dan laadt Claude ze)"]


def a_rechten(m, ini, p, st, droog):
    doelen = [("inbox", pad(m, "inbox")), ("opvang", pad(m, "opvang")), ("ruw", pad(m, "inbox_ruw"))]
    if droog:
        return [f"zou een testbestand _setup-test-{ini}.tmp schrijven en meteen wissen in {k}" for k, _ in doelen]
    res, ok = [], True
    for k, d in doelen:
        if not d or not d.is_dir():
            if k == "ruw" and d and d.parent.is_dir():
                res.append("ruw ontbreekt")
                continue
            res.append(f"{k} niet zichtbaar")
            ok = False
            continue
        f = d / f"_setup-test-{ini}.tmp"
        try:
            f.write_text("setup-test", encoding="utf-8")
            f.unlink()
            res.append(f"{k} schrijfbaar")
        except OSError as e:
            res.append(f"{k} niet schrijfbaar ({e.__class__.__name__})")
            ok = False
    bewaar_staat(ini, {"schrijftest": {"datum": NU.date().isoformat(), "ok": ok, "detail": ", ".join(res)}}, False)
    return res


def a_profiel(m, ini, p, st, droog):
    if not p.get("mail"):
        return ["eerst de checklist of A1: het werkadres ontbreekt"]
    if adres_fout(m, p["mail"]):
        return [f"niet geschreven: {adres_fout(m, p['mail'])}"]
    my, sh = drives()
    prof = lees_json(PROFIEL, {}) or {}
    nieuw = dict(prof)
    nieuw.update({"initialen": ini, "mailbox": p["mail"]})
    if sh:
        nieuw.setdefault("drive", str(sh))
    if my:
        nieuw.setdefault("werkmap", str(my / "Claude workspace"))
    uit = []
    if nieuw != prof:
        uit.append(schrijf_json(PROFIEL, nieuw, droog, f"~/.claude/e3-shared.json ({', '.join(k for k in nieuw if nieuw.get(k) != prof.get(k))})"))
    else:
        uit.append("e3-shared.json klopt al")
    return uit


def a_transcript(m, ini, p, st, droog):
    sk = transcript_skill()
    if not sk:
        return ["transcript-skill ontbreekt: eerst A3"]
    setup = sk / "scripts" / "setup.py"
    root = HOME / "Documents" / "Transcripts"
    stappen = [[sys.executable, str(setup), "--install"], [sys.executable, str(setup), "--root", str(root)]]
    if droog:
        return [f"zou draaien: {' '.join(c[1:])}" for c in stappen] + [
            "zou Documents\\Sound Recordings en Documents\\Transcripts aanmaken als ze ontbreken",
            "zou een proefopname van een halve minuut maken (Windows-spraak, geen microfoon) en lokaal uitschrijven in een tijdelijke map"]
    uit = []
    ok_sys = (HOME / ".claude" / "e3-transcript" / "systeem.md").exists()
    if not ok_sys:
        for c in stappen:
            r = subprocess.run(c)
            uit.append(f"{pathlib.Path(c[1]).name} {' '.join(c[2:])}: {'ok' if r.returncode == 0 else 'fout ' + str(r.returncode)}")
    for d in ("Sound Recordings", "Transcripts"):
        (HOME / "Documents" / d).mkdir(parents=True, exist_ok=True)
    if dic(st.get("proefopname")).get("ok"):
        uit.append("proefopname al gedaan")
        return uit
    import tempfile
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="e3-setup-"))
    wav = tmp / "proef.wav"
    zin = ("Dit is een proefopname van de setup van Equals Three. We meten hoe snel deze laptop een gesprek uitschrijft. "
           "Afspraak: vrijdag om tien uur met de boekhouder, bod van een komma twee miljoen euro. ") * 2
    ps(f"Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
       f"$s.SetOutputToWaveFile('{wav}'); $s.Speak('{zin}'); $s.Dispose()", timeout=120)
    if not wav.exists():
        bewaar_staat(ini, {"proefopname": {"ok": False, "detail": "Windows-spraak kon geen proefbestand maken"}}, False)
        return uit + ["proefopname mislukt: geen proefbestand"]
    env = dict(os.environ, E3_TRANSCRIPTS_DIR=str(tmp / "uit"))
    t0 = time.time()
    r = subprocess.run([sys.executable, str(sk / "scripts" / "transcribe.py"), str(wav), "--lang", "nl", "--out", str(tmp / "uit")],
                       env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3600)
    duur = time.time() - t0
    txt = list((tmp / "uit").rglob("*transcript*.txt"))
    ok = r.returncode == 0 and bool(txt) and txt[0].stat().st_size > 20
    if ok:
        detail = f"{duur:.0f} s voor ongeveer 30 s audio"
    else:
        regels = [x.strip() for x in (r.stderr or r.stdout or "").splitlines() if x.strip()]
        echt = [x for x in regels if not re.match(r"(\w*Warning\b|warnings\.warn|Downloading|Fetching)", x)]
        fout = (echt or regels)[-1:] or ["onbekend"]
        laag = " ".join(regels).lower()
        dll = "dll" in fout[0].lower()
        tip = (" (Visual C++-runtime ontbreekt: doe A0)" if not vcredist() else " (Smart App Control? klik Toestaan en herstart)") if dll else ""
        if not tip and ("huggingface" in laag or "hf hub" in laag or "snapshot" in laag or "connection" in laag):
            tip = " (het spraakmodel kwam niet volledig binnen: opnieuw proberen op een stabiele verbinding)"
        detail = "mislukt: " + fout[0][:160] + tip
    bewaar_staat(ini, {"proefopname": {"ok": ok, "detail": detail, "datum": NU.date().isoformat()}}, False)
    shutil.rmtree(tmp, ignore_errors=True)
    return uit + [f"proefopname {detail}"]


def a_e3crm(m, ini, p, st, droog):
    if not p.get("mail") or adres_fout(m, p["mail"]):
        return ["eerst A1: geen geldig werkadres"]
    uit = []
    bron = pad(m, "e3crm_toegang") if m["paden"].get("e3crm_toegang") else None
    gedeeld = bron is not None and bron.is_file()
    if not gedeeld and not all(e3crm_toegang()):
        return ["geen E3CRM-toegang op deze laptop en geen gedeelde toegang op de drive: stap voor de beheerder"]
    eigen = (lees_json(E3CRM_CFG, {}) or {}).get("eigen")
    if gedeeld and not os.environ.get("E3CRM_TOKEN") and not eigen:   # een eigen sleutel (A10) nooit overschrijven
        # Kopie ontbreekt of is verouderd (token geroteerd): stil overnemen, de inhoud nooit tonen.
        verschilt = not E3CRM_CFG.exists() or E3CRM_CFG.read_bytes() != bron.read_bytes()
        if verschilt and droog:
            uit.append("zou de E3CRM-toegang van de gedeelde drive overnemen in ~/.claude/e3crm.json (zonder ze te tonen)")
        elif verschilt:
            E3CRM_CFG.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(bron, E3CRM_CFG)
            uit.append("E3CRM-toegang overgenomen in ~/.claude/e3crm.json")
    if droog and not all(e3crm_toegang()):
        zoek = dic(st.get("account")).get("arx_mail") or p.get("arx_mail") or p["mail"]
        return uit + [f"zou team.zet sturen: persoon met {zoek}, initialen {ini}, werkadres {p['mail']} vooraan"]
    # Bestaande adressen bewaren; het werkadres van de eigen mailbox vooraan (daar gaat de E3 Daily-mail heen).
    bestaand = []
    try:
        lijst = e3crm({"actie": "team.lijst"})
        if lijst.get("bron") == "e3crm":
            eigen = next((x for x in lijst.get("team", []) if x.get("initialen") == ini), None)
            bestaand = [a.lower() for a in (eigen or {}).get("werkadres") or []]
    except E3crmFout:
        pass
    werkadres = [p["mail"].lower()] + [a for a in bestaand if a != p["mail"].lower()]
    zoek = dic(st.get("account")).get("arx_mail") or p.get("arx_mail") or p["mail"]
    body = {"actie": "team.zet", "adres": zoek, "initialen": ini, "werkadres": werkadres, "door": ini}
    if droog:
        return uit + [f"zou team.zet sturen: persoon met {zoek}, initialen {ini}, werkadres {'; '.join(werkadres)}"]
    try:
        r = e3crm(body)
    except E3crmFout as e:
        return uit + [f"team.zet mislukt: {wie_lost_op(str(e))}"]
    return uit + [f"fiche {r.get('id')} ({r.get('naam')}): initialen {r.get('initialen')}, werkadres "
                  f"{', '.join(r.get('werkadres') or [])}" + ("" if r.get("gewijzigd") else ", was al zo")]


def a_whatsapp(m, ini, p, st, droog):
    """Playwright installeren en de lezer koppelen. 'koppel' wacht tot tien minuten op de scan en daarna op de lijst:
    Claude draait deze stap in de achtergrond en toont de regel 'QR: http://127.0.0.1:...' in het browserpaneel."""
    sk = whatsapp_skill()
    if not sk:
        return ["whatsapp-skill ontbreekt: eerst A3"]
    lezer = sk / "scripts" / "wa_lezer.py"
    if droog:
        return ["zou Playwright installeren als het ontbreekt (pip, met de geïnstalleerde Chrome, geen extra browser)",
                f"zou {lezer.name} status draaien en, als er nog geen koppeling is, {lezer.name} koppel --ini {ini} "
                "(QR-code als lokale pagina)"]
    uit = []
    if not heeft_playwright():
        r = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "playwright"])
        uit.append(f"Playwright installeren: {'ok' if r.returncode == 0 else 'fout ' + str(r.returncode)}")
    if not browser():
        return uit + ["geen Chrome: installeer Google Chrome en start deze stap opnieuw"]

    def meet():
        r = subprocess.run([sys.executable, str(lezer), "status"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=300)
        try:
            return json.loads(r.stdout.strip().splitlines()[-1])
        except Exception:
            return {"stand": "fout", "lijst": False}

    s = meet()
    if s.get("stand") == "qr":
        print("Koppelen: de QR-code verschijnt zo als lokale pagina.", flush=True)
        r = subprocess.run([sys.executable, str(lezer), "koppel", "--ini", ini], timeout=1800)
        uit.append(f"koppelen: {'ok' if r.returncode == 0 else 'fout ' + str(r.returncode)}")
        s = meet()
    ok = s.get("stand") == "chats" and s.get("lijst")
    detail = ("gekoppeld, lijst Equals Three aanwezig" if ok else
              "gekoppeld, lijst Equals Three nog niet binnen" if s.get("stand") == "chats" else
              f"niet gekoppeld ({s.get('stand')})")
    bewaar_staat(ini, {"whatsapp": {"ok": bool(ok), "detail": detail, "datum": NU.date().isoformat()}}, False)
    return uit + [detail]


WA_STARTER = '''"""Starter van de WhatsApp-sweep (gemaakt door de setup-wizard, stap W2). Zoekt bij elke run de nieuwste
geïnstalleerde whatsapp-skill, zodat de geplande taak een update van de plugin overleeft."""
import glob, os, re, runpy, sys
kand = sorted(glob.glob({cache!r}), key=lambda x: [int(n) for n in re.findall(r"\\d+", os.path.basename(os.path.dirname(os.path.dirname(x))))])
skill = kand[-1] if kand else {dev!r}
lezer = os.path.join(skill, "scripts", "wa_lezer.py")
sys.argv = [lezer, "sweep", "--ini", {ini!r}]
sys.path.insert(0, os.path.dirname(lezer))
runpy.run_path(lezer, run_name="__main__")
'''


def wa_taak_ps(ini, pythonw, starter):
    """PowerShell die de Windows-taak maakt: werkdagen elk uur 8u10-20u10, verborgen, enkel aangemeld, één tegelijk."""
    q = lambda s: str(s).replace("'", "''")
    return (f"$a = New-ScheduledTaskAction -Execute '{q(pythonw)}' -Argument '-I \"{q(starter)}\"'; "
            "$t = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 08:10; "
            "$t.Repetition = (New-ScheduledTaskTrigger -Once -At 08:10 -RepetitionInterval (New-TimeSpan -Hours 1) "
            "-RepetitionDuration (New-TimeSpan -Hours 12 -Minutes 1)).Repetition; "
            "$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable "
            "-ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew -Hidden; "
            "$p = New-ScheduledTaskPrincipal -UserId \"$env:USERDOMAIN\\$env:USERNAME\" -LogonType Interactive -RunLevel Limited; "
            f"Register-ScheduledTask -TaskName 'E3 WhatsApp-sweep {q(ini)}' -Action $a -Trigger $t -Settings $s -Principal $p -Force "
            "-Description 'Equals Three: leest de chats in de WhatsApp-lijst Equals Three en zet nieuwe berichten in de Dossync-inbox. "
            "Zonder model, lage prioriteit.' | Out-Null; "
            f"(Get-ScheduledTaskInfo -TaskName 'E3 WhatsApp-sweep {q(ini)}').NextRunTime.ToString('dd/MM HH:mm')")


def a_whatsapp_sweep(m, ini, p, st, droog):
    """Starter in %LOCALAPPDATA%\\E3 schrijven en de Windows-taak maken. Bij een flow in proef enkel voorbereiden,
    tenzij --inplannen (de tester)."""
    if not dic(st.get("whatsapp")).get("ok"):
        return ["lezer nog niet gekoppeld of lijst Equals Three ontbreekt: eerst W1"]
    sk = whatsapp_skill()
    if not sk:
        return ["whatsapp-skill ontbreekt: eerst A3"]
    pythonw = pathlib.Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.exists():
        return [f"pythonw.exe niet gevonden naast {sys.executable}"]
    starter = pathlib.Path(os.environ["LOCALAPPDATA"]) / "E3" / "whatsapp-sweep.py"
    cmd = wa_taak_ps(ini, pythonw, starter)
    v, _ = vrijgave(m, {"flow": "07"})
    plannen = v == "vrij" or INPLANNEN
    if droog:
        return [f"zou {starter} schrijven (zoekt bij elke run de nieuwste skill, nu {sk})",
                f"zou de taak 'E3 WhatsApp-sweep {ini}' {'inplannen' if plannen else 'voorbereiden, niet inplannen (flow in proef)'}"]
    starter.parent.mkdir(parents=True, exist_ok=True)
    starter.write_text(WA_STARTER.format(cache=WA_CACHE, dev=str(WA_DEV), ini=ini),
                       encoding="utf-8")
    uit = [f"starter geschreven: {starter}"]
    if not plannen:
        return uit + ["flow 07 staat in proef: taak niet ingepland. Inplannen met: wizard.py doe W2 --inplannen", cmd]
    r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=60)
    ok = r.returncode == 0
    detail = (f"Windows-taak 'E3 WhatsApp-sweep {ini}', werkdagen 8u10-20u10 elk uur; volgende run {r.stdout.strip()}"
              if ok else f"taak maken mislukt: {(r.stderr or r.stdout).strip()[:200]}")
    taken = dictdic(st.get("taak"))
    taken["whatsapp"] = {"ok": ok, "detail": detail, "datum": NU.date().isoformat()}
    bewaar_staat(ini, {"taak": taken}, False)
    return uit + [detail]


INPLANNEN = False

ACTIES = {"A0": a_programmas, "A14": a_mappen, "A9": a_teaminstructies, "A7": a_e3crm, "A10": a_sleutel, "A11": a_sleutel_cloud, "A2": a_laptop, "A3": a_plugins, "A5": a_rechten, "A6": a_profiel, "R1": a_transcript,
          "W1": a_whatsapp, "W2": a_whatsapp_sweep}


def doe(m, ini, stap_id, droog):
    st = staat(ini)
    p = persoon(m, ini, st)
    stap = next((s for s in m["stappen"] if s["id"] == stap_id), None)
    if not stap:
        return {"stap": stap_id, "uit": ["onbekende stap"]}
    v, reden = vrijgave(m, stap)
    if v == "dicht":
        return {"stap": stap_id, "uit": [f"flow dicht: {reden}"]}
    if stap["soort"] == "pc":
        try:
            ok, detail = PC[stap["controle"]](m, ini, p, st)
        except Exception:
            ok, detail = False, ""
        if ok:
            return {"stap": stap_id, "uit": [f"klopt al, overgeslagen: {detail}"]}
    if stap_id not in ACTIES:
        return {"stap": stap_id, "uit": [f"geen automatische actie; {stap['soort']}-stap: zie SKILL.md"]}
    return {"stap": stap_id, "droog": droog, "uit": ACTIES[stap_id](m, ini, p, st, droog)}


def adres_fout(m, mail):
    """Geeft de reden waarom een adres niet mag, of None."""
    mail = (mail or "").strip().lower()
    if not mail.endswith("@" + m["domein"]):
        return f"{mail or 'geen adres'} is geen werkadres op @{m['domein']}"
    if mail in m["geweigerd"]:
        return f"{mail} is geen persoonlijk werkadres (gedeeld of namens iemand anders)"
    return None


def lees_waarde(delen):
    """JSON, of sleutel=waarde-paren (werkt in elke shell: Windows PowerShell 5.1 haalt de aanhalingstekens uit JSON-argumenten)."""
    if len(delen) == 1:
        try:
            return json.loads(delen[0]), None
        except json.JSONDecodeError:
            if delen[0].lstrip().startswith("{"):
                return None, ("ongeldige JSON (PowerShell haalt de aanhalingstekens weg). Gebruik sleutel=waarde, "
                              "bv. noteer account ok=true mail=naam@equalsthree.be \"detail=Gmail bevestigd\"")
            if "=" not in delen[0]:
                return delen[0], None
    if all("=" in d for d in delen):
        uit = {}
        for d in delen:
            k, v = d.split("=", 1)
            uit[k.strip()] = {"true": True, "false": False, "null": None}.get(v.strip().lower(), v)
        return uit, None
    return " ".join(delen), None


def noteer(m, ini, sleutel, waarde, droog):
    w, fout = lees_waarde(waarde if isinstance(waarde, list) else [waarde])
    if fout:
        return f"niet genoteerd: {fout}"
    if sleutel == "account" and isinstance(w, dict):
        if not w.get("mail") and m["personen"].get(ini, {}).get("mail"):
            w["mail"] = m["personen"][ini]["mail"]
        fout = adres_fout(m, w.get("mail"))
        if fout:
            return f"geweigerd: {fout}. Gebruik je eigen werkadres op @{m['domein']}."
    if sleutel.startswith("connector.") and isinstance(w, dict) and w.get("ok"):
        fout = adres_fout(m, w.get("adres"))
        eigen = dic(staat(ini).get("account")).get("mail")
        if fout or (eigen and (w.get("adres") or "").lower() != eigen.lower()):
            w["ok"] = False
            w["detail"] = fout or f"hangt aan {w.get('adres')}, niet aan {eigen}"
    if sleutel == "claude_code" and isinstance(w, dict) and w.get("ok"):
        eigen = dic(staat(ini).get("account")).get("mail")
        fout = adres_fout(m, w.get("adres"))
        if not fout and eigen and (w.get("adres") or "").lower() != eigen.lower():
            fout = f"aangemeld als {w.get('adres')}, niet als {eigen}"
        if not fout and "team" not in str(w.get("plan") or "").lower():
            fout = f"geen Team-plan van Equals Three (plan: {w.get('plan') or 'onbekend'})"
        if not fout and w.get("routines") is not True:
            fout = "cloudtaken (routines) kunnen niet aangemaakt worden met deze zetel"
        if fout:
            w["ok"], w["detail"] = False, fout
    if isinstance(w, dict):
        w.setdefault("tijd", NU.isoformat(timespec="minutes"))
    st = staat(ini)
    deel = {}
    if "." in sleutel:
        hoofd, sub = sleutel.split(".", 1)
        d = dict(st.get(hoofd, {}))
        d[sub] = w
        deel[hoofd] = d
    else:
        deel[sleutel] = w
    return bewaar_staat(ini, deel, droog)


def wacht(m, ini, tekst, minuten):
    inbox = pad(m, "inbox")
    if not inbox:
        return {"gevonden": None, "detail": "inbox niet zichtbaar"}
    einde = time.time() + minuten * 60
    start = time.time() - 15 * 60
    patroon = tekst.lower()
    while True:
        for f in inbox.rglob("*"):
            try:
                if f.is_file() and patroon in f.name.lower() and f.stat().st_mtime >= start:
                    return {"gevonden": str(f), "grootte": f.stat().st_size,
                            "tijd": dt.datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds")}
            except OSError:
                continue
        if time.time() > einde:
            return {"gevonden": None, "detail": f"na {minuten} minuten niets met '{tekst}' in de inbox"}
        time.sleep(20)


def opruimen(m, ini, droog):
    inbox, doel = pad(m, "inbox"), pad(m, "verwerkt_test")
    if not inbox:
        return ["inbox niet zichtbaar"]
    uit = []
    for f in inbox.rglob("*"):
        if f.is_file() and re.search(rf"\bTEST\b.*\b{re.escape(ini)}\b", f.name):
            if droog:
                uit.append(f"zou verplaatsen naar _verwerkt/setup-test: {f.name}")
            else:
                doel.mkdir(parents=True, exist_ok=True)
                shutil.move(str(f), str(doel / f.name))
                uit.append(f"verplaatst: {f.name}")
    return uit or ["geen testbestanden"]


# ---------- rapport ----------

TEKEN = {"ok": "✓", "fout": "✗", "open": "…", "vraag": "?", "nvt": "–", "dicht": "⏸", "klaar-te-zetten": "⏸", "op-laptop": "○"}
WOORD = {"ok": "werkt", "fout": "werkt niet", "open": "nog niet nagekeken", "vraag": "eerst een vraag",
         "nvt": "niet van toepassing", "dicht": "nog niet vrijgegeven", "klaar-te-zetten": "voorbereid, nog in proef",
         "op-laptop": "na te kijken op de laptop"}


WIE = {"beheerder": "de beheerder", "tools@": "tools@", "jij": "jij", "wizard": "de wizard"}


def linkjes(s):
    return re.sub(r"https?://\S+?(?=[,;]?(\s|$))", lambda u: f"<a href='{u.group(0)}'>deze link</a>", html.escape(s))


def label(r):
    return f"{r['id']} {r['naam']}" if r["id"].isdigit() else r["naam"]


def flowstand(m, c):
    per = {x["id"]: x for x in c["punten"]}
    st = staat(c["ini"])
    rijen = []
    for f in m["flows"]:
        pts = [per[s] for s in f["stappen"] if s in per]
        stats = [x["status"] for x in pts]
        if f["vrijgave"] == "dicht":
            s = "dicht"
        elif stats and all(x == "nvt" for x in stats):
            s = "nvt"
        elif "fout" in stats:
            s = "fout"
        elif any(x in ("open", "vraag") for x in stats):
            s = "open" if "open" in stats else "vraag"
        elif "op-laptop" in stats:
            s = "op-laptop"
        elif "klaar-te-zetten" in stats:
            s = "klaar-te-zetten"
        else:
            s = "ok"
        t = dic(st.get("test")).get(f["id"])
        test_uitslag = ("geslaagd" if t.get("ok") else "mislukt: " + (t.get("detail") or "")) if t else "nog niet gedraaid"
        if s == "ok" and t and not t.get("ok"):
            s = "fout"
        p = persoon(m, c["ini"], st)
        rijen.append({"id": f["id"], "naam": f["naam"], "status": s, "vrijgave": f["vrijgave"], "reden": f.get("reden", ""),
                      "test": vul(f["test"], m, c["ini"], p), "uitslag": test_uitslag,
                      "punten": [x for x in pts if x["status"] != "nvt"]})
    return rijen


def rapport(m, ini, droog, andere_pc, uit):
    c = controleer(m, ini, andere_pc)
    rijen = flowstand(m, c)
    p = c["persoon"]
    titel = f"Setup {ini}" + (" · droge run" if droog else "")
    md = [f"# {titel} · {NU:%d/%m/%Y %H:%M}", "",
          f"{p.get('naam') or ini}, {p.get('mail') or 'werkadres nog niet bekend'}. "
          + ("Droge run: er is niets gewijzigd. " if droog else "")
          + ("De laptopcontroles gelden voor een andere pc en zijn niet hier uitgevoerd." if andere_pc else ""), ""]
    if c["vragen"]:
        md += ["Eerst te vragen: " + ", ".join(c["vragen"]), ""]
    md += ["| Flow | Stand | Test | Wie lost op |", "|---|---|---|---|"]
    for r in rijen:
        wie = sorted({x["wie"] for x in r["punten"] if x["status"] in ("fout", "open")} - {"wizard"})
        md.append(f"| {label(r)} | {TEKEN[r['status']]} {WOORD[r['status']]} | {r['uitslag']} | {', '.join(wie) or '-'} |")
    vragen = {"toestel": "iPhone of Android?", "granola": "Neem je online meetings op met Granola?",
              "plaud": "Heb jij het Plaud-toestel?", "opnemen": "Neem je gesprekken aan tafel op met de laptop?",
              "whatsapp": "Wil je werkchats uit WhatsApp laten meelezen?"}
    zelf = [f"Vraag: {vragen.get(v, v)}" for v in c["vragen"]]
    for x in c["punten"]:
        if x["gebruiker"] and x["wie"] not in ("beheerder", "tools@") and x["status"] in ("fout", "open", "op-laptop", "vraag"):
            voorwaarde = "" if x["soort"] == "gebruiker" else " (enkel als de controle faalt)"
            zelf.append(f"{x['id']}: {x['gebruiker']}{voorwaarde}")
    if zelf:
        md += ["", f"## Wat {p.get('naam') or ini} zelf doet, één stap per keer", ""]
        md += [f"{i}. {s}" for i, s in enumerate(zelf, 1)]
    md += ["", "## Per stap", ""]
    for x in c["punten"]:
        if x["status"] == "nvt":
            continue
        md.append(f"- **{x['id']} {x['titel']}** {TEKEN[x['status']]} {x['detail']}")
        if x.get("aandacht"):
            md.append(f"  - aandachtspunt: {x['aandacht']}")
        if x["status"] in ("fout", "open", "op-laptop", "klaar-te-zetten", "vraag"):
            md.append(f"  - de wizard: {x['actie']}")
            if x["gebruiker"]:
                md.append(f"  - {WIE.get(x['wie'], x['wie'])}: {x['gebruiker']}")
    tekst = "\n".join(md) + "\n"
    kaarten = []
    for r in rijen:
        regels = "".join(f"<li><b>{html.escape(x['titel'])}</b> {TEKEN[x['status']]} {html.escape(x['detail'])}"
                         + (f"<div class=g>{WIE.get(x['wie'], x['wie']).capitalize() if x['wie'] != 'tools@' else 'tools@'}: {linkjes(x['gebruiker'])}</div>"
                            if x["gebruiker"] and x["status"] in ("fout", "open", "op-laptop", "vraag") else "")
                         + (f"<div class=g2>Aandachtspunt: {html.escape(x['aandacht'])}</div>" if x.get("aandacht") else "")
                         + "</li>" for x in r["punten"])
        kaarten.append(f"<section class='k {r['status']}'><h2><span>{TEKEN[r['status']]}</span>{html.escape(label(r))}</h2>"
                       f"<p class=s>{WOORD[r['status']]}" + (f" · {html.escape(r['reden'])}" if r['reden'] and r['status'] in ('dicht', 'klaar-te-zetten') else "")
                       + f"</p><ul>{regels}</ul><p class=t>Test: {html.escape(r['test'])}<br>Uitslag: {html.escape(r['uitslag'])}</p></section>")
    tel = {k: sum(1 for r in rijen if r["status"] == k) for k in TEKEN}
    pagina = f"""<!doctype html><html lang=nl><meta charset=utf-8><title>{html.escape(titel)}</title>
<style>body{{font:15px/1.45 'TWK Lausanne',Arial,sans-serif;margin:32px;color:#000;background:#fff;max-width:1100px}}
h1{{font-weight:400;font-size:26px;margin:0 0 4px}}.sub{{color:#555;margin:0 0 20px}}
.tel{{display:flex;gap:10px;margin:0 0 22px}}.tel div{{border:1px solid #000;padding:8px 14px}}.tel b{{font-size:22px;font-weight:400;display:block}}
main{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px}}
.k{{border:1px solid #000;padding:14px 16px}}.k h2{{font-size:17px;font-weight:600;margin:0}}.k h2 span{{display:inline-block;width:24px}}
.k.fout{{border-width:3px}}.k.dicht,.k.nvt,.k.klaar-te-zetten{{background:#f2f2f2;border-style:dashed}}
.s{{margin:2px 0 8px;color:#444}}ul{{padding-left:18px;margin:0}}li{{margin:4px 0}}.g{{margin-top:3px;padding:4px 8px;background:#000;color:#fff;overflow-wrap:anywhere}}.g a{{color:#fff}}.g2{{margin-top:3px;padding:4px 8px;border:1px solid #000}}
.t{{font-size:13px;color:#444;border-top:1px solid #ddd;padding-top:6px;margin-top:10px}}</style>
<h1>{html.escape(titel)}</h1><p class=sub>{html.escape(p.get('naam') or ini)} · {html.escape(p.get('mail') or '')} · {NU:%d/%m/%Y %H:%M}{' · niets gewijzigd' if droog else ''}</p>
<div class=tel><div><b>{tel['ok']}</b>werkt</div><div><b>{tel['fout']}</b>werkt niet</div><div><b>{tel['open'] + tel['vraag'] + tel['op-laptop']}</b>nog na te kijken</div><div><b>{tel['dicht'] + tel['klaar-te-zetten']}</b>nog niet vrijgegeven</div></div>
<main>{''.join(kaarten)}</main></html>"""
    if uit:
        doel = pathlib.Path(uit)
    elif droog:
        doel = None
    else:
        doel = STAAT_DIR / f"setup-rapport {NU:%y%m%d} {ini}"
    geschreven = []
    if doel is not None:
        doel.parent.mkdir(parents=True, exist_ok=True)
        doel.with_suffix(".md").write_text(tekst, encoding="utf-8")
        doel.with_suffix(".html").write_text(pagina, encoding="utf-8")
        geschreven = [str(doel.with_suffix(".md")), str(doel.with_suffix(".html"))]
        for g in geschreven:
            spiegel(g)
    return {"bestanden": geschreven, "flows": [{k: r[k] for k in ("id", "naam", "status", "uitslag")} for r in rijen],
            "tekst": tekst if doel is None else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["checklist", "controleer", "doe", "noteer", "wacht", "opruimen", "rapport", "sleutel"])
    ap.add_argument("arg", nargs="*")
    ap.add_argument("--ini")
    ap.add_argument("--droog", action="store_true")
    ap.add_argument("--andere-pc", action="store_true")
    ap.add_argument("--minuten", type=int, default=10)
    ap.add_argument("--uit")
    ap.add_argument("--geen-browser", action="store_true", help="checklist: de pagina niet zelf openen (tests)")
    ap.add_argument("--inplannen", action="store_true", help="W2: taak ook inplannen als flow 07 in proef staat (tester)")
    a = ap.parse_args()
    global INPLANNEN
    INPLANNEN = a.inplannen
    m = manifest()
    if a.cmd == "checklist":
        print(json.dumps(checklist(m, a.minuten if a.minuten != 10 else 30, not a.geen_browser), indent=1, ensure_ascii=False))
        return
    ini = (a.ini or (lees_json(PROFIEL, {}) or {}).get("initialen") or "").upper()
    if not ini:
        ap.error("geef --ini (je initialen) of vul eerst de checklist in")
    if a.cmd == "controleer":
        out = controleer(m, ini, a.andere_pc)
    elif a.cmd == "doe":
        out = doe(m, ini, a.arg[0], a.droog)
    elif a.cmd == "noteer":
        out = noteer(m, ini, a.arg[0], a.arg[1:], a.droog)
    elif a.cmd == "wacht":
        out = wacht(m, ini, a.arg[0], a.minuten)
    elif a.cmd == "opruimen":
        out = opruimen(m, ini, a.droog)
    elif a.cmd == "sleutel":
        out = zet_sleutel(ini)
    else:
        out = rapport(m, ini, a.droog, a.andere_pc, a.uit)
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
