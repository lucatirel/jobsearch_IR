# Aurora Job Monitor

Starter kit per monitorare offerte di lavoro coerenti con il profilo di Aurora Olivola.

## Cosa fa

- Interroga ReliefWeb API.
- Legge feed RSS configurati.
- Controlla alcune pagine pubbliche in modo leggero e configurabile.
- Deduplica offerte già viste in SQLite.
- Applica uno scoring coerente con il profilo di Aurora.
- Produce:
  - `reports/latest_jobs.csv`
  - `reports/latest_report.md`
  - `job_monitor.sqlite3`

## Cosa NON fa

- Non fa scraping di LinkedIn. LinkedIn va gestito tramite alert ufficiali, notifiche email o export manuali.
- Non automatizza login o candidature.
- Non promette copertura perfetta: alcune career page sono dinamiche o protette.

## Setup locale Windows

```powershell
cd aurora_job_monitor
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python job_monitor.py --config config.yaml --since-days 7 --include-seen
```

Output:

```text
reports/latest_report.md
reports/latest_jobs.csv
```

## Esecuzione automatica su Windows

Aprire Utilità di pianificazione → Crea attività → Azione:

```text
Programma: powershell.exe
Argomenti: -ExecutionPolicy Bypass -File "C:\path\aurora_job_monitor\run_daily_windows.ps1"
```

Trigger consigliato: ogni giorno alle 09:00.

## GitHub Actions

Copiare la cartella in un repository GitHub. Il workflow `.github/workflows/daily-job-monitor.yml` esegue il monitor ogni giorno e salva il report come artifact.

## Fonti da aggiungere gradualmente

Aggiungere feed RSS ufficiali o pagine career pubbliche in `config.yaml`. Per fonti con API ufficiali, creare una nuova funzione `fetch_*` nel file `job_monitor.py`.

## Nota pratica

La versione migliore per lavorare davvero è ibrida:

1. Script per ReliefWeb/RSS/fonti pubbliche.
2. Alert ufficiali LinkedIn, Impactpool, EuroBrussels, Devex e career page.
3. Report giornaliero filtrato e valutato con lo scoring.
4. Revisione umana solo delle offerte A/B.
