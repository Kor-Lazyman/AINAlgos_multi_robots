param(
    [string]$Output = 'output\train_e_retry1_40updates',
    [int]$Updates = 40
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$WaamPython = 'C:\Users\lazzyman\anaconda3\envs\waam\python.exe'
if (-not (Test-Path -LiteralPath $WaamPython)) { throw 'waam Python environment not found' }
New-Item -ItemType Directory -Path 'output\logs' -Force | Out-Null
$RunLog = Join-Path 'output\logs' ((Split-Path $Output -Leaf) + '.log')
# Native Python warnings on stderr are log messages, not PowerShell failures.
$ErrorActionPreference = 'Continue'
& $WaamPython -u train.py --updates $Updates --n-steps 64 --batch-size 32 --epochs 10 --eval-every 4 --save-every 4 --device cuda --train-dir train --validation-dir validation --official-validator --output $Output 2>&1 | Tee-Object -FilePath $RunLog
exit $LASTEXITCODE
