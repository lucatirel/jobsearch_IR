# Run once manually from PowerShell in this folder:
#   py -m venv .venv
#   .\.venv\Scripts\Activate.ps1
#   pip install -r requirements.txt
#   python job_monitor.py --config config.yaml --since-days 3

Set-Location $PSScriptRoot
.\.venv\Scripts\python.exe .\job_monitor.py --config .\config.yaml --since-days 3
