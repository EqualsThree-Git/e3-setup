---
name: setup
description: Sluit een nieuwe collega van Equals Three aan op het AI-framework Finance, zonder hulp van iemand anders, in Claude Code in de desktop-app, ook op een pc die net uit de doos komt (eerst start.ps1 uit de repo e3-setup, dan deze skill). Controleert programma's, GitHub, laptop, Claude Code op het Team-plan, plugins uit de marketplaces op GitHub, teaminstructies, connectors en rechten, zet per bron (mail, agenda, Granola, Plaud, Geluidsrecorder, memo's, WhatsApp, foto's, bijlagen, links, publieke bronnen, E3 Daily, ochtendbriefing, retro) zelf klaar wat kan, toont wat enkel de persoon kan doen als één korte stap tegelijk, test elke flow en eindigt met een rapport per flow. Herneembaar - een tweede keer starten slaat over wat al klopt. Met --droog toont hij enkel wat hij zou doen. Triggert op "/setup", "/setup:setup", "/tools:setup", "zet mij op", "sluit mij aan", "onboarding", "setup-wizard", "nieuwe collega aansluiten", "werkt mijn dossync", "wat werkt er bij mij niet".
metadata:
  version: "2.0.0"
---

# /setup:setup (v2.0.0)

Eén wizard voor elke collega die aansluit, ook de eerste dag. Iedereen werkt in Claude Code in de desktop-app (niet in Cowork of chat) en alles loopt via deze wizard: hij controleert en installeert, de persoon doet enkel wat alleen een mens kan. De persoon onthoudt geen procedure en leest geen handleiding: jij doet het werk, hij of zij doet enkel wat alleen een mens kan (een login, een toestemming, iets op de gsm), telkens één stap.

- De wizard is een eigen repo, `EqualsThree-Git/e3-setup` (publiek, marketplace `e3-setup`, plugin `setup`). Op een kale pc begint alles met `start.ps1` uit die repo, zonder Claude: `irm https://raw.githubusercontent.com/EqualsThree-Git/e3-setup/main/start.ps1 | iex`. Dat installeert Python, Git, Node, GitHub CLI, Claude Code, de Claude-app en Google Drive voor desktop, laat de persoon aanmelden bij GitHub, zet de marketplaces en plugins klaar en opent de checklist.
- `flows.json` naast dit bestand zegt wat er aangesloten wordt, welke flow vrijgegeven is en wat elke stap controleert. Volg het; vul niets aan uit je geheugen. Namen, adressen en de webapp staan niet in de (publieke) repo maar in `paden.config` op de shared drive (`Framework › 10 Flows › setup-config.json`); de wizard voegt die samen zodra Drive E3 - Finance toont. `controleer` geeft `"config": false` zolang dat bestand niet zichtbaar is: werk dan eerst A0, A12 en A2 af.
- `scripts/wizard.py` ziet de laptop en houdt de stand bij in `~/.claude/e3-setup/staat.json`. Jij ziet de connectors en de taken op claude.ai en noteert wat je vaststelt met `wizard.py noteer`.
- Draai de scripts met `python` (niet `python -I`). Noteer altijd met `sleutel=waarde`-paren (`noteer account ok=true mail=naam@equalsthree.be "detail=Gmail bevestigd"`), nooit met JSON: Windows PowerShell haalt de aanhalingstekens uit JSON-argumenten. `<W>` hieronder is `python "<map van deze skill>/scripts/wizard.py"`.

## Toon

Nederlands, kort, zonder uitleg over hoe het framework werkt. Eén stap voor de gebruiker per bericht, in één of twee zinnen, met de knop of het scherm bij naam. Wacht op "klaar" (of een antwoord) en kijk dan zelf na of het gelukt is. Lukt een stap twee keer niet, zeg dan wie het oplost (staat in het veld `wie`), zet hem op ✗ en ga verder met de volgende flow. Eén flow die faalt houdt de andere niet tegen. Noem nooit een collega bij naam als oplossing: wie iets oplost is de gebruiker zelf of de beheerder uit `flows.json`.

## Wat nooit

- Een connector koppelen aan, of verder werken met, een adres buiten `@equalsthree.be` of uit `geweigerd` (een gedeeld adres, een adres namens iemand anders, een privéadres). Dan stop je die connector en vraag je opnieuw te koppelen.
- Mail- of agenda-inhoud tonen. Enkel adressen, aantallen en ✓/✗.
- Wachtwoorden, tokens of codes vragen, tonen of bewaren. Ook niet de gedeelde login van OpenTheBox of Bizzy.
- Schrijven in een klantmap, mails versturen, afspraken of uitnodigingen maken, iets in Arx schrijven.
- Een taak inplannen voor een flow die in `flows.json` niet op `vrij` staat, of een cloudtaak stil aanmaken: toon altijd eerst de exacte instellingen.
- Iemand anders zijn account, browserprofiel of laptop gebruiken.

## 0. Starten

1. Zeg in één regel wat je doet: "Ik kijk je laptop, skills en connectors na en zet per bron klaar wat kan. Ik lees geen mails of afspraken, enkel adressen. Waar ik jou nodig heb, vraag ik één ding tegelijk."
2. **Droge run?** Bij `--droog` of "droge run": voeg `--droog` toe aan elke `doe`, `noteer`, `opruimen` en `rapport`, maak geen taken, roep geen enkele schrijvende tool aan, en zeg bij elke stap "zou doen: …". Is de droge run voor een collega op een andere pc (`--voor <INI>`), voeg dan ook `--andere-pc` toe aan `controleer` en `rapport`, roep geen connector aan (het zijn niet de zijne) en schrijf het rapport met `--uit` naar de scratchpad. Ga in dat geval meteen naar stap 4.
3. **Programma's.** Normaal deed `start.ps1` dit al. Ontbreekt Python toch: kijk met PowerShell `python --version`. Ontbreekt het of is het ouder dan 3.10: vraag één keer "Mag ik Python 3.12 installeren (zonder adminrechten)?" en draai na ja `winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements --disable-interactivity`. Daarna een nieuwe shell.
4. **Checklist.** Is er nog geen `~/.claude/e3-shared.json` met initialen, draai dan `<W> checklist` in de achtergrond: het opent een lokale pagina (regel `CHECKLIST: http://127.0.0.1:...` op stderr; open die in het browserpaneel als de browser niet zelf opent) waar de persoon werkadres, naam, initialen, rol, gsm, Granola, Plaud, opnemen en WhatsApp invult en ziet wat er voor hem aangesloten wordt. Na Bewaren stopt het script en kent de wizard de persoon; `--ini` mag je daarna weglaten.
5. `<W> controleer`. De uitvoer is de stand per stap. Wat `ok` is, sla je over; zeg het in één regel: "Al in orde: laptop, skills, webapp." Begin bij `volgende`.

## 1. Basis, in de volgorde van `flows.json`

- **A0 Programma's.** `<W> doe A0`: installeert met winget wat ontbreekt (Git, Node, GitHub CLI, Claude Code, de Claude-app, Drive voor desktop, en Chrome als WhatsApp meeleest). Vraagt Windows toestemming, dan is dat de gebruikersstap.
- **A12 GitHub.** `<W> controleer` kijkt `gh auth status` en de toegang tot `EqualsThree-Git/e3-finance-skills` en `e3-dossync` na. Niet aangemeld: start `gh auth login --hostname github.com --git-protocol https --web` in de achtergrond, toon de persoon de code van acht tekens uit de uitvoer en zeg: "Plak deze code in de browser die opent en klik Authorize." Daarna `gh auth setup-git`. Geen toegang tot de repo's: de beheerder nodigt het GitHub-account uit; de persoon aanvaardt in de mail van GitHub.
- **A1 Wie ben je.** Het werkadres komt uit de checklist. Bevestig het met de Gmail-connector (`search_threads` met `in:sent`, één resultaat, enkel de afzender): die moet gelijk zijn. Geen Arx: Arx wordt vervangen door E3CRM. Noteer: `<W> noteer account ok=true mail=<werkadres> ini=<INI> "detail=<naam>, Gmail bevestigd"`. Een ander adres van dezelfde persoon in E3CRM (bv. een ouder adres) staat als `arx_mail` in de config.
- **A2 Laptop.** `<W> doe A2 --ini <INI>`. Ontbreekt Google Drive voor desktop of is E3 - Finance niet zichtbaar, dan de gebruikersstap.
- **A3 E3-plugins.** `<W> doe A3 --ini <INI>`. De plugin `setup` komt uit `e3-setup` (EqualsThree-Git/e3-setup), `tools` en `deliverables` uit de marketplace `e3-shared` (GitHub: EqualsThree-Git/e3-finance-skills), `dossync` uit `e3-dossync` (EqualsThree-Git/e3-dossync); de wizard voegt de marketplaces toe en installeert wat ontbreekt. De oude chat-skills (zips) en `.plugin`-bestanden installeer je niet meer. Lukt installeren niet en staan de plugins niet via de organisatie klaar, vraag dan één stap: "Typ `/plugin` en installeer tools, deliverables en dossync." Na een installatie: Claude herstarten (gebruikersstap) en daarna deze skill opnieuw starten; de wizard gaat verder waar hij was. Verouderde plugins (`arx`, `mail`, `analyst-tools`) noem je; verwijderen enkel na ja.
- **A4 Connectors.** Per connector één lichte oproep, enkel het adres:
  - Gmail: `search_threads` met `in:sent`, één resultaat, enkel het afzenderadres.
  - Google Calendar: `list_calendars`; de primaire agenda moet het werkadres zijn met `accessRole` owner. Enkel `freeBusyReader` betekent: verkeerd account.
  - Google Drive: `search_files` op de root, één resultaat, de eigenaar.
  - Granola: enkel als de persoon Granola gebruikt, `get_account_info`.
  Noteer elk: `<W> noteer connector.gmail ok=true adres=<adres> --ini <INI>` (bij een fout `ok=false "detail=<wat>"`). Een ontbrekende of verkeerde connector is één gebruikersstap per connector. Een connector die geen tools heeft, telt als ontbrekend.
- **A5 Rechten.** `<W> doe A5 --ini <INI>`: schrijft en wist meteen een testbestand in Dossync › inbox, opvang en inbox › ruw. Niet schrijfbaar: de stap voor de beheerder, en de flows die de inbox nodig hebben gaan op ✗.
- **A14 Mappen.** `<W> doe A14`: maakt `My Drive › Claude workspace` (werkmap) en `Dossync › opvang › runs` en `inbox › ruw` als ze ontbreken; ontbreekt de inbox of opvang zelf, dan is dat voor de beheerder. My Drive zelf is de wachtrij van route-queue (TE VERPLAATSEN); `Dossier-sync` en `_Uit mail` maakt de webapp (M1).
- **A6 Profiel.** `<W> doe A6 --ini <INI>`: zet initialen, mailbox, drive en werkmap in `~/.claude/e3-shared.json`.
- **A7 Fiche in E3CRM.** `<W> doe A7 --ini <INI>`: zet `initialen` en `werkadres` op de eigen persoonsfiche in E3CRM (opvraag `team.zet`, gezocht op het Arx-adres, `door` = de eigen initialen) en leest na met `team.lijst`. Dat is het enige register van wie bij het team hoort: de verwerker (veld `door`), de E3 Daily en de webapp lezen het. De toegang tot E3CRM staat in `~/.claude/e3crm.json`; de wizard neemt ze stil over van de gedeelde kopie (`paden.e3crm_toegang`) als ze ontbreekt of verouderd is. Lees, toon of log dat bestand nooit, ook niet om te controleren. Het werkadres van de eigen mailbox staat vooraan in `werkadres`: daar gaat de E3 Daily-mail heen; andere adressen op de fiche blijven staan. Fouten zeg je zoals E3CRM ze geeft: "Geen persoon met …" betekent eerst in Arx, na de nachtrun opnieuw; "Kolommen ontbreken" en "initialen al in gebruik" zijn voor de beheerder.

- **A10 Eigen E3CRM-sleutel (laptop).** `<W> doe A10 --ini <INI>`: vraagt bij E3CRM een eigen sleutel aan (`sleutel.aanvraag`); tools@ mailt hem naar het werkadres uit het register, nooit naar een ander adres. Daarna één gebruikersstap: de persoon voert in een terminal `python "<wizard.py>" sleutel --ini <INI>` uit en plakt de sleutel uit de mail (verborgen invoer). De wizard test hem en zet hem in `~/.claude/e3crm.json` met `eigen: <INI>`; A7 overschrijft een eigen sleutel nooit meer met de gedeelde beheersleutel. Vraag de sleutel nooit in de chat en vul hem nooit zelf in. Intrekken doet de beheerder in E3CRM (`sleutelIntrekken('<INI>')`); een nieuwe aanvraag vervangt de oude sleutel.
- **A11 Eigen E3CRM-sleutel (cloud).** `<W> doe A11 --ini <INI>` vraagt een cloudsleutel aan: die mag enkel lezen, voorstellen doen en correcties melden. De persoon maakt zelf op claude.ai/code een persoonlijke omgeving (nooit een gedeelde): Network access Limited met `script.google.com` en `script.googleusercontent.com`, en de variabelen `E3CRM_URL` en `E3CRM_TOKEN` uit de mail. Claude mag naam, domeinen en `E3CRM_URL` voorbereiden, de sleutel plakt de persoon zelf. Noteer: `<W> noteer sleutel_cloud ok=true omgeving=<naam> --ini <INI>`.
- **A8 Claude Code op het Team-plan.** Je draait zelf in Claude Code; controleer dat de persoon in de desktop-app (tabblad Code) is aangemeld met het eigen @equalsthree.be-account op het Team-plan van Equals Three, niet met een privéaccount. Kijk na met `claude auth status` of Instellingen › Account (adres, plan) en met de schedule-skill (kan een cloudtaak, routine, aangemaakt worden?). Claude Code zit op elke Team-zetel, ook Standard (support.claude.com, Team plan): een Standard-zetel is dus geen blokkade. Noteer: `<W> noteer claude_code ok=true adres=<adres> plan=Team zetel=Standard|Premium routines=true --ini <INI>` (bij een fout `"ok":false,"detail":"<wat>"`; de wizard weigert een ander adres, een ander plan dan Team en `routines` niet op true). Bij een Standard-zetel meldt de wizard als aandachtspunt dat de gebruikslimiet lager ligt dan bij een Premium-zetel: zeg dat in één zin, zonder alarm, en ga verder. Niet aangemeld of geen cloudtaken: de gebruikersstap uit `flows.json`, en lukt dat niet, dan is de beheerder aan zet (zetel).
- **A13 GitHub op claude.ai.** Voor de cloudtaken moet claude.ai/code de repo's kunnen kiezen. Kijk na met de schedule-skill (repositories) of laat de persoon het tonen; anders de gebruikersstap: claude.ai/code › repository kiezen › Connect GitHub, met het eigen GitHub-account. Noteer `<W> noteer github_cloud ok=true "detail=e3-dossync en e3-finance-skills zichtbaar"`.
- **A9 Teaminstructies.** `<W> doe A9 --ini <INI>`: kopieert alles onder de lijn `---` van `Framework › 01 Framework › Teaminstructies Claude.md` naar `~/.claude/CLAUDE.md`, tussen de markeringen `<!-- E3 teaminstructies begin -->` en `<!-- E3 teaminstructies einde -->`. Bestaat het bestand al, dan voegt de wizard enkel dat blok toe of vervangt hij het; de rest van het bestand blijft staan. Een volgende start ververst het blok als de teaminstructies veranderden. Zeg daarna dat ze in een nieuwe sessie gelden.

## 2. Vragen

De checklist beantwoordt ze allemaal (rol, toestel, granola, plaud, opnemen, whatsapp). Geeft `controleer` toch iets in `vragen`, vraag enkel dat, met keuzeknoppen, en noteer met `<W> noteer antwoord.<sleutel> <waarde>`. Rol `eigenaar` (wie het framework beheert) krijgt de retro-cloudtaak.

## 3. Per flow

Werk de stappen af in de volgorde van `flows.json`. Bij elke stap: wat is `status` en `vrijgave`?
- `dicht`: niets doen. In het rapport staat de reden.
- `nvt`: overslaan.
- pc-stap: `<W> doe <stap> --ini <INI>`, daarna `controleer` opnieuw. Nog niet ok: de gebruikersstap.
- gebruikersstap: één bericht met het veld `gebruiker`, wachten, nakijken.
- taakstap (`M2`, `BR1`, `RT1`, `G1`, `R2`): zie hieronder. Bij `vrijgave: proef` maak je de taaktekst klaar en toon je hem, maar je plant niets in.

**M1 Webapp en B1 Bijlagen.** Mag het adres de webapp niet gebruiken (staat niet in `webapp_gebruikers`), dan is dat een stap voor de beheerder en stop je flow 01, 10 en 11. Anders de gebruikersstap met de link: toestemming geven, Dossync activeren, ook Gmail lezen toestaan. Kijk daarna met `controleer` na (de status wordt binnen een kwartier geschreven; wacht met `<W> wacht` niet, maar ga intussen verder en kom terug).

**Cloudtaken in het algemeen.** Een cloudtaak draait op claude.ai en loopt ook als de laptop uit staat. De wizard maakt ze zelf aan op de claude.ai van de persoon: eerst A13 (GitHub op claude.ai) en A11 (de persoonlijke omgeving met de E3CRM-cloudsleutel), dan elke taak met die omgeving. Maak er nooit stil een aan: toon de gebruiker eerst de exacte instellingen (naam, dagen en uur, repository, connectors, prompt) in een kopieerbaar blok, en maak ze aan (schedule-skill) of laat ze aanmaken pas na een ja. Kijk daarna zelf na dat ze bestaan (lijst van de routines: naam, schema, repository) en noteer ze met `<W> noteer taak.<naam> ok=true|false "detail=<één zin>" --ini <INI>`. Bestaat een taak niet na het aanmaken, dan is de stap ✗. Lokale geplande taken van de desktop-app draaien enkel als de laptop aan staat; gebruik ze enkel voor wat lokaal moet (Plaud, Geluidsrecorder, WhatsApp).

**M2 Dossync-cloudtaken (flow 01, 02, 11).** Twee routines op claude.ai van de gebruiker zelf: `Dossync <INI> ochtend` en `Dossync <INI> namiddag`, op werkdagen (maandag tot vrijdag) op `dossync_uren` (Brusselse tijd), repository `EqualsThree-Git/e3-dossync`, connectors enkel Arx, Gmail, Google Calendar en Google Drive. Prompt (vul INI en adres in):

```
Dossync-run in de cloud voor <INI> (<werkadres>). <PROEF>

Lees en volg dossync/skills/dossync/CLOUD.md uit de repo e3-dossync, en SKILL.md in dezelfde map voor alles wat daar niet anders staat. Regels voor logregels en contacten staan in de repo e3-finance-skills (tools/skills/update-longlist en tools/skills/add-arx); is die niet beschikbaar, volg dan wat SKILL.md erover zegt.

Dit is een run zonder toezicht: stel geen vragen, zet geen profielfoto's, en eindig met de korte samenvatting uit CLOUD.md stap 7.
```

`<PROEF>` is de eerste keer: "Proefrun: schrijf niets in Arx en verschuif laatsteRun niet. Zet in het uit-bestand run.proef op true." Maak de routines met de schedule-skill (RemoteTrigger) als die beschikbaar is; kan die geen repository of connectors kiezen, of is ze er niet, dan toon je de gebruiker één scherm tegelijk: claude.ai/code › Scheduled › New task, naam, de tekst (in een kopieerbaar blok), Daily op het uur, Advanced › Repository, Advanced › Connectors, Create. Is Claude Code op het web niet beschikbaar voor de zetel, dan ✗ met wie = beheerder ("Claude Code op het web aanzetten voor deze zetel") en ga verder.
Laat daarna de ochtendtaak één keer lopen (Run now). Test: binnen een kwartier staat in My Drive › Dossier-sync een uit-bestand of een `laatsteRun` van vandaag, met `who` = INI en `run.mailbox` = het werkadres, en `run.agenda.calendar` = ok. Toon enkel de tellers uit de samenvatting. Zegt de gebruiker dat die er goed uitzien, zet dan in beide routines de proefzin om naar "Gewone run: wat zeker is, schrijf je in Arx; de rest wordt een voorstel. Zet in het uit-bestand run.proef op false." Noteer `taak.dossync`, `test.01`, `test.02` en `test.11`.

**BR1 Briefing-cloudtaak (flow briefing).** Routine `Briefing <INI>` op claude.ai van de gebruiker zelf, werkdagen om 7u15 (Brusselse tijd, cron `15 7 * * 1-5`), repository `EqualsThree-Git/e3-dossync`, connectors Google Calendar, Gmail, Google Drive en Arx op het werkadres. Prompt (vul INI en adres in):

```
Voer /dossync:briefing uit voor <INI>, <werkadres>, echt.
```

Eerst een proef zonder `echt`: `Voer /dossync:briefing uit voor <INI>, <werkadres>.` Die maakt een proefbestand dat de mail van 8u niet leest. Laat de taak één keer lopen (Run now), kijk in `Dossync › briefing` of het proefbestand er staat met de juiste INI en het werkadres (toon enkel dat, geen inhoud), en vraag dan of de gebruiker de taak mag omzetten naar de prompt met `echt`. Noteer `taak.briefing`. Bij `vrijgave: proef` toon je de instellingen en de proefprompt maar plan je niets in.

**RT1 Retro-cloudtaak (enkel de eigenaar).** Voor wie in `flows.json` `eigenaar` is (anders ✗ niet van toepassing, niets doen): routine `Retro` op claude.ai van de eigenaar, op de eerste werkdag van de maand om 8u (Brusselse tijd, cron `0 8 1-3 * 1-5`; de prompt laat haar niets doen als vandaag niet de eerste werkdag is), repository `EqualsThree-Git/e3-finance-skills`, connectors Google Drive, met E3CRM-toegang. Prompt:

```
Voer /tools:retro uit (voorbereiden) voor de vorige maand. Doe niets als vandaag niet de eerste werkdag van de maand is.
```

Zolang de flow `retro` dicht staat (E3CRM kent de acties van de correctielog nog niet), toon je enkel de instellingen en plan je niets in. Noteer `taak.retro`.

**G1 Granola (flow 03).** Routine `Granola-opvang <INI>`: werkdagen elk uur van 8u05 tot 20u05, repository `EqualsThree-Git/e3-dossync`, connectors enkel Granola, Arx en Google Drive, met als instructie de tekst uit het veld `controle` van G1 (die verwijst naar `dossync/skills/opvang/granola.md`). Test: Granola-connector op het werkadres en `search_meetings` van de laatste zeven dagen geeft een aantal (geen inhoud tonen); na de eerste run een bestand `<YYMMDD HHMM> granola <INI>.json` in `Dossync › opvang › runs` met `fout` leeg.

**P1 Plaud (flow 04).** Enkel voor wie het toestel heeft en enkel als de flow vrij is. Dan: `npx -y @plaud-ai/mcp@latest login` starten (opent de browser), gebruikersstap, en `get_current_user` als test.

**R1 en R2 Geluidsrecorder (flow 05).** `<W> doe R1 --ini <INI>`: installeert faster-whisper via de transcript-skill (dat kan enkele minuten duren en vraagt soms een Windows-toestemming), zet de uitvoermap op `Documents\Transcripts` en schrijft een proefopname van een halve minuut uit (Windows-spraak, geen microfoon, in een tijdelijke map die daarna weg is). Draai het in de achtergrond en wacht. De laptoptaak (`R2`) is een geplande taak in Claude Desktop (scheduled-tasks), `Dossync opnames <INI>`, elk uur van 8u tot 20u, met de prompt uit `opvang/geluidsrecorder - taak.md` waarin `<INI>` en `<skill>` (het pad van de geïnstalleerde transcript-skill) ingevuld zijn.

**T1 Memo en F1 Foto (flow 06 en 09).** Enkel voor een iPhone; bij Android zijn ze niet van toepassing en loopt het via de E3 Tools-app (flow 13). Eerst één stap: "Installeer de Google Drive-app en meld je aan met <werkadres>. Zet toetsenbord-dictee aan met Nederlands (Instellingen › Algemeen › Toetsenbord)." Dan de teststap uit `flows.json` en `<W> wacht "TEST memo <INI>" --ini <INI>` (of `"TEST kaartje <INI>"`). Gevonden: kijk met de Drive-connector (`search_files` op de titel) of de eigenaar het werkadres is. Niets na tien minuten: probeer bij de memo de vervangroutes B en C uit `Framework › 05 Handleidingen › Memo naar de inbox (iPhone en Android).md`, één per keer. Noteer `test.06` en `test.09`, en draai daarna `<W> opruimen --ini <INI>` (de testbestanden gaan naar `_verwerkt/setup-test`).

**W1 WhatsApp-lezer (flow 07).** Enkel als de persoon in de checklist WhatsApp aanvinkte. Eerst de gebruikersstap: een lijst "Equals Three" in WhatsApp met de werkchats (intern en klanten); wat er niet in staat, wordt nooit gelezen. Dan `<W> doe W1 --ini <INI>` **in de achtergrond**: het installeert Playwright en start de koppeling. Verschijnt de regel `QR: http://127.0.0.1:<poort>/qr.html`, open die url in het browserpaneel (`preview_start` met `url`) en vraag: "Scan de QR-code: WhatsApp > Gekoppelde apparaten > Apparaat koppelen." Na de scan wacht de stap tot de lijst binnen is (tot tien minuten). Vraag daarna het apparaat te benoemen: "E3 CRM-lezer - <INI> laptop". Nooit WhatsApp Web openen in Chrome of CIC voor deze stap.

**W2 WhatsApp-sweep (flow 07).** Taakstap, geen model, vereist W1 ok. `<W> doe W2 --ini <INI>` schrijft de starter `%LOCALAPPDATA%\E3\whatsapp-sweep.py`. Die neemt bij elke run de nieuwste geïnstalleerde whatsapp-skill, zodat een update van de plugin de taak niet breekt. Daarna maakt de stap de Windows-taak "E3 WhatsApp-sweep <INI>": werkdagen elk uur van 8u10 tot 20u10, met pythonw, verborgen, op lage prioriteit, enkel als de gebruiker aangemeld is, nooit twee tegelijk. Bij `vrijgave: proef` bereidt de stap de taak enkel voor en toont ze het commando; de tester plant in met `--inplannen`. Proef vooraf: `wa_lezer.py sweep --ini <INI> --droog`; de items komen in `whatsapp-uit\_droog`. De uitvoer van de taak staat in `%LOCALAPPDATA%\E3\whatsapp-lezer.log`, en elke run zet een regel in de Dossync-runlog.

**E1 E3 Tools-app (flow 13).** Dicht zolang er geen Apple Developer-account is (TestFlight). Toon enkel de reden.

**K1 Publieke bronnen (flow 12).** Nakijken met `controleer`. OpenTheBox en Bizzy lopen op een gedeelde login van tools@: noem dat, vraag niets.

**E3 Daily.** De fiche uit A7 is de aanmelding. De mail van 8u vraagt daarnaast de initialen in `DAILY_ONTVANGERS` (stap D2): dat kan enkel tools@ zetten, de wizard toont het als stap voor tools@ en test het niet. Zolang de flow dicht is, staat in het rapport "nog niet live". Is ze vrij: test met Gmail `search_threads` op `from:tools@equalsthree.be subject:"E3 Daily" newer_than:3d`, enkel het aantal.

Noteer elke test met `<W> noteer test.<flow> ok=true|false "detail=<één zin>" --ini <INI>`.

## 4. Rapport

`<W> rapport --ini <INI>` schrijft `setup-rapport <YYMMDD> <INI>` (md en html) in `~/.claude/e3-setup/`. Open de html. Zeg daarna in drie tot zes regels: wat werkt, wat niet en wie het oplost, en wat nog niet vrijgegeven is. Eindig met: "Start /setup:setup opnieuw wanneer je wil; ik sla over wat klopt."

## Opnieuw starten

Een tweede start doet hetzelfde: `controleer` zegt wat klopt, `doe` slaat een stap over die al klopt, notities blijven staan. Kijk de connectors (A4) en de taaktest wel opnieuw na als de notitie ouder is dan een dag. Zo dient dezelfde wizard ook als controle: "werkt mijn dossync nog?".

## Voor de beheerder

- Een flow vrijgeven = in `flows.json` `vrijgave` op `vrij` zetten (repo e3-setup). De wizard verandert niet.
- Personen, de webapp, `webapp_gebruikers`, `geweigerd` en `uren_nieuw` staan in `Framework › 10 Flows › setup-config.json` op E3 - Finance, nooit in de repo (die is publiek).
- Testen op een kale pc: `sandbox\start-sandbox.ps1` in de repo maakt een Windows Sandbox met de repo en een logmap.
- Een nieuwe collega met eigen uren: niets te doen, de wizard kiest het eerste vrije paar uit `uren_nieuw`. Wie bij het team hoort, staat op de persoonsfiche in E3CRM (A7). `webapp_gebruikers` is tijdelijk, tot de webapp die fiche leest.
- `eigenaar: true` bij een persoon in de config, of rol eigenaar in de checklist, bepaalt wie de retro-cloudtaak (RT1) krijgt; `zetel` is een vermelding voor het aandachtspunt over de gebruikslimiet van een Standard-zetel.
- `wizard.py` gebruikt enkel de standaardbibliotheek, zodat het draait op een laptop waar net Python op kwam.
