# E3 setup

Zet een nieuwe Windows-pc van Equals Three op het AI-framework Finance.

1. Open PowerShell en plak:

   ```powershell
   irm https://raw.githubusercontent.com/EqualsThree-Git/e3-setup/main/start.ps1 | iex
   ```

   Dat installeert wat ontbreekt, laat je aanmelden bij GitHub, zet de E3-plugins klaar en opent de checklist.
2. Open de Claude-app, meld je aan met je werkadres, kies **Code** en typ `/setup:setup`.

De wizard doet de rest en eindigt met een rapport per flow. Opnieuw starten mag altijd: wat klopt, slaat hij over.

## Inhoud

- `start.ps1`: stap 0, zonder Claude.
- `setup/`: de plugin `setup` (marketplace `e3-setup`) met de wizard (`skills/setup`).
- `sandbox/`: test op een kale Windows in Windows Sandbox (`start-sandbox.ps1`).

Deze repo is publiek en bevat geen namen, adressen of sleutels. De interne configuratie staat op de gedeelde drive.
