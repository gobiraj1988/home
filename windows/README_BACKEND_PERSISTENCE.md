# APEX Backend Permanent-aa Run Pannradhu (Runbook)

> Goal: **Dashboard chart eppovum online-a irukkanum.** "Backend offline" nu varakoodaadhu.
> Indha file unga `windows/` folder-la irukkura scripts-a eppadi use pannradhu nu sollum.

Backend = `J:\APEX_AGI_Forex_Trading_Bot\APEX QUANT\scaffold\backend`
Port = **8010** (`http://127.0.0.1:8010`)
Dashboard = `J:\My_Trader\dashboard\nexus_terminal.html`

---

## 1. Quick Answer / TL;DR

**"Naan chart eppovum velai seyyanum, athuthaan venum":**

- `install_autostart.ps1` file-a **right-click → "Run with PowerShell"**.
- **Oru thadava** pannina pothum. Apparam computer logon aana udane backend thaana start aagidum. Forever set. 🎉

**Autostart venaam, daily-a kaila start panna virumburaa:**

- `START_APEX_ALL.bat` file-a **double-click** pannunga. Backend + dashboard rendum open aagidum.

Adhaan. Mela ulladhu vendaam nu nenacha, intha rendu vazhi mattum theriஞா pothum.

---

## 2. ஏன் முன்னாடி backend off ஆகுது?

Romba simple-a sollanum-na:

- Munnaadi neenga backend-a **console PowerShell window** -la `python.exe` vechu run panneenga.
- Andha **window-a close pannina udane backend-um sethupochu** (window thaan backend-a pidichu vechirundhuchu).
- Backend sethaal → dashboard-ku connect panna onnum illa → chart **"backend offline"** nu kaattum.

**Fix:**

- Ippo namma backend-a **`pythonw.exe`** (window illaadha, hidden mode) -la **detached-a** run panrom.
- Idhaala window-e theriyaadhu, **mooditaalum backend saagaadhu**. 👍
- Innum permanent-a venum-na → **Windows Scheduled Task** (`install_autostart.ps1`) use pannunga. Logon-la thaana start aagidum, crash aanaalum thaana restart aagidum.

---

## 3. Option A — Daily One-Click (`START_APEX_ALL.bat`)

Idhu unga **daily easy button**.

**Eppadi:**

1. `windows\START_APEX_ALL.bat` -a **double-click**.

**Enna nadakkum (expect):**

- Backend **hidden-a** (window theriyaama) start aagum.
- Konja second-la **dashboard** (`nexus_terminal.html`) browser-la open aagum.
- Ellam sariyaa irundhaal dashboard-la **pachai (green) "MT5 Connected"** kaattum.
- Chart live-a varum.

> Note: Backend already run aagitirundhaal, indha script athai marubadi start pannaadhu — adhuvum OK. Just dashboard open aagum.

---

## 4. Option B — Permanent Autostart (`install_autostart.ps1`)

Idhu thaan **truly permanent** option. Oru thadava set pannina, marubadi yosikka vendaam.

**Step-by-step:**

1. `windows\install_autostart.ps1` file-a **right-click** pannunga.
2. **"Run with PowerShell"** -a select pannunga.
3. (Admin kekkudhaan-na "Yes" kuduthuduங்க.)
4. Idhu `APEX_Backend` nu oru **Windows Scheduled Task** create pannum.

**Enna setup aagudhu:**

- Computer-la neenga **logon aana udane** backend **thaana start** aagum.
- Backend **crash aanaalum thaana restart** aagidum.
- Window theriyaadhu (hidden), so accidental-a close panra problem-e illa.

**Verify pannradhu (sariya set aachaa nu check):**

1. Start menu-la **"Task Scheduler"** nu type panni open pannunga.
2. **Task Scheduler Library** -la **`APEX_Backend`** task irukka paarunga.
3. Status **Ready / Running** nu kaattanum.

**Remove pannanum-na (autostart venaam-na):**

- `windows\uninstall_autostart.ps1` -a **right-click → "Run with PowerShell"**.
- Idhu `APEX_Backend` task-a delete pannidum. Apparam autostart nadakkaadhu.

---

## 5. Daily Checks

Roju ஒரு thadava intha checks pannina pothum:

- `status_apex_backend.bat` -a double-click → **ONLINE** nu kaattanum (process id-um kaattum).
- Dashboard-la chart correct-a varala-na **`Ctrl + R`** (refresh) pannunga.
- ONLINE varala / OFFLINE nu kaattudhaa-na → `START_APEX_ALL.bat` -a double-click pannunga.

**Scripts summary:**

```text
START_APEX_ALL.bat       -> Backend start (persistent) + dashboard open  [daily button]
start_apex_backend.bat   -> Backend mattum start (detached, window close pannalaum saagaadhu)
stop_apex_backend.bat    -> Port 8010-la run aagura backend-a stop pannum
status_apex_backend.bat  -> ONLINE / OFFLINE + process id kaattum
install_autostart.ps1    -> Autostart setup (Scheduled Task "APEX_Backend")  [permanent]
uninstall_autostart.ps1  -> Andha autostart task-a remove pannum
```

---

## 6. Troubleshooting

**Chart "sample" data / "offline" kaattudhu:**

- Backend run aagala. → `START_APEX_ALL.bat` (or `start_apex_backend.bat`) pannunga.
- Apparam dashboard-la `Ctrl + R`.

**"error 10048" / "port in use" / "address already in use" message:**

- Idhu **problem illa**. Backend **already run aagiடுச்சு** nu artham. Port 8010-a vere onnu use pannuthu (= namma backend-e).
- Onnum panna vendaam. Dashboard-a refresh panna pothum.

**MT5 Connected (green) varala:**

- **MetaTrader 5 (MT5) open-a, login pannina nilaila irukkanum.** Live data MT5-la irundhuthaan varum.
- MT5 close-a irundhaal backend ON-a irundhaalum live data varaadhu.

**MUKKIYAM — idhellam pannidaadheenga:**

- `APEX_AGI_Forex_Trading_Bot` folder-a **delete pannaadheenga, move pannaadheenga, rename pannaadheenga.**
  - **Adhu thaan backend.** Athukulla irukkura **`.venv`** -la **hardcoded paths** irukku — folder nகர்ந்தாal / path maaru-na backend velai seyyaadhu.

---

## 7. Important Reminders

- **APEX_AGI = backend** (data + logic engine). → `J:\APEX_AGI_Forex_Trading_Bot\...\scaffold\backend`
- **My_Trader = dashboard frontend** (neenga paarkkura chart UI). → `J:\My_Trader\dashboard\nexus_terminal.html`
- **Rendum venum.** Backend illaama dashboard velai seyyaadhu; dashboard illaama chart paarka mudiyaadhu.
- **`M:\OLD_BOT_ARCHIVE` = safety backup.** Edhaavadhu thappaa pona, idhu unga safe copy. Idhaiyum touch pannaadheenga.

---

> Doubt-na, simple-a nyabagam vechukonga:
> 1) Chart venum → `START_APEX_ALL.bat` double-click.
> 2) Forever venum → `install_autostart.ps1` right-click → Run with PowerShell.
> 3) ONLINE-a check panna → `status_apex_backend.bat`.
