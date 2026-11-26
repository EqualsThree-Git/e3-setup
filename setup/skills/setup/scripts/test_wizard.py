"""Tests voor wizard.py op een nagebootste laptop en drive in een tijdelijke map. Raakt niets echts aan.

    python test_wizard.py
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
WIZ = HERE / "wizard.py"
fouten = 0


def check(naam, voorwaarde, extra=""):
    global fouten
    print(("ok   " if voorwaarde else "FOUT ") + naam + (f"  ({extra})" if extra and not voorwaarde else ""))
    fouten += 0 if voorwaarde else 1


CONFIG = {
    "geweigerd": ["tools@equalsthree.be", "jan.detest@equalsthree.be"],
    "beheerder": "de beheerder van de gedeelde drive E3 - Finance (tools@equalsthree.be)",
    "webapp": "https://script.google.com/macros/s/TEST/exec",
    "webapp_gebruikers": ["rik@equalsthree.be", "sam@equalsthree.be", "jan@equalsthree.be"],
    "personen": {
        "RP": {"naam": "Rik Proef", "mail": "rik@equalsthree.be", "toestel": "Android", "granola": True, "plaud": False, "opnemen": True, "dossync_uren": ["09:55", "14:55"]},
        "SVL": {"naam": "Sam Voorbeeld", "mail": "sam@equalsthree.be", "toestel": "iPhone", "granola": True, "plaud": False, "opnemen": None, "dossync_uren": ["10:15", "15:15"]},
        "JDS": {"naam": "Jan De Test", "mail": "jan@equalsthree.be", "toestel": "iPhone", "granola": True, "plaud": True, "opnemen": None,
                "dossync_uren": ["10:35", "15:35"], "arx_mail": "jan.detest@equalsthree.be", "eigenaar": True, "zetel": "Standard"}},
    "uren_nieuw": [["10:55", "15:55"], ["11:15", "16:15"], ["11:35", "16:35"]],
}


def opzet():
    t = pathlib.Path(tempfile.mkdtemp(prefix="e3-setup-test-"))
    root, home = t / "drive", t / "home"
    for d in ("My Drive/Dossier-sync", "My Drive/_Uit mail", "Shared drives/E3 - Finance/Dossync/inbox/ruw",
              "Shared drives/E3 - Finance/Dossync/opvang",
              "Shared drives/E3 - Finance/Framework", "Shared drives/1. Equals Three - Clients"):
        (root / d).mkdir(parents=True)
    (home / ".claude" / "plugins").mkdir(parents=True)
    (home / ".claude" / "plugins" / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {
        "setup@e3-setup": [{"version": "1.0.0"}], "tools@e3-shared": [{"version": "2.17.0"}], "deliverables@e3-shared": [{"version": "2.6.2"}],
        "dossync@e3-dossync": [{"version": "1.4.0"}]}}), encoding="utf-8")
    cfg = root / "Shared drives/E3 - Finance/Framework/10 Flows/setup-config.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(json.dumps(CONFIG), encoding="utf-8")
    env = dict(os.environ, E3_TEST_SNEL="1", E3_DRIVE_ROOT=str(root), E3_HOME=str(home), E3_SETUP_DIR=str(home / ".claude" / "e3-setup"))
    return t, env


def w(env, *args):
    r = subprocess.run([sys.executable, str(WIZ), *args], capture_output=True, text=True, encoding="utf-8", env=env)
    if r.returncode:
        print(r.stderr)
    return json.loads(r.stdout)


def foto(t):
    return {str(p.relative_to(t)): (p.stat().st_size, p.stat().st_mtime) for p in t.rglob("*")}


def punt(c, id_):
    return next(x for x in c["punten"] if x["id"] == id_)



# ---------- nagebootste E3CRM (opvraagfunctie team.lijst / team.zet) ----------
import http.server
import threading

TOKEN = "geheim-token-123"
CRM = {"personen": [{"id": "P-000001", "voornaam": "Jan", "achternaam": "De Test", "mail": "jan.detest@equalsthree.be",
                     "initialen": None, "werkadres": []}], "zet": []}


class Crm(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if b.get("token") != TOKEN:
            out = {"ok": False, "fout": "token ongeldig"}
        elif b["actie"] == "team.lijst":
            team = [dict(x, werkadres=x["werkadres"]) for x in CRM["personen"] if x["initialen"]]
            out = {"ok": True, "data": {"bron": "e3crm" if team else "terugval", "team": team}}
        elif b["actie"] == "team.zet":
            CRM["zet"].append(b)
            hit = next((x for x in CRM["personen"] if b.get("adres") in [x["mail"], *x["werkadres"]]), None)
            if not hit:
                out = {"ok": False, "fout": f"Geen persoon met {b.get('adres')} in E3CRM. Vraag de beheerder hem in E3CRM te zetten."}
            else:
                oud = (hit["initialen"], list(hit["werkadres"]))
                hit["initialen"] = b["initialen"]
                hit["werkadres"] = b["werkadres"] if isinstance(b["werkadres"], list) else [b["werkadres"]]
                out = {"ok": True, "data": {"id": hit["id"], "naam": "Jan De Test", "initialen": hit["initialen"],
                                            "werkadres": hit["werkadres"], "gewijzigd": oud != (hit["initialen"], hit["werkadres"])}}
        else:
            out = {"ok": False, "fout": "onbekende actie"}
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)


srv = http.server.HTTPServer(("127.0.0.1", 0), Crm)
threading.Thread(target=srv.serve_forever, daemon=True).start()
CRM_URL = f"http://127.0.0.1:{srv.server_port}/exec"

t, env = opzet()

# 1. Droog schrijft niets
voor = foto(t)
w(env, "doe", "A5", "--ini", "JDS", "--droog")
w(env, "doe", "A6", "--ini", "JDS", "--droog")
w(env, "noteer", "antwoord.toestel", '"iPhone"', "--ini", "JDS", "--droog")
r = w(env, "rapport", "--ini", "JDS", "--droog")
w(env, "opruimen", "--ini", "JDS", "--droog")
check("droge run schrijft niets", foto(t) == voor)
check("droge run geeft het rapport als tekst", r["bestanden"] == [] and "Setup JDS" in (r["tekst"] or ""))

# 2. Vrijgave en toepasbaarheid
c = w(env, "controleer", "--ini", "JDS")
check("Plaud is dicht", punt(c, "P1")["status"] == "dicht")
check("Granola-taak wordt voorbereid, niet ingepland", punt(c, "G1")["status"] == "klaar-te-zetten")
check("E3CRM-fiche is een laptopstap met eigen controle", punt(c, "A7")["soort"] == "pc")
check("Geluidsrecorder: eerst vragen of JDS opneemt", "opnemen" in c["vragen"] and punt(c, "R1")["status"] == "vraag")
check("eerste open stap is een basisstap", c["volgende"] in ("A0", "A12", "A1"), c["volgende"])

# 3. Herneembaar
a = w(env, "doe", "A6", "--ini", "JDS")
check("A6 schrijft het profiel", any("geschreven" in x for x in a["uit"]), a["uit"])
b = w(env, "doe", "A6", "--ini", "JDS")
check("A6 tweede keer overgeslagen", b["uit"][0].startswith("klopt al"), b["uit"])
w(env, "doe", "A5", "--ini", "JDS")
c = w(env, "controleer", "--ini", "JDS")
check("A5 schrijftest ok", punt(c, "A5")["status"] == "ok", punt(c, "A5")["detail"])
check("A5 tweede keer overgeslagen", w(env, "doe", "A5", "--ini", "JDS")["uit"][0].startswith("klopt al"))
check("geen testbestand achtergelaten", not list((t / "drive").rglob("_setup-test-*")))
prof = json.loads((t / "home/.claude/e3-shared.json").read_text(encoding="utf-8"))
check("profiel met werkadres en initialen", prof["mailbox"] == "jan@equalsthree.be" and prof["initialen"] == "JDS")
check("geen register op de drive", not (t / "drive/Shared drives/E3 - Finance/Dossync/deelnemers").exists())

# 4. Adressen
r = w(env, "noteer", "account", '{"ok":true,"mail":"tools@equalsthree.be"}', "--ini", "JDS")
check("tools@ geweigerd", r.startswith("geweigerd"))
r = w(env, "noteer", "account", '{"ok":true,"mail":"jan@gmail.com"}', "--ini", "JDS")
check("privéadres geweigerd", r.startswith("geweigerd"))
w(env, "noteer", "account", '{"ok":true,"mail":"jan@equalsthree.be","detail":"Arx"}', "--ini", "JDS")
w(env, "noteer", "connector.calendar", '{"ok":true,"adres":"rik@equalsthree.be"}', "--ini", "JDS")
c = w(env, "controleer", "--ini", "JDS")
check("connector op andermans adres = fout", punt(c, "A4")["status"] == "fout", punt(c, "A4")["detail"])

# 5. Webapp: nieuw adres buiten de gebruikerslijst, en een actieve status
c = w(env, "controleer", "--ini", "XYZ")
check("onbekende collega: werkadres eerst bevestigen", punt(c, "A1")["status"] == "open")
w(env, "noteer", "account", '{"ok":true,"mail":"nieuw@equalsthree.be"}', "--ini", "XYZ")
c = w(env, "controleer", "--ini", "XYZ")
check("nieuw adres niet in webapp-lijst = stap beheerder", punt(c, "M1")["status"] == "fout" and "beheerder" in punt(c, "M1")["detail"])
check("nieuw adres krijgt vrije uren", c["persoon"]["dossync_uren"] == ["10:55", "15:55"])
import datetime as dt
nu = dt.datetime.now().astimezone().isoformat()
(t / "drive/My Drive/Dossier-sync/dossync-status.json").write_text(json.dumps({"gebruiker": "JDS", "geschreven": nu}), encoding="utf-8")
(t / "drive/My Drive/_Uit mail/bijlagen.json").write_text(json.dumps({"laatsteRun": nu, "items": []}), encoding="utf-8")
c = w(env, "controleer", "--ini", "JDS")
check("webapp actief herkend", punt(c, "M1")["status"] == "ok", punt(c, "M1")["detail"])
check("bijlagen-inname herkend", punt(c, "B1")["status"] == "ok", punt(c, "B1")["detail"])

# 6. Testbestand vanaf de gsm en opruimen
(t / "drive/Shared drives/E3 - Finance/Dossync/inbox/TEST memo JDS.txt").write_text("TEST memo JDS", encoding="utf-8")
r = w(env, "wacht", "TEST memo JDS", "--ini", "JDS", "--minuten", "0")
check("testmemo gevonden", bool(r["gevonden"]))
r = w(env, "opruimen", "--ini", "JDS")
check("testmemo naar _verwerkt/setup-test", (t / "drive/Shared drives/E3 - Finance/Dossync/_verwerkt/setup-test/TEST memo JDS.txt").exists())

# 6b. Fiche in E3CRM (A7)
c = w(env, "controleer", "--ini", "JDS")
check("A7 zonder E3CRM-toegang = fout", punt(c, "A7")["status"] == "fout" and "toegang" in punt(c, "A7")["detail"])
r = w(env, "doe", "A7", "--ini", "JDS")
check("A7 zonder toegang en zonder gedeelde kopie = beheerder", "beheerder" in r["uit"][-1], r["uit"])
(t / "home/.claude/e3crm.json").write_text(json.dumps({"url": CRM_URL, "token": TOKEN}), encoding="utf-8")
c = w(env, "controleer", "--ini", "JDS")
check("A7 terugval = nog niet in het register", punt(c, "A7")["status"] == "fout" and "terugval" in punt(c, "A7")["detail"])
n = len(CRM["zet"])
r = w(env, "doe", "A7", "--ini", "JDS", "--droog")
check("A7 droog stuurt niets", len(CRM["zet"]) == n and r["uit"][-1].startswith("zou team.zet"))
r = w(env, "doe", "A7", "--ini", "JDS")
z = CRM["zet"][-1]
check("A7 zoekt op het andere adres en zet werkadres", z["adres"] == "jan.detest@equalsthree.be" and z["werkadres"] == ["jan@equalsthree.be"]
      and z["initialen"] == "JDS", z)
c = w(env, "controleer", "--ini", "JDS")
check("A7 ok na team.zet", punt(c, "A7")["status"] == "ok", punt(c, "A7")["detail"])
check("team.zet met door = eigen initialen", CRM["zet"][-1]["door"] == "JDS")
vw = t / "home/.claude/plugins/cache/e3-dossync/dossync/1.5.0/skills/verwerker/scripts"
vw.mkdir(parents=True)
(vw / "verwerker.py").write_text("def team():\n    return {'adres': {'jan@equalsthree.be': 'JDS'}}\n"
                                 "def wie_is(d, t):\n    return t['adres'].get(d)\n", encoding="utf-8")
c = w(env, "controleer", "--ini", "JDS")
check("verwerker herkent het werkadres", punt(c, "A7")["status"] == "ok" and "verwerker herkent" in punt(c, "A7")["detail"], punt(c, "A7")["detail"])
check("D2 is een stap voor tools@", punt(c, "D2")["wie"] == "tools@")
n = len(CRM["zet"])
r = w(env, "doe", "A7", "--ini", "JDS")
check("A7 tweede keer overgeslagen", r["uit"][0].startswith("klopt al") and len(CRM["zet"]) == n, r["uit"])
r = w(env, "doe", "A7", "--ini", "XYZ")
check("A7 onbekende persoon: eerst in E3CRM", "Geen persoon" in r["uit"][-1], r["uit"])
uitvoer = json.dumps([w(env, "controleer", "--ini", "JDS"), r])
check("token komt nooit in de uitvoer", TOKEN not in uitvoer)

# 6c. Gedeelde kopie van de toegang en rotatie
CRM["personen"][0]["werkadres"] = ["jan.detest@equalsthree.be", "jan@equalsthree.be"]
gedeeld = t / "drive/Shared drives/E3 - Finance/E3CRM/_toegang/e3crm.json"
gedeeld.parent.mkdir(parents=True)
TOKEN = "nieuw-token-456"
gedeeld.write_text(json.dumps({"url": CRM_URL, "token": TOKEN}), encoding="utf-8")
lokaal = t / "home/.claude/e3crm.json"
r = w(env, "doe", "A7", "--ini", "JDS", "--droog")
check("droog neemt de gedeelde toegang niet over", TOKEN not in lokaal.read_text(encoding="utf-8"))
r = w(env, "doe", "A7", "--ini", "JDS")
check("geroteerde toegang stil overgenomen", lokaal.read_bytes() == gedeeld.read_bytes() and "overgenomen" in r["uit"][0], r["uit"])
check("token ook na rotatie niet in de uitvoer", TOKEN not in json.dumps(r))
check("werkadres van de mailbox vooraan, ander adres bewaard",
      CRM["zet"][-1]["werkadres"] == ["jan@equalsthree.be", "jan.detest@equalsthree.be"], CRM["zet"][-1]["werkadres"])
lokaal.unlink()
r = w(env, "doe", "A7", "--ini", "JDS")
check("ontbrekende toegang uit de gedeelde kopie", lokaal.exists() and "overgenomen" in r["uit"][0], r["uit"])

# 7. Andere pc en rapport
c = w(env, "controleer", "--ini", "JDS", "--andere-pc")
check("andere pc: laptopstappen niet hier uitgevoerd", punt(c, "A2")["status"] == "op-laptop")
r = w(env, "rapport", "--ini", "JDS")
md = pathlib.Path(r["bestanden"][0]).read_text(encoding="utf-8")
check("rapport heeft elke flow", all(f" {n} |" in md for n in ("Mail", "Agenda", "Granola", "Plaud", "Bijlagen", "E3 Daily", "Ochtendbriefing", "Maandelijkse retro")))
check("E3 Daily dicht in het rapport", next(f for f in r["flows"] if f["id"] == "daily")["status"] == "dicht")
check("de oude naam dagvragen komt nergens meer voor", "dagvragen" not in md.lower() and "dagvragen" not in (HERE.parent / "flows.json").read_text(encoding="utf-8").lower())
check("flow retro dicht zolang E3CRM de acties niet kent", next(f for f in r["flows"] if f["id"] == "retro")["status"] == "dicht")

# 8. Claude Code (A8), teaminstructies (A9), plugins uit de marketplaces, cloudtaken per persoon
c = w(env, "controleer", "--ini", "JDS")
check("A8 nog niet nagekeken = open", punt(c, "A8")["status"] == "open" and punt(c, "A8")["soort"] == "claude")
r = w(env, "noteer", "claude_code", '{"ok":true,"adres":"jan@gmail.com","plan":"Team","routines":true}', "--ini", "JDS")
c = w(env, "controleer", "--ini", "JDS")
check("A8 met privéadres = fout", punt(c, "A8")["status"] == "fout" and "geen werkadres" in punt(c, "A8")["detail"], punt(c, "A8")["detail"])
w(env, "noteer", "claude_code", '{"ok":true,"adres":"jan@equalsthree.be","plan":"Pro","routines":true}', "--ini", "JDS")
c = w(env, "controleer", "--ini", "JDS")
check("A8 zonder Team-plan = fout", punt(c, "A8")["status"] == "fout" and "Team-plan" in punt(c, "A8")["detail"], punt(c, "A8")["detail"])
w(env, "noteer", "claude_code", '{"ok":true,"adres":"jan@equalsthree.be","plan":"Team","routines":false}', "--ini", "JDS")
c = w(env, "controleer", "--ini", "JDS")
check("A8 zonder cloudtaken = fout", punt(c, "A8")["status"] == "fout" and "cloudtaken" in punt(c, "A8")["detail"], punt(c, "A8")["detail"])
w(env, "noteer", "claude_code", '{"ok":true,"adres":"jan@equalsthree.be","plan":"Team","zetel":"Standard","routines":true}', "--ini", "JDS")
c = w(env, "controleer", "--ini", "JDS")
check("A8 ok op Team-plan, Standard-zetel", punt(c, "A8")["status"] == "ok", punt(c, "A8")["detail"])
check("Standard-zetel: aandachtspunt over de gebruikslimiet, geen blokkade", "gebruikslimiet" in punt(c, "A8").get("aandacht", ""))
check("aandachtspunt staat in het rapport", "aandachtspunt" in pathlib.Path(w(env, "rapport", "--ini", "JDS")["bestanden"][0]).read_text(encoding="utf-8"))

ti = t / "drive/Shared drives/E3 - Finance/Framework/01 Framework"
ti.mkdir(parents=True, exist_ok=True)
bron = ti / "Teaminstructies Claude.md"
bron.write_text("# Teaminstructies\n\nVersie 25/11/2026. Plak alles onder de lijn.\n\n---\n\nJe werkt voor het Finance-team.\n\nWat je nooit doet:\n- Een mail versturen.\n",
                encoding="utf-8")
cm = t / "home/.claude/CLAUDE.md"
c = w(env, "controleer", "--ini", "JDS")
check("A9 zonder CLAUDE.md = fout", punt(c, "A9")["status"] == "fout" and "bestaat nog niet" in punt(c, "A9")["detail"], punt(c, "A9")["detail"])
r = w(env, "doe", "A9", "--ini", "JDS", "--droog")
check("A9 droog schrijft niets", not cm.exists() and r["uit"][0].startswith("zou doen"), r["uit"])
r = w(env, "doe", "A9", "--ini", "JDS")
tekst = cm.read_text(encoding="utf-8")
check("A9 maakt CLAUDE.md met het blok, zonder de kop boven de lijn",
      tekst.startswith("<!-- E3 teaminstructies begin -->") and tekst.rstrip().endswith("<!-- E3 teaminstructies einde -->")
      and "Je werkt voor het Finance-team." in tekst and "Plak alles" not in tekst, tekst)
c = w(env, "controleer", "--ini", "JDS")
check("A9 ok", punt(c, "A9")["status"] == "ok", punt(c, "A9")["detail"])
check("A9 tweede keer overgeslagen", w(env, "doe", "A9", "--ini", "JDS")["uit"][0].startswith("klopt al"))
cm.write_bytes("# Mijn eigen regels\r\nAntwoord kort.\r\n".encode("utf-8"))
r = w(env, "doe", "A9", "--ini", "JDS")
tekst = cm.read_bytes().decode("utf-8")
check("A9 voegt toe aan een bestaand bestand en laat de rest staan",
      tekst.startswith("# Mijn eigen regels\r\nAntwoord kort.\r\n") and "<!-- E3 teaminstructies begin -->" in tekst and "Je werkt voor het Finance-team." in tekst, tekst)
check("A9 behoudt de regeleinden van het bestand", "\r\n" in tekst and "\n" not in tekst.replace("\r\n", ""))
cm.write_bytes((tekst.rstrip() + "\r\n\r\nMijn staartregel.\r\n").encode("utf-8"))
bron.write_text(bron.read_text(encoding="utf-8").replace("Een mail versturen.", "Een mail versturen.\n- Iets verwijderen."), encoding="utf-8")
c = w(env, "controleer", "--ini", "JDS")
check("A9 herkent een verouderd blok", punt(c, "A9")["status"] == "fout" and "verouderd" in punt(c, "A9")["detail"], punt(c, "A9")["detail"])
w(env, "doe", "A9", "--ini", "JDS")
tekst = cm.read_bytes().decode("utf-8")
check("A9 vervangt enkel het blok: eigen regels en staartregel blijven", "Iets verwijderen." in tekst and tekst.count("E3 teaminstructies begin") == 1
      and tekst.startswith("# Mijn eigen regels") and tekst.rstrip().endswith("Mijn staartregel."), tekst)

inst = t / "home/.claude/plugins/installed_plugins.json"
volledig = inst.read_text(encoding="utf-8")
inst.write_text(json.dumps({"version": 2, "plugins": {"tools@e3-shared": [{"version": "2.19.0"}]}}), encoding="utf-8")
r = w(env, "doe", "A3", "--ini", "JDS", "--droog")
check("A3 voegt de marketplaces op GitHub toe en installeert daaruit",
      "zou draaien: claude plugin marketplace add EqualsThree-Git/e3-finance-skills" in r["uit"] and "zou draaien: claude plugin marketplace add EqualsThree-Git/e3-dossync" in r["uit"]
      and "zou draaien: claude plugin install dossync@e3-dossync" in r["uit"] and "zou draaien: claude plugin install deliverables@e3-shared" in r["uit"]
      and not any("install tools" in x for x in r["uit"]), r["uit"])
inst.write_text(volledig, encoding="utf-8")

c = w(env, "controleer", "--ini", "JDS")
check("briefing-cloudtaak wordt voorbereid, niet ingepland (proef)", punt(c, "BR1")["status"] == "klaar-te-zetten")
check("de briefing-prompt met echt staat in de stap", "echt" in punt(c, "BR1")["actie"] and "15 7 * * 1-5" in punt(c, "BR1")["actie"])
check("retro-taak voor de eigenaar (JDS) is dicht", punt(c, "RT1")["status"] == "dicht")
c = w(env, "controleer", "--ini", "SVL")
check("retro-taak niet van toepassing voor wie geen eigenaar is", punt(c, "RT1")["status"] == "nvt")
check("A8 en A9 gelden voor iedereen", punt(c, "A8")["status"] != "nvt" and punt(c, "A9")["status"] != "nvt")

# 9. Zelfstandige wizard: publieke flows.json, config op de drive, checklist, mappen, keuzes
import urllib.request
pub = json.loads((HERE.parent / "flows.json").read_text(encoding="utf-8"))
check("publieke flows.json bevat geen personen, webapp of geweigerde adressen",
      not any(k in pub for k in ("personen", "webapp", "webapp_gebruikers", "geweigerd")))
check("config-pad staat in flows.json", pub["paden"].get("config", "").endswith("setup-config.json"))
c = w(env, "controleer", "--ini", "JDS")
check("config van de drive gevonden", c["config"] is True)
env2 = dict(env, E3_SETUP_CONFIG=str(t / "bestaat-niet.json"))
c2 = w(env2, "controleer", "--ini", "ZZ")
check("zonder config: webapp wacht op Drive, geen valse melding voor de beheerder",
      punt(c2, "M1")["status"] == "open" and "Drive" in punt(c2, "M1")["detail"], punt(c2, "M1"))
check("zonder config valt de wizard niet om", c2["config"] is False and c2["persoon"]["mail"] is None, c2["persoon"])
check("eerste stappen: programma's, dan GitHub", [x["id"] for x in c["punten"]][:3] == ["A0", "A12", "A1"])


def checklist_post(body):
    p = subprocess.Popen([sys.executable, str(WIZ), "checklist", "--geen-browser"], env=env, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, encoding="utf-8")
    url = p.stderr.readline().split("CHECKLIST: ", 1)[1].strip()
    pagina = urllib.request.urlopen(url, timeout=10).read().decode("utf-8")
    antwoorden = []
    for b in body:
        req = urllib.request.Request(url + "bewaar", data=json.dumps(b).encode(), headers={"Content-Type": "application/json"}, method="POST")
        antwoorden.append(json.loads(urllib.request.urlopen(req, timeout=10).read()))
    out, _ = p.communicate(timeout=30)
    return pagina, antwoorden, json.loads(out)


pagina, a, uit = checklist_post([
    {"mail": "nieuw@gmail.com", "naam": "Nieuwe Collega", "ini": "nc"},
    {"mail": "tools@equalsthree.be", "naam": "Nieuwe Collega", "ini": "nc"},
    {"mail": "Nieuw@equalsthree.be", "naam": "Nieuwe Collega", "ini": "nc", "rol": "partner", "toestel": "Android",
     "granola": False, "plaud": False, "opnemen": True, "whatsapp": False}])
check("checklist-pagina krijgt de flows mee", '"flows"' in pagina and "/*DATA*/" not in pagina)
check("checklist weigert een privéadres", not a[0]["ok"] and "geen werkadres" in a[0]["fout"], a[0])
check("checklist weigert een gedeeld adres", not a[1]["ok"], a[1])
check("checklist bewaart en stopt", a[2]["ok"] and uit["ok"] and uit["ini"] == "NC" and uit["mail"] == "nieuw@equalsthree.be", uit)
prof = json.loads((t / "home/.claude/e3-shared.json").read_text(encoding="utf-8"))
check("checklist zet initialen en mailbox in het profiel", prof["initialen"] == "NC" and prof["mailbox"] == "nieuw@equalsthree.be")
c = w(env, "controleer")
check("na de checklist kent de wizard de persoon zonder --ini", c["ini"] == "NC" and c["persoon"]["naam"] == "Nieuwe Collega" and c["persoon"]["mail"] == "nieuw@equalsthree.be", c["persoon"])
check("geen vragen meer na de checklist", c["vragen"] == [], c["vragen"])
check("WhatsApp nee = W1 en W2 niet van toepassing", punt(c, "W1")["status"] == "nvt" and punt(c, "W2")["status"] == "nvt")
check("Granola nee = G1 niet van toepassing", punt(c, "G1")["status"] == "nvt")
check("partner is geen eigenaar: retro nvt", punt(c, "RT1")["status"] == "nvt")
_, _, uit = checklist_post([{"mail": "nieuw@equalsthree.be", "naam": "Nieuwe Collega", "ini": "NC", "rol": "partner", "eigenaar": True, "whatsapp": True}])
c = w(env, "controleer")
check("partner die het framework beheert: retro geldt", punt(c, "RT1")["status"] != "nvt" and c["persoon"]["eigenaar"] is True)
check("WhatsApp ja: W1 geldt", punt(c, "W1")["status"] != "nvt")
check("E3 Tools-app staat dicht met reden", punt(c, "E1")["status"] == "dicht" and "Apple" in punt(c, "E1")["detail"])

ws = t / "drive/My Drive/Claude workspace"
runs = t / "drive/Shared drives/E3 - Finance/Dossync/opvang/runs"
r = w(env, "doe", "A14", "--droog")
check("A14 droog maakt niets", not ws.exists() and any("zou aanmaken" in x for x in r["uit"]), r["uit"])
r = w(env, "doe", "A14")
check("A14 maakt werkmap en runs aan", ws.is_dir() and runs.is_dir(), r["uit"])
c = w(env, "controleer")
check("A14 ok daarna", punt(c, "A14")["status"] == "ok", punt(c, "A14")["detail"])
import shutil as _sh
_sh.rmtree(t / "drive/Shared drives/E3 - Finance/Dossync/inbox")
r = w(env, "doe", "A14")
check("A14: ontbrekende inbox is voor de beheerder", any("inbox ontbreekt: stap voor de beheerder" in x for x in r["uit"]), r["uit"])
r = w(env, "doe", "A0", "--droog")
check("A0 droog toont enkel winget-opdrachten", r["uit"][0].startswith("klopt al") or all(x.startswith("zou draaien: winget install") for x in r["uit"]), r["uit"])


# 10. noteer vanuit Windows PowerShell 5.1 (aanhalingstekens weg)
r = w(env, "noteer", "account", "{ok:true,mail:nieuw@equalsthree.be}")
check("kapotte JSON wordt geweigerd met uitleg", r.startswith("niet genoteerd") and "sleutel=waarde" in r, r)
r = w(env, "noteer", "account", "ok=true", "mail=nieuw@equalsthree.be", "detail=Nieuwe Collega, Gmail bevestigd")
c = w(env, "controleer")
check("noteer met sleutel=waarde", punt(c, "A1")["status"] == "ok" and "Gmail bevestigd" in punt(c, "A1")["detail"], punt(c, "A1"))
w(env, "noteer", "antwoord.toestel", "iPhone")
check("losse waarde blijft tekst", w(env, "controleer")["persoon"]["toestel"] == "iPhone")
st = json.loads((t / "home/.claude/e3-setup/staat.json").read_text(encoding="utf-8"))
st["NC"]["claude_code"] = "{ok:true}"
(t / "home/.claude/e3-setup/staat.json").write_text(json.dumps(st), encoding="utf-8")
c = w(env, "controleer")
check("een oude, onleesbare notitie laat controleer niet vallen", punt(c, "A8")["status"] == "fout" and "onleesbaar" in punt(c, "A8")["detail"])

print(f"\n{'ALLES OK' if not fouten else f'{fouten} FOUT(EN)'}  ({t})")
sys.exit(1 if fouten else 0)
