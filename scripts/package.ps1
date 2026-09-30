# Windows twin of package.sh. Builds from git so .gitignore decides what ships.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$version = (python -c "import clauditseo; print(clauditseo.__version__)").Trim()
$out = "clauditseo-$version.zip"
git archive --format=zip --prefix="clauditseo/" -o $out HEAD
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [IO.Compression.ZipFile]::OpenRead((Resolve-Path $out))
try   { $names = $zip.Entries.FullName }
finally { $zip.Dispose() }
$leaks = $names -match '\.venv|node_modules|reports/out|\.pytest_cache|benchmarks\.zip|clauditseo-.*\.zip'
if ($leaks) {
  Write-Host "packaging leak detected in ${out}:"
  $leaks | ForEach-Object { Write-Host "  $_" }
  exit 1
}
"{0} clean ({1:N1} MB)" -f $out, ((Get-Item $out).Length / 1MB)
