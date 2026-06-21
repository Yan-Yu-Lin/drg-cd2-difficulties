# Watches CD2.sav; when it changes, decodes it into the repo and makes a git
# checkpoint (commit + push). Polling-based for robustness. Installed as a
# Task Scheduler task at logon. Logs to logs\watcher.log.
$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'

$Repo   = 'D:\dev\cd2-difficulty-library'
$Save   = 'C:\Program Files (x86)\Steam\steamapps\common\Deep Rock Galactic\FSD\Saved\SaveGames\Mods\CD2.sav'
$Python = 'C:\Users\arthu\AppData\Roaming\uv\python\cpython-3.12.12-windows-x86_64-none\python.exe'
$Git    = 'C:\Users\arthu\AppData\Local\Programs\Git\cmd\git.exe'
$Gh     = 'C:\Program Files\GitHub CLI\gh.exe'

$StateDir = Join-Path $Repo '.state'
$LogDir   = Join-Path $Repo 'logs'
$StateFile= Join-Path $StateDir 'last_sha256.txt'
$LogFile  = Join-Path $LogDir 'watcher.log'
New-Item -ItemType Directory -Force -Path $StateDir, $LogDir | Out-Null

function Log($m) {
  $line = "{0}  {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m
  Add-Content -Path $LogFile -Value $line
}

function Get-Sha($path) {
  try { (Get-FileHash -Path $path -Algorithm SHA256).Hash } catch { $null }
}

function Wait-Stable($path) {
  # returns $true once the file is unchanged for ~3s and readable (not mid-write)
  for ($i = 0; $i -lt 20; $i++) {
    if (-not (Test-Path $path)) { return $false }
    $a = (Get-Item $path).Length; $la = (Get-Item $path).LastWriteTimeUtc
    Start-Sleep -Seconds 3
    if (-not (Test-Path $path)) { return $false }
    $b = (Get-Item $path).Length; $lb = (Get-Item $path).LastWriteTimeUtc
    if ($a -eq $b -and $la -eq $lb) {
      try { $fs = [System.IO.File]::Open($path,'Open','Read','ReadWrite'); $fs.Close(); return $true }
      catch { } # still locked, keep waiting
    }
  }
  return $false
}

function Process-Change {
  if (-not (Wait-Stable $Save)) { Log 'save not stable/readable yet; skipping'; return }
  $sha = Get-Sha $Save
  if (-not $sha) { return }
  $last = if (Test-Path $StateFile) { Get-Content $StateFile -Raw } else { '' }
  if ($sha.Trim() -eq $last.Trim()) { return }   # unchanged

  Log "change detected (sha $($sha.Substring(0,8)))"
  $snap = Join-Path $StateDir 'CD2.snapshot.sav'
  Copy-Item -Path $Save -Destination $snap -Force

  $out = & $Python (Join-Path $Repo 'tools\decode_cd2.py') $snap $Repo 2>&1
  Log "decode: $out"
  if ($LASTEXITCODE -ne 0) { Log 'decode failed; aborting commit'; return }

  Push-Location $Repo
  try {
    & $Git add -A 2>&1 | Out-Null
    & $Git diff --cached --quiet
    if ($LASTEXITCODE -ne 0) {
      $n = (Get-ChildItem (Join-Path $Repo 'difficulties') -Filter *.cd2.json).Count
      $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
      $msg = "auto: $ts ($n difficulties, cd2 $($sha.Substring(0,8)))"
      & $Git commit -m $msg 2>&1 | Out-Null
      Log "committed: $msg"
      & $Git push 2>&1 | ForEach-Object { Log "push: $_" }
    } else {
      Log 'no file changes after decode (nothing to commit)'
    }
  } finally { Pop-Location }

  Set-Content -Path $StateFile -Value $sha.Trim()
}

Log '=== watcher started ==='
while ($true) {
  try { Process-Change } catch { Log "ERROR: $_" }
  Start-Sleep -Seconds 30
}
