$ErrorActionPreference = 'Stop'
$requiredNodeRange = '>=24.15.0 <25'
$desktopRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Push-Location $desktopRoot
try {
  $nodeCommand = Get-Command node -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
  $nodeVersion = $null
  if ($nodeCommand) {
    try {
      $measuredVersion = & $nodeCommand.Source -p 'process.versions.node' 2>$null
      if ($LASTEXITCODE -eq 0 -and $measuredVersion -match '^\d+\.\d+\.\d+$') { $nodeVersion = [string]$measuredVersion }
    } catch { $nodeVersion = $null }
  }
  $supportedNode = $nodeVersion -and $nodeVersion -match '^24\.(\d+)\.\d+$' -and [int]$Matches[1] -ge 15
  if (-not $nodeCommand -or -not $supportedNode) {
    # Bootstrap failure is still reportable without Node; never enumerate env or
    # include raw exception text, a computer name, an account name, or credentials.
    $runId = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH-mm-ss-fffZ') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,8)
    $evidenceDirectory = Join-Path $desktopRoot ('out/windows-evidence/' + $runId)
    New-Item -ItemType Directory -Force -Path $evidenceDirectory | Out-Null
    $lockPath = Join-Path $desktopRoot 'package-lock.json'
    $lockHash = if (Test-Path -LiteralPath $lockPath) { (Get-FileHash -Algorithm SHA256 -LiteralPath $lockPath).Hash.ToLowerInvariant() } else { $null }
    $commit = $null
    $dirty = $null
    if (Get-Command git -CommandType Application -ErrorAction SilentlyContinue) {
      try {
        $gitCommit = & git rev-parse HEAD 2>$null
        if ($LASTEXITCODE -eq 0) { $commit = ($gitCommit | Out-String).Trim() }
        $gitChanges = & git status --porcelain=v1 --untracked-files=normal 2>$null
        if ($LASTEXITCODE -eq 0) { $dirty = [bool](($gitChanges | Out-String).Trim().Length) }
      } catch { $dirty = $null }
    }
    $now = [DateTime]::UtcNow.ToString('o')
    $stages = foreach ($stageId in @('preflight','dependencies','typecheck','unit-tests','native-smoke','make-win','artifacts','archive-check','packaged-smoke')) {
      if ($stageId -eq 'preflight') { @{ id = $stageId; status = 'FAILED'; startedAt = $now; finishedAt = $now; exitCode = 1 } }
      else { @{ id = $stageId; status = 'NOT_RUN'; startedAt = $null; finishedAt = $null; exitCode = $null } }
    }
    $report = [ordered]@{
      schemaVersion = 1; runId = $runId; startedAt = $now; finishedAt = $now
      outcome = 'BUILD_FAILED'; failureCode = $(if ($nodeCommand) { 'NODE_24_15_REQUIRED' } else { 'NODE_NOT_FOUND' }); manualAcceptance = 'UNTESTED'
      source = @{ commit = $commit; dirty = $dirty; gitAvailable = ($null -ne $commit -and $null -ne $dirty); lockfile = @{ path = 'package-lock.json'; sha256 = $lockHash } }
      host = @{ platform = [Environment]::OSVersion.Platform.ToString(); osVersion = [Environment]::OSVersion.VersionString; osRelease = [Environment]::OSVersion.Version.ToString(); osArch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString(); nodeVersion = $nodeVersion; nodeArch = $null }
      runtime = @{ requiredNodeRange = $requiredNodeRange; npmVersion = $null; npmSource = $null; nodeSha256 = $null; npmCliSha256 = $null; launchMode = $null }
      stages = @($stages)
      artifacts = @()
      scope = 'Automatic build evidence only; installation, visible startup, uninstall and display scaling require the separate manual record.'
    }
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText((Join-Path $evidenceDirectory 'windows-build.json'), ($report | ConvertTo-Json -Depth 8), $utf8)
    $manual = (Get-Content -LiteralPath (Join-Path $desktopRoot 'docs/WINDOWS_ACCEPTANCE_TEMPLATE.md') -Raw -Encoding UTF8).Replace('{{RUN_ID}}', $runId)
    [System.IO.File]::WriteAllText((Join-Path $evidenceDirectory 'WINDOWS_ACCEPTANCE.md'), $manual, $utf8)
    Write-Output ('Node.js ' + $requiredNodeRange + ' x64 is required. Failure evidence: ' + $evidenceDirectory)
    exit 1
  }
  & $nodeCommand.Source (Join-Path $PSScriptRoot 'windows-build-evidence.mjs')
  $buildExitCode = $LASTEXITCODE
  exit $buildExitCode
} finally {
  Pop-Location
}
