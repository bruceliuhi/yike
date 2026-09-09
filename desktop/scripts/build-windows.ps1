$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne 'Win32NT') { throw 'Run this script on Windows.' }
if ([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne 'X64') { throw 'Windows x64 is required for this candidate.' }
Set-Location (Join-Path $PSScriptRoot '..')
$nodeVersion = & node -p 'process.versions.node.slice(0,2)'
if ($LASTEXITCODE -ne 0 -or $nodeVersion -ne '24') { throw 'Install Node.js 24 x64 before building.' }
$nodeArch = & node -p 'process.arch'
if ($nodeArch -ne 'x64') { throw 'Node.js must be the x64 build.' }

function Invoke-Npm([string[]] $Arguments) {
  & npm.cmd @Arguments
  if ($LASTEXITCODE -ne 0) { throw "npm failed: $($Arguments -join ' ')" }
}
Invoke-Npm -Arguments @('ci')
Invoke-Npm -Arguments @('run', 'typecheck')
Invoke-Npm -Arguments @('test')
& node scripts/run-native-service-smoke.mjs
if ($LASTEXITCODE -ne 0) { throw 'Native Electron transport smoke failed.' }
Invoke-Npm -Arguments @('run', 'make:win')
$archive = Get-ChildItem out -Filter app.asar -Recurse | Where-Object { $_.FullName -match 'win32-x64' } | Select-Object -First 1
if (-not $archive) { throw 'Packaged Windows app.asar is missing.' }
& node scripts/verify-package.mjs $archive.FullName
if ($LASTEXITCODE -ne 0) { throw 'Packaged resources validation failed.' }
& node scripts/run-packaged-smoke.mjs $archive.FullName
if ($LASTEXITCODE -ne 0) { throw 'Packaged application smoke failed.' }
Get-ChildItem out/make/squirrel.windows/x64 -File | Get-FileHash -Algorithm SHA256
Write-Output 'Build artifacts created. Installation, launch, uninstall and signing still need Windows acceptance.'
