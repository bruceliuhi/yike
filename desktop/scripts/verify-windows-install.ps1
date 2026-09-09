param(
  [Parameter(Mandatory = $true)][string]$BuildReport,
  [Parameter(Mandatory = $true)][string]$ExpectedCommit,
  [Parameter(Mandatory = $true)][int]$ProcessId
)

$ErrorActionPreference = 'Stop'
$reportPath = (Resolve-Path -LiteralPath $BuildReport).ProviderPath
$build = Get-Content -LiteralPath $reportPath -Raw -Encoding UTF8 | ConvertFrom-Json
$evidence = [ordered]@{
  schemaVersion = 1; runId = $build.runId; checkedAt = [DateTime]::UtcNow.ToString('o')
  sourceCommit = $build.source.commit; buildReportSha256 = (Get-FileHash -LiteralPath $reportPath -Algorithm SHA256).Hash.ToLowerInvariant()
  outcome = 'IDENTITY_FAILED'; failureCode = $null; processId = $ProcessId
  processStartedAt = $null; executableName = $null; installedAsarSha256 = $null
  expectedAsarSha256 = $null; executableSha256 = $null
  manualAcceptance = 'UNTESTED'
  scope = 'Installed visible process and archive identity only; installation, interactions, scaling, restart and uninstall remain manual.'
}
$exitCode = 1
try {
  if ([Environment]::OSVersion.Platform -ne 'Win32NT') { throw 'WINDOWS_REQUIRED' }
  if ($ExpectedCommit -notmatch '^[a-fA-F0-9]{40}$' -or $build.source.commit -ne $ExpectedCommit.ToLowerInvariant() -or
      $build.sourceVerification.expectedCommit -ne $ExpectedCommit.ToLowerInvariant() -or
      $build.sourceVerification.status -ne 'VERIFIED' -or $build.outcome -ne 'BUILD_SUCCEEDED' -or $build.source.dirty -ne $false) { throw 'BUILD_SOURCE_NOT_VERIFIED' }
  $archives = @($build.artifacts | Where-Object { $_.path -match '^out/[^/]+-win32-x64/resources/app\.asar$' })
  if ($archives.Count -ne 1 -or $archives[0].sha256 -notmatch '^[a-f0-9]{64}$') { throw 'BUILD_ARCHIVE_MISSING' }
  $evidence.expectedAsarSha256 = $archives[0].sha256
  $process = Get-Process -Id $ProcessId -ErrorAction Stop
  $executable = $process.Path
  if (-not $executable -or [System.IO.Path]::GetFileName($executable) -ne 'YikeAI.exe' -or $process.MainWindowHandle -eq 0) { throw 'VISIBLE_YIKE_PROCESS_REQUIRED' }
  $started = $process.StartTime.ToUniversalTime()
  $evidence.processStartedAt = $started.ToString('o')
  $evidence.executableName = 'YikeAI.exe'
  $finished = [DateTimeOffset]::Parse($build.finishedAt).UtcDateTime
  if ($started -le $finished) { throw 'OLD_PROCESS_STARTED_BEFORE_BUILD_FINISHED' }
  $archive = Join-Path ([System.IO.Path]::GetDirectoryName($executable)) 'resources/app.asar'
  $evidence.installedAsarSha256 = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
  $evidence.executableSha256 = (Get-FileHash -LiteralPath $executable -Algorithm SHA256).Hash.ToLowerInvariant()
  $executables = @($build.artifacts | Where-Object { $_.path -match '^out/[^/]+-win32-x64/YikeAI\.exe$' })
  if ($executables.Count -ne 1 -or $evidence.executableSha256 -ne $executables[0].sha256) { throw 'INSTALLED_EXECUTABLE_MISMATCH' }
  if ($evidence.installedAsarSha256 -ne $evidence.expectedAsarSha256) { throw 'INSTALLED_ARCHIVE_MISMATCH' }
  # Re-read the same PID after hashing; never stop an existing user process.
  $after = Get-Process -Id $ProcessId -ErrorAction Stop
  if ($after.StartTime.ToUniversalTime() -ne $started -or $after.Path -ne $executable -or $after.MainWindowHandle -eq 0) { throw 'PROCESS_CHANGED_DURING_CHECK' }
  $evidence.outcome = 'IDENTITY_VERIFIED'
  $exitCode = 0
} catch {
  $known = @('WINDOWS_REQUIRED','BUILD_SOURCE_NOT_VERIFIED','BUILD_ARCHIVE_MISSING','VISIBLE_YIKE_PROCESS_REQUIRED','OLD_PROCESS_STARTED_BEFORE_BUILD_FINISHED','INSTALLED_ARCHIVE_MISMATCH','INSTALLED_EXECUTABLE_MISMATCH','PROCESS_CHANGED_DURING_CHECK')
  $evidence.failureCode = if ($known -contains $_.Exception.Message) { $_.Exception.Message } else { 'INSTALLED_IDENTITY_CHECK_FAILED' }
} finally {
  $name = 'windows-installed-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,8) + '.json'
  $destination = Join-Path ([System.IO.Path]::GetDirectoryName($reportPath)) $name
  $utf8 = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($destination, ($evidence | ConvertTo-Json -Depth 8), $utf8)
  Write-Output ($evidence.outcome + '; manual acceptance remains UNTESTED. Evidence: ' + $destination)
}
exit $exitCode
