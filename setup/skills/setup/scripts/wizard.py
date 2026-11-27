"""Setup-wizard voor een nieuwe collega op het AI-framework Finance van Equals Three.

Het script ziet de laptop; Claude ziet de connectors en de taken op claude.ai en noteert die hier.
Wat het moet aansluiten staat in ../flows.json, niet in dit script.

    python wizard.py checklist                                   eerste scherm: wie ben je en wat gebruik je (lokale pagina)
    python wizard.py controleer [--ini JDS] [--andere-pc]        stand per stap, JSON, schrijft niets
    python wizard.py doe STAP --ini JDS [--droog]                de automatische actie van een pc-stap
    python wizard.py doe R2|V1 --ini JDS --ja [--inplannen]      wachter of E3 run inplannen (dienstregeling), enkel na een ja
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
    p["plaud_ketting"] = ini in plaud_ketting(m)          # Plaud-token op elke laptop in de ketting (regels.json)
    if not p.get("dossync_uren"):
        bezet = {tuple(x["dossync_uren"]) for x in m["personen"].values() if x.get("dossync_uren")}
        p["dossync_uren"] = next((u for u in m["uren_nieuw"] if tuple(u) not in bezet), m["uren_nieuw"][-1])
    return p


def vul(tekst, m, ini, p, **extra):
    w = {"INI": ini, "mail": p.get("mail") or f"<werkadres van {ini}>",
         "webapp": m["webapp"] or "de webapp (de link staat in de config op E3 - Finance; eerst Google Drive voor desktop)",
         "beheerder": m["beheerder"], "uren": " en ".join(p.get("dossync_uren") or []),
         "connector": "de connector met een ✗", "ketting": ", ".join(plaud_ketting(m)) or "de ketting in Dossync › regels.json"}
    w.update(extra)
    return re.sub(r"\{(\w+)\}", lambda x: str(w.get(x.group(1), x.group(0))), tekst or "")


def geldt(stap, p):
    g = stap["geldt"]
    if g == "altijd":
        return True
    if g in ("granola", "plaud", "opnemen", "whatsapp"):
        return p.get(g)          # True, False of None (nog te vragen)
    if g == "plaud_ketting":     # P1: op elke laptop in de Plaud-ketting uit Dossync › regels.json
        return bool(p.get("plaud_ketting"))
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
    for d in (OPNAMEMAP.name, "Transcripts"):
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


# ---------- Dienstregeling (27/11, dossync 2.11, tools 2.27): de laptoptaken komen uit Dossync › dienstregeling.json ----------
# Doelbeeld › 04 Dienstregeling: alles wat op een klok loopt, staat in dienstregeling.json; de wizard plant er de
# laptoptaken uit in (naam en uren) en de gezondheidscontrole meet ertegen.
#   ritme 1  "E3 Dossync opnames wachter <INI>" (plan-opnames.ps1), één per laptop: opnames en pop-up in Documents\Opnames E3
#            (de Geluidsrecorder verhuist er vanzelf naartoe), de gsm-map (My Drive\E3Brain persoonlijk\import gsm), de
#            Plaud-toewijzing, elk uur de uurrun; hij houdt "E3 WhatsApp-live <INI>" en "E3 Later wachter" in leven en maakt
#            na het uitschrijven meteen de samenvatting met claude -p (Sonnet) op de eigen aanmelding.
#   ritme 2  "E3 run <INI>" (plan-verwerker.ps1) op werkdagen om 7u20 en 12u50: eerst Granola ophalen, dan de verwerker.
#   WhatsApp de live-lezer "E3 WhatsApp-live <INI>" bij het aanmelden (wa_live.py), niet meer de uurlijkse sweep.
# Alles gaat naar de lokale inbox Documents\E3 Inbox, nooit naar de gedeelde drive. Plaud: het token op elke laptop in de
# ketting uit Dossync › regels.json; de toewijzing zorgt dat niets dubbel binnenkomt. Elke laptoptaak laat een regel na in
# Dossync › gezondheid › <INI>.json (stap H1).

DIENST_MIN = {"tools": (2, 27), "dossync": (2, 11)}
OPNAMEMAP = HOME / "Documents" / "Opnames E3"
LOKALE_INBOX = pathlib.Path(os.environ.get("E3_LOKALE_INBOX") or HOME / "Documents" / "E3 Inbox")
DIENST_STANDAARD = {   # enkel als dienstregeling.json niet zichtbaar is (nog geen Drive)
    "wachter": {"naam": "E3 Dossync opnames wachter <INI>",
                "wanneer": "bij het aanmelden, elke 20 s; elk uur de uurrun (8u tot 21u); Plaud-lijst om de 5 min"},
    "run": {"naam": "E3 run <INI>", "wanneer": "07:20 en 12:50 op werkdagen"},
    "whatsapp-live": {"naam": "E3 WhatsApp-live <INI>",
                      "wanneer": "bij het aanmelden, bij elk nieuw bericht, vangnet elke minuut; items elk uur"},
}
OUDE_TAKEN = {"wachter": ["E3 Dossync opnames <INI>"], "run": ["E3 Dossync verwerker"], "whatsapp-live": ["E3 WhatsApp-sweep <INI>"]}
DIENST_STAP = {"wachter": "R2", "run": "V1", "whatsapp-live": "W2"}


def dienst(m, id_):
    """De taak uit dienstregeling.json (naam, wanneer, model, ...), aangevuld met de standaard."""
    q = pad(m, "dienstregeling") if m["paden"].get("dienstregeling") else None
    d = dic(lees_json(q, {}) if q else {})
    t = next((x for x in (d.get("taken") or []) if isinstance(x, dict) and x.get("id") == id_), None)
    return {**DIENST_STANDAARD.get(id_, {}), **(t or {})}


def taaknaam(m, id_, ini):
    return str(dienst(m, id_)["naam"]).replace("<INI>", ini)


def uren(m, id_):
    """De kloktijden uit 'wanneer' van de dienstregeling, bv. ['07:20', '12:50']."""
    return re.findall(r"\b\d{1,2}:\d{2}\b", str(dienst(m, id_).get("wanneer") or ""))


def taken_in_planner(namen):
    """{taaknaam: staat} van deze taken in Windows Taakplanner; een ontbrekende taak staat er niet in.
    E3_TAKEN (json) enkel voor tests."""
    ruw = os.environ.get("E3_TAKEN")
    if ruw is None:
        lijst = ", ".join("'" + n.replace("'", "''") + "'" for n in namen)
        ruw = ps(f"@(Get-ScheduledTask -TaskName {lijst} -ErrorAction SilentlyContinue | "
                 "ForEach-Object { [pscustomobject]@{n=$_.TaskName; s=[string]$_.State} }) | ConvertTo-Json -Compress")
    try:
        d = json.loads(ruw or "[]")
    except json.JSONDecodeError:
        return {}
    if isinstance(d, dict):
        d = d.get("value", [d]) if "n" not in d else [d]
    return {x["n"]: x.get("s") for x in d if isinstance(x, dict) and x.get("n") in namen}


def nakijk(id_):
    """Nakijken van een laptoptaak uit de dienstregeling: staat ze er, staat ze aan, en is de oude taak weg?"""
    def c(m, ini, p, st):
        naam = taaknaam(m, id_, ini)
        oud = [x.replace("<INI>", ini) for x in OUDE_TAKEN.get(id_, [])]
        taken = taken_in_planner([naam] + oud)
        if naam not in taken:
            return False, f"taak ontbreekt in Taakplanner: {naam}"
        if str(taken[naam]).lower() in ("disabled", "1"):
            return False, f"taak uitgeschakeld: {naam}"
        weg = [x for x in oud if x in taken]
        if weg:
            return False, (f"{naam} staat er ({taken[naam]}), maar de oude taak {', '.join(weg)} ook nog: "
                           f"doe {DIENST_STAP[id_]} opnieuw, dat ruimt ze op")
        return True, f"{naam} staat in Taakplanner ({taken[naam]})"
    return c


NAKIJKEN = {k: nakijk(k) for k in DIENST_STANDAARD}


def versie(naam):
    """Versie van een geïnstalleerde plugin als tuple, of None."""
    inst = geinstalleerd()
    k = next((k for k in inst if k.split("@")[0] == naam), None)
    nrs = re.findall(r"\d+", str(inst[k].get("version") or "")) if k else []
    return tuple(int(n) for n in nrs) or None


def te_oud(minimum):
    """['eerst A3: plugin tools 2.17.0, 2.27 of later nodig', ...] voor elke plugin onder het minimum."""
    uit = []
    for n, (a, b) in minimum.items():
        v = versie(n)
        if not v or v[:2] < (a, b):
            uit.append(f"eerst A3: plugin {n} {'.'.join(map(str, v)) if v else 'ontbreekt'}, {a}.{b} of later nodig")
    return uit


def dossync_scripts(skill):
    """Map scripts van een skill in de nieuwste geïnstalleerde dossync, of None."""
    kand = sorted(glob.glob(str(HOME / ".claude" / "plugins" / "cache" / "*" / "dossync" / "*" / "skills" / skill / "scripts")),
                  key=lambda x: [int(n) for n in re.findall(r"\d+", pathlib.Path(x).parents[2].name)])
    return pathlib.Path(kand[-1]) if kand else None


def claude_pad():
    """Zoals de taken van dossync: E3_CLAUDE, ~/.local/bin/claude.exe, dan het PATH."""
    for c in (os.environ.get("E3_CLAUDE"), str(HOME / ".local" / "bin" / "claude.exe"), shutil.which("claude")):
        if c and os.path.exists(c):
            return c
    return None


def claude_aanmelding():
    """(aangemeld, adres) van de claude-CLI die de laptoptaken gebruiken. E3_CLAUDE_STATUS (json) enkel voor tests."""
    ruw = os.environ.get("E3_CLAUDE_STATUS")
    if ruw is None:
        c = claude_pad()
        if not c:
            return None, None
        try:
            ruw = subprocess.run([c, "auth", "status"], capture_output=True, text=True, encoding="utf-8",
                                 errors="replace", timeout=30).stdout
        except Exception:
            return None, None
    try:
        s = json.loads(ruw)
    except json.JSONDecodeError:
        return None, None
    return bool(s.get("loggedIn")), s.get("email")


def claude_vereiste(p, waarvoor):
    """[] als claude -p op het werkadres aangemeld is, anders wat de gebruiker moet doen."""
    aan, adres = claude_aanmelding()
    mail = p.get("mail")
    if aan is None:
        return [f"claude-CLI niet gevonden: eerst A0 ({waarvoor} draait claude -p)"]
    if not aan or (mail and (adres or "").lower() != mail.lower()):
        return [f"claude -p is {'niet aangemeld' if not aan else 'aangemeld als ' + str(adres)}, niet op {mail} "
                f"({waarvoor} draait claude -p): GEBRUIKER: voer in een terminal 'claude auth login' uit en meld je aan met {mail}"]
    return []


def plaud_ketting(m):
    """De Plaud-ketting uit Dossync › regels.json, met de vrager vooraan (zoals toewijzing.py). [] zonder regels.json."""
    q = pad(m, "regels") if m["paden"].get("regels") else None
    d = dic(lees_json(q, {}) if q else {})
    k = [str(x).upper() for x in (dic(d.get("taak_opnemen")).get("ketting") or [])]
    v = str(dic(d.get("plaud")).get("vrager") or "").upper()
    if v and v in k:
        k = k[k.index(v):] + k[:k.index(v)]
    elif v:
        k = [v] + k
    return k


def plaud_connector():
    """Staat de Plaud-connector in ~/.claude.json, voor alle sessies of voor een project?"""
    d = lees_json(HOME / ".claude.json", {}) or {}
    if "plaud" in (d.get("mcpServers") or {}):
        return True
    return any("plaud" in (dic(v).get("mcpServers") or {}) for v in (d.get("projects") or {}).values())


def plaud_token():
    for n in ("tokens-mcp.json", "tokens.json"):
        f = HOME / ".plaud" / n
        if f.is_file():
            return f
    return None


def plaud_test(sc, token):
    """plaud.py test van dossync: 'Plaud-token werkt' of de reden. Het token zelf komt nooit in de uitvoer."""
    env = dict(os.environ, PLAUD_TOKENS=str(token))
    try:
        r = subprocess.run([sys.executable, "-I", str(sc / "plaud.py"), "test"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60, env=env)
    except Exception as e:
        return False, f"plaud.py test liep niet ({e.__class__.__name__})"
    regel = (r.stdout or r.stderr or "").strip().splitlines()[-1:] or ["geen uitvoer"]
    return r.returncode == 0 and "werkt" in regel[0], regel[0][:160]


def c_plaud(m, ini, p, st):
    sc = dossync_scripts("opvang")
    con, token = plaud_connector(), plaud_token()
    map_ = OPNAMEMAP.is_dir()
    delen = ["Plaud-connector aanwezig" if con else "Plaud-connector ontbreekt",
             "Documents\\Opnames E3 ok" if map_ else "Documents\\Opnames E3 ontbreekt"]
    if not sc or not (sc / "plaud.py").is_file():
        return False, "; ".join(delen + ["plaud.py niet gevonden (dossync 2.11 of later ontbreekt)"])
    if not token:
        return False, "; ".join(delen + ["nog niet aangemeld bij Plaud (geen token in %USERPROFILE%\\.plaud)"])
    ok, detail = plaud_test(sc, token)
    return con and map_ and ok, "; ".join(delen + [detail])


def dossync_map(m):
    q = pad(m, "inbox")
    return q.parent if q else None


def c_gezondheid(m, ini, p, st):
    """H1: Dossync › gezondheid › <INI>.json na de eerste wachterronde, en gezondheid.py controle --ini <INI>."""
    sc = dossync_scripts("dossync")
    g = sc / "gezondheid.py" if sc else None
    if not g or not g.is_file():
        return False, "gezondheid.py niet gevonden (dossync 2.11 of later ontbreekt)"
    root = dossync_map(m)
    if not root:
        return None, "Dossync niet zichtbaar (eerst A2)"
    d = dic(lees_json(root / "gezondheid" / f"{ini}.json", {}))
    if not d.get("wachter"):
        return None, f"nog geen wachterronde in Dossync › gezondheid › {ini}.json (binnen tien minuten na het inplannen van R2)"
    try:
        r = subprocess.run([sys.executable, "-I", str(g), "controle", "--ini", ini, "--json"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60, env=dict(os.environ, DOSSYNC_ROOT=str(root)))
        problemen = dic(json.loads((r.stdout or "").strip().splitlines()[-1])).get(ini) or []
    except Exception as e:
        return False, f"gezondheid.py controle liep niet ({e.__class__.__name__})"
    if problemen:
        return False, "; ".join(problemen)
    return True, "alles draaide: " + ", ".join(f"{k} {str(dic(v).get('laatst') or '')[5:16].replace('T', ' ')}" for k, v in d.items())


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
    # elke laptop heeft een wachter die uitschrijft (dienstregeling, ritme 1)
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
    uit.append(("My Drive › E3Brain persoonlijk › import gsm", my / "E3Brain persoonlijk" / "import gsm" if my else None, "diep"))
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
        elif not mag or (mag != "diep" and not q.parent.is_dir()):
            uit.append(f"{k} ontbreekt: stap voor de beheerder")
        elif droog:
            uit.append(f"zou aanmaken: {k}")
        else:
            q.mkdir(parents=mag == "diep", exist_ok=True)
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
    data = {"domein": m["domein"], "geweigerd": m["geweigerd"], "flows": flows, "plaud_ketting": plaud_ketting(m),
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
      "bijlagen": c_bijlagen, "transcript": c_transcript, "whatsapp": c_whatsapp, "publiek": c_publiek, "plaud": c_plaud, "gezondheid": c_gezondheid}


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
            verdwenen = False
            if s["soort"] != "pc":
                ok, detail = c_notitie(s, st)
                if ok is not False and s.get("nakijken") and not andere_pc:   # bv. R2 en V1: staan de taken er (nog)?
                    try:
                        ok2, detail2 = NAKIJKEN[s["nakijken"]](m, ini, p, st)
                    except Exception as e:
                        ok2, detail2 = False, f"nakijken faalde: {e}"
                    if ok:
                        ok, detail = ok2, detail2
                        verdwenen = not ok2   # ingepland maar nu weg: fout tonen, ook als de flow in proef staat
                    elif ok2:                 # al ingepland buiten de wizard om (met de hand of een vorige versie)
                        ok, detail = True, detail2 + "; al ingepland, niet door deze wizard"
            status = {True: "ok", False: "fout", None: "open"}[ok]
            if s["soort"] == "taak" and v == "proef" and status != "ok" and not verdwenen:
                status, detail = "klaar-te-zetten", (reden or "flow nog in proef").rstrip(".") + "; de taak wordt voorbereid, niet ingepland"
            punt.update(status=status, detail=detail)
        punten.append(punt)
    volgende = next((x for x in punten if x["status"] in ("fout", "open", "vraag")), None)
    return {"ini": ini, "config": m.get("config_gevonden"), "persoon": {k: p.get(k) for k in ("naam", "mail", "rol", "toestel", "granola", "plaud_ketting", "opnemen", "whatsapp", "dossync_uren", "eigenaar", "zetel")},
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
            "zou Documents\\Opnames E3 (de opnamemap) en Documents\\Transcripts aanmaken als ze ontbreken",
            "zou een proefopname van een halve minuut maken (Windows-spraak, geen microfoon) en lokaal uitschrijven in een tijdelijke map"]
    uit = []
    ok_sys = (HOME / ".claude" / "e3-transcript" / "systeem.md").exists()
    if not ok_sys:
        for c in stappen:
            r = subprocess.run(c)
            uit.append(f"{pathlib.Path(c[1]).name} {' '.join(c[2:])}: {'ok' if r.returncode == 0 else 'fout ' + str(r.returncode)}")
    for d in (OPNAMEMAP.name, "Transcripts"):
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


WA_LIVE_STARTER = '''"""Starter van WhatsApp-live (gemaakt door de setup-wizard, stap W2). Zoekt bij elke start de nieuwste
geïnstalleerde whatsapp-skill, zodat de taak een update van de plugin overleeft."""
import glob, os, re, runpy, sys
kand = sorted(glob.glob({cache!r}), key=lambda x: [int(n) for n in re.findall(r"\\d+", os.path.basename(os.path.dirname(os.path.dirname(x))))])
skill = kand[-1] if kand else {dev!r}
lezer = os.path.join(skill, "scripts", "wa_live.py")
sys.argv = [lezer, "live", "--ini", {ini!r}]
sys.path.insert(0, os.path.dirname(lezer))
runpy.run_path(lezer, run_name="__main__")
'''


def wa_live_ps(naam, oud, pythonw, starter):
    """PowerShell die 'E3 WhatsApp-live <INI>' maakt: bij het aanmelden, blijft draaien, herstart na een crash, verborgen,
    één tegelijk. Verwijdert de oude uurlijkse sweep en start de taak meteen."""
    q = lambda s: str(s).replace("'", "''")
    return (f"$a = New-ScheduledTaskAction -Execute '{q(pythonw)}' -Argument '-I \"{q(starter)}\"'; "
            "$t = New-ScheduledTaskTrigger -AtLogOn -User \"$env:USERDOMAIN\\$env:USERNAME\"; "
            "$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable "
            "-ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -RestartCount 999 "
            "-RestartInterval (New-TimeSpan -Minutes 1) -Hidden; "
            "$p = New-ScheduledTaskPrincipal -UserId \"$env:USERDOMAIN\\$env:USERNAME\" -LogonType Interactive -RunLevel Limited; "
            f"Register-ScheduledTask -TaskName '{q(naam)}' -Action $a -Trigger $t -Settings $s -Principal $p -Force "
            "-Description 'Equals Three: WhatsApp-live leest de chats in de lijst Equals Three uit het geheugen van WhatsApp Web, "
            "opent nooit een chat en zet items in de lokale inbox Documents\\E3 Inbox. Zonder model (dienstregeling, ritme 1).' | Out-Null; "
            f"if (Get-ScheduledTask -TaskName '{q(oud)}' -ErrorAction SilentlyContinue) {{ "
            f"Unregister-ScheduledTask -TaskName '{q(oud)}' -Confirm:$false; 'verwijderd: {q(oud)}' }}; "
            f"Start-ScheduledTask -TaskName '{q(naam)}'; '{q(naam)}: ' + [string](Get-ScheduledTask -TaskName '{q(naam)}').State")


def al_ingepland(ini, st, notitie, detail, droog):
    """De taak staat al in Taakplanner: niets inplannen. Ontbreekt de notitie (met de hand ingepland), dan noteren."""
    if not droog and not dic(dic(st.get("taak")).get(notitie)).get("ok"):
        taken = dict(dic(st.get("taak")))
        taken[notitie] = {"ok": True, "detail": detail + "; stond al in Taakplanner", "datum": NU.date().isoformat()}
        bewaar_staat(ini, {"taak": taken}, False)
    return [f"klopt al, overgeslagen: {detail}"]


def noteer_taak(ini, st, notitie, ok, detail):
    taken = dict(dic(st.get("taak")))
    taken[notitie] = {"ok": ok, "detail": detail, "datum": NU.date().isoformat()}
    bewaar_staat(ini, {"taak": taken}, False)


def a_whatsapp_live(m, ini, p, st, droog):
    """W2: de live-lezer als Windows-taak 'E3 WhatsApp-live <INI>' (bij het aanmelden, blijft draaien; de wachter houdt
    hem in leven). Vervangt de uurlijkse sweep. Bij een flow in proef enkel voorbereiden, tenzij --inplannen (de tester)."""
    naam = taaknaam(m, "whatsapp-live", ini)
    ok, detail = NAKIJKEN["whatsapp-live"](m, ini, p, st)
    if ok:
        return al_ingepland(ini, st, "whatsapp", detail, droog)
    if not dic(st.get("whatsapp")).get("ok"):
        return ["lezer nog niet gekoppeld of lijst Equals Three ontbreekt: eerst W1"]
    sk = whatsapp_skill()
    nodig = te_oud({"tools": DIENST_MIN["tools"]})
    if not sk or not (sk / "scripts" / "wa_live.py").is_file():
        nodig.append("wa_live.py niet gevonden: eerst A3 (tools 2.27 of later)")
    pythonw = pathlib.Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.exists():
        nodig.append(f"pythonw.exe niet gevonden naast {sys.executable}")
    starter = pathlib.Path(os.environ.get("LOCALAPPDATA") or HOME / "AppData" / "Local") / "E3" / "whatsapp-live.py"
    oud = OUDE_TAKEN["whatsapp-live"][0].replace("<INI>", ini)
    cmd = wa_live_ps(naam, oud, pythonw, starter)
    plannen = vrijgave(m, {"flow": "07"})[0] == "vrij" or INPLANNEN
    if droog:
        return [f"zou nakijken: {x}" for x in nodig] + [
            f"zou {starter} schrijven (zoekt bij elke start de nieuwste whatsapp-skill{', nu ' + str(sk) if sk else ''})",
            f"zou de taak '{naam}' ({dienst(m, 'whatsapp-live').get('wanneer')}) "
            f"{'inplannen' if plannen else 'voorbereiden, niet inplannen (flow in proef)'} en de oude '{oud}' verwijderen"]
    if nodig:
        return nodig
    starter.parent.mkdir(parents=True, exist_ok=True)
    starter.write_text(WA_LIVE_STARTER.format(cache=WA_CACHE, dev=str(WA_DEV), ini=ini), encoding="utf-8")
    uit = [f"starter geschreven: {starter}"]
    if not plannen:
        return uit + ["flow 07 staat in proef: taak niet ingepland. Inplannen met: wizard.py doe W2 --inplannen", cmd]
    r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=60)
    ok = r.returncode == 0 and naam in (r.stdout or "")
    detail = (f"Windows-taak '{naam}' bij het aanmelden, gestart" + ("; oude sweep verwijderd" if "verwijderd" in r.stdout else "")
              if ok else f"taak maken mislukt: {(r.stderr or r.stdout).strip()[:200]}")
    noteer_taak(ini, st, "whatsapp", ok, detail)
    return uit + [detail]


def a_plaud(m, ini, p, st, droog):
    """P1: op elke laptop in de Plaud-ketting (Dossync › regels.json). Connector voor alle sessies, Documents\\Opnames E3,
    en na de aanmelding plaud.py test. De aanmelding zelf doet Claude met de tool login van de connector; de persoon
    klikt Authorize in de browser. De toewijzing van dossync zorgt dat een opname nooit dubbel binnenkomt."""
    if not p.get("plaud_ketting"):
        k = plaud_ketting(m)
        return [f"{ini} staat niet in de Plaud-ketting (Dossync › regels.json: {', '.join(k) or 'niet zichtbaar'}): hier niets te doen"]
    sc = dossync_scripts("opvang")
    if not sc or not (sc / "plaud.py").is_file():
        return ["plaud.py ontbreekt: eerst A3 (dossync 2.11 of later)"]
    npx = shutil.which("npx")
    if droog:
        uit = [] if OPNAMEMAP.is_dir() else ["zou Documents\\Opnames E3 aanmaken (daarin haalt Plaud op)"]
        if not plaud_connector():
            uit.append("zou draaien: claude mcp add -s user plaud -- npx -y @plaud-ai/mcp@latest")
        uit.append("zou na de aanmelding (tool login van de connector) plaud.py test draaien" if not plaud_token()
                   else "zou plaud.py test draaien")
        return uit
    OPNAMEMAP.mkdir(parents=True, exist_ok=True)
    uit, nieuw = [], False
    if not plaud_connector():
        claude = claude_pad()
        if not claude:
            return uit + ["claude-CLI niet gevonden: voeg de connector toe met /mcp in Claude, naam plaud, commando npx -y @plaud-ai/mcp@latest"]
        if not npx:
            return uit + ["Node.js ontbreekt (npx): eerst A0"]
        r = subprocess.run([claude, "mcp", "add", "-s", "user", "plaud", "--", npx, "-y", "@plaud-ai/mcp@latest"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        if r.returncode:
            return uit + [f"Plaud-connector toevoegen mislukt: {(r.stderr or r.stdout).strip()[:200]}"]
        uit.append("Plaud-connector toegevoegd voor alle sessies")
        nieuw = True
    token = plaud_token()
    if not token:
        if nieuw:
            return uit + ["GEBRUIKER: start een nieuwe sessie in Claude Code (de connector laadt pas dan) en zeg 'verder met de setup'"]
        return uit + ["CLAUDE: roep de tool login van de Plaud-connector aan; de persoon meldt zich in de browser aan op het "
                      "gedeelde Plaud-account en klikt Authorize. Daarna doe P1 opnieuw."]
    ok, detail = plaud_test(sc, token)
    return uit + [detail if ok else f"{detail}: meld opnieuw aan met de tool login van de Plaud-connector"]


def ps_arg(v):
    if isinstance(v, (list, tuple)):
        return ",".join(ps_arg(x) for x in v)
    return "'" + str(v).replace("'", "''") + "'"


def plan_taak(m, ini, st, id_, notitie, nodig, ps1, args, wat, droog):
    """Gemeen deel van R2 en V1: vereisten, droog, proef, de vraag, en pas na --ja het PowerShell-script van dossync.
    Met -Command (niet -File), zodat een lijst als -Uren '07:20','12:50' als lijst aankomt."""
    naam = taaknaam(m, id_, ini)
    stap = DIENST_STAP[id_]
    oproep = f"& {ps_arg(ps1)}" + "".join(f" -{k} {ps_arg(v)}" for k, v in args)
    cmd = f'powershell -NoProfile -ExecutionPolicy Bypass -Command "{oproep}"'
    flow = next((s["flow"] for s in m["stappen"] if s["id"] == stap), "dienst")
    plannen = vrijgave(m, {"flow": flow})[0] == "vrij" or INPLANNEN
    if droog:
        return [f"zou nakijken: {x}" for x in nodig] + [
            f"zou na een ja {wat} {'inplannen' if plannen else 'voorbereiden, niet inplannen (flow in proef)'}", cmd]
    if nodig:
        return nodig
    if not plannen:
        return [f"flow {flow} staat in proef: niet ingepland. Inplannen met: wizard.py doe {stap} --inplannen --ja", cmd]
    if not JA:
        return [f"VRAAG: mag ik {wat} inplannen? Na ja: wizard.py doe {stap} --ja", cmd]
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", oproep],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    ok = r.returncode == 0 and (naam in (r.stdout or "") or NAKIJKEN[id_](m, ini, {}, st)[0])
    if ok:
        detail = f"ingepland: {naam}" + ("; " + "; ".join(x.strip() for x in r.stdout.splitlines() if x.startswith("verwijderd"))
                                          if "verwijderd" in (r.stdout or "") else "")
    elif r.returncode == 0:
        detail = f"taak ontbreekt na {pathlib.Path(ps1).name}: {naam}"
    else:
        detail = f"inplannen mislukt: {(r.stderr or r.stdout).strip()[:200]}"
    noteer_taak(ini, st, notitie, ok, detail)
    return [detail]


def a_opnames(m, ini, p, st, droog):
    """R2: de wachter (dienstregeling, ritme 1) via plan-opnames.ps1 -Ini <INI> -Sinds <vandaag>. Eerst de vereisten, dan
    pas na een ja van de gebruiker (--ja) inplannen. Bij een flow in proef enkel voorbereiden, tenzij --inplannen."""
    naam = taaknaam(m, "wachter", ini)
    ok, detail = NAKIJKEN["wachter"](m, ini, p, st)
    if ok:
        return al_ingepland(ini, st, "opnames", detail, droog)
    nodig = te_oud(DIENST_MIN)
    ok, detail = c_transcript(m, ini, p, st)
    if not ok:
        nodig.append(f"eerst R1: {detail}")
    nodig += claude_vereiste(p, "de samenvatting na het uitschrijven")
    sc = dossync_scripts("opvang")
    ps1 = sc / "plan-opnames.ps1" if sc else None
    if not ps1 or not ps1.is_file():
        nodig.append("plan-opnames.ps1 niet gevonden: eerst A3 (dossync 2.11 of later)")
    wat = (f"de wachter '{naam}' ({dienst(m, 'wachter').get('wanneer')}; en om 8u als vangnet): bij elke nieuwe opname "
           f"in Documents\\Opnames E3 van meer dan 10 s een pop-up (Transcriberen, Wacht op run of Negeer; na 15 s zonder "
           f"keuze Wacht op run), de gsm-map, Plaud en elk uur de uurrun; hij houdt WhatsApp-live en Later in leven en maakt "
           f"na het uitschrijven de samenvatting met claude -p; alles naar de lokale inbox Documents\\E3 Inbox, enkel als "
           f"de gebruiker aangemeld is. De oude uurtaak verdwijnt")
    return plan_taak(m, ini, st, "wachter", "opnames", nodig, ps1, [("Ini", ini), ("Sinds", NU.date().isoformat())], wat, droog)


def a_run(m, ini, p, st, droog):
    """V1 (en G1): 'E3 run <INI>' (dienstregeling, ritme 2) via plan-verwerker.ps1 -Ini <INI> -Uren <uit de
    dienstregeling>: eerst Granola ophalen, dan /dossync:verwerker. Draait claude -p: de CLI moet op het werkadres
    aangemeld zijn. Pas na een ja (--ja) inplannen."""
    naam = taaknaam(m, "run", ini)
    ok, detail = NAKIJKEN["run"](m, ini, p, st)
    if ok:
        return al_ingepland(ini, st, "run", detail, droog)
    nodig = te_oud({"dossync": DIENST_MIN["dossync"]})
    if not all(e3crm_toegang()):
        nodig.append("eerst A7: geen E3CRM-toegang op deze laptop (de verwerker leest E3CRM)")
    nodig += claude_vereiste(p, "E3 run (Granola en de verwerker)")
    sc = dossync_scripts("verwerker")
    ps1 = sc / "plan-verwerker.ps1" if sc else None
    if not ps1 or not ps1.is_file():
        nodig.append("plan-verwerker.ps1 niet gevonden: eerst A3 (dossync 2.11 of later)")
    u = uren(m, "run")
    wat = (f"de taak '{naam}' (op werkdagen om {' en '.join(u) or '07:20 en 12:50'}: eerst Granola ophalen, dan "
           f"/dossync:verwerker met claude -p op {p.get('mail')}; leest de lokale inbox Documents\\E3 Inbox en de gedeelde "
           f"inbox en zet enkel wat relevant is in E3 Daily; lokale transcripten en chats verlaten de laptop nooit letterlijk). "
           f"De oude taak 'E3 Dossync verwerker' verdwijnt")
    return plan_taak(m, ini, st, "run", "run", nodig, ps1, [("Ini", ini)] + ([("Uren", u)] if u else []), wat, droog)


INPLANNEN = False
JA = False

ACTIES = {"A0": a_programmas, "A14": a_mappen, "A9": a_teaminstructies, "A7": a_e3crm, "A10": a_sleutel, "A11": a_sleutel_cloud, "A2": a_laptop, "A3": a_plugins, "A5": a_rechten, "A6": a_profiel, "R1": a_transcript,
          "W1": a_whatsapp, "W2": a_whatsapp_live, "P1": a_plaud, "R2": a_opnames, "V1": a_run, "G1": a_run}


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


def inboxen(m):
    """De gedeelde inbox op de drive en de lokale inbox van deze laptop (opnames, WhatsApp-chats), met hun _verwerkt."""
    uit = []
    gedeeld = pad(m, "inbox")
    if gedeeld:
        uit.append((gedeeld, pad(m, "verwerkt_test")))
    uit.append((LOKALE_INBOX / "inbox", LOKALE_INBOX / "_verwerkt" / "setup-test"))
    return uit


def wacht(m, ini, tekst, minuten):
    bakken = [i for i, _ in inboxen(m)]
    einde = time.time() + minuten * 60
    start = time.time() - 15 * 60
    patroon = tekst.lower()
    while True:
        for f in (x for b in bakken if b.is_dir() for x in b.rglob("*")):
            try:
                if f.is_file() and patroon in f.name.lower() and f.stat().st_mtime >= start:
                    return {"gevonden": str(f), "grootte": f.stat().st_size,
                            "tijd": dt.datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds")}
            except OSError:
                continue
        if time.time() > einde:
            return {"gevonden": None, "detail": f"na {minuten} minuten niets met '{tekst}' in de inbox of de lokale inbox"}
        time.sleep(20)


def opruimen(m, ini, droog):
    """Testbestanden van INI naar _verwerkt/setup-test naast de inbox waar ze stonden (gedeeld of lokaal)."""
    uit = []
    for inbox, doel in inboxen(m):
        if not inbox.is_dir():
            continue
        for f in list(inbox.rglob("*")):
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
              "opnemen": "Neem je gesprekken aan tafel op met de laptop?",
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
    ap.add_argument("--inplannen", action="store_true", help="W2, R2, V1: taak ook inplannen als de flow in proef staat (tester)")
    ap.add_argument("--ja", action="store_true", help="R2, V1: de gebruiker zei ja op het inplannen")
    a = ap.parse_args()
    global INPLANNEN, JA
    INPLANNEN, JA = a.inplannen, a.ja
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
