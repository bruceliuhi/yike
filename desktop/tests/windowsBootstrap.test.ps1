param([string]$NodeExecutable, [string]$UnsupportedNodeExecutable)

$ErrorActionPreference = 'Stop'
$candidateCommit = '0123456789abcdef0123456789abcdef01234567'
$desktopSource = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$powershellExecutable = (Get-Process -Id $PID).Path
$temporaryParent = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath()).TrimEnd('\')
$fixtureName = 'yike-windows-bootstrap-' + [Guid]::NewGuid().ToString('N')
$fixtureRoot = Join-Path $temporaryParent $fixtureName

function Invoke-FixturePowerShell([string]$Arguments, [string]$SearchPath, [int]$BuildExitCode = 0) {
  $start = New-Object System.Diagnostics.ProcessStartInfo
  $start.FileName = $powershellExecutable
  $start.Arguments = '-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass ' + $Arguments
  $start.UseShellExecute = $false
  $start.CreateNoWindow = $true
  $start.RedirectStandardOutput = $true
  $start.RedirectStandardError = $true
  $start.EnvironmentVariables['PATH'] = $SearchPath
  $start.EnvironmentVariables['PATHEXT'] = '.COM;.EXE;.BAT;.CMD'
  $start.EnvironmentVariables['YIKE_BOOTSTRAP_FIXTURE_EXIT'] = [string]$BuildExitCode
  $start.EnvironmentVariables['YIKE_PILOT_AUTH_SECRET'] = 'bootstrap-fixture-private-secret'
  $start.EnvironmentVariables['COMPUTERNAME'] = 'bootstrap-fixture-private-computer'
  $start.EnvironmentVariables['USERNAME'] = 'bootstrap-fixture-private-user'
  $start.EnvironmentVariables.Remove('NODE_OPTIONS')
  $process = New-Object System.Diagnostics.Process
  $process.StartInfo = $start
  try {
    if (-not $process.Start()) { throw 'Could not start fixture PowerShell.' }
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit(15000)) {
      $process.Kill()
      throw 'Fixture PowerShell exceeded 15 seconds.'
    }
    return @{ ExitCode = $process.ExitCode; Output = $stdout.Result; Error = $stderr.Result }
  } finally {
    $process.Dispose()
  }
}

function Assert-BootstrapFailure([string]$Name, [string]$SearchPath, [string]$FailureCode, $NodeVersion) {
  $failedDesktop = Join-Path $fixtureRoot ($Name + ' desktop with spaces')
  $failedScripts = Join-Path $failedDesktop 'scripts'
  $failedDocs = Join-Path $failedDesktop 'docs'
  New-Item -ItemType Directory -Path $failedScripts, $failedDocs | Out-Null
  Copy-Item -LiteralPath (Join-Path $desktopSource 'scripts/build-windows.ps1') -Destination $failedScripts
  Copy-Item -LiteralPath (Join-Path $desktopSource 'docs/WINDOWS_ACCEPTANCE_TEMPLATE.md') -Destination $failedDocs
  Copy-Item -LiteralPath $evidenceScript -Destination $failedScripts
  $result = Invoke-FixturePowerShell ('-File "' + (Join-Path $failedScripts 'build-windows.ps1') + '" -ExpectedCommit ' + $candidateCommit) $SearchPath
  if ($result.ExitCode -ne 1 -or $result.Output.Contains('BOOTSTRAP_FIXTURE ') -or $result.Error) {
    throw ('{0}: Expected bootstrap exit 1 without downstream invocation or stderr; got exit {1}. {2} {3}' -f $Name, $result.ExitCode, $result.Output.Trim(), $result.Error.Trim())
  }
  $reportFiles = @(Get-ChildItem -LiteralPath (Join-Path $failedDesktop 'out/windows-evidence') -Filter 'windows-build.json' -File -Recurse)
  if ($reportFiles.Count -ne 1) { throw ($Name + ': Expected exactly one failure report.') }
  $rawReport = Get-Content -LiteralPath $reportFiles[0].FullName -Raw -Encoding UTF8
  $report = $rawReport | ConvertFrom-Json
  if ($report.schemaVersion -ne 1 -or $report.outcome -ne 'BUILD_FAILED' -or $report.failureCode -ne $FailureCode -or $report.manualAcceptance -ne 'UNTESTED') {
    throw ($Name + ': Failure report changed its schema, outcome, failure code or manual acceptance.')
  }
  if ($report.host.nodeVersion -ne $NodeVersion -or $null -ne $report.host.nodeArch) {
    throw ($Name + ': Report must retain only the measured Node version and unknown architecture.')
  }
  $expectedStages = @('preflight','dependencies','typecheck','unit-tests','native-smoke','make-win','artifacts','archive-check','packaged-smoke')
  if ($report.stages.Count -ne 9) { throw ($Name + ': Expected all nine stages.') }
  for ($index = 0; $index -lt $expectedStages.Count; $index++) {
    $stage = $report.stages[$index]
    if ($stage.id -ne $expectedStages[$index]) { throw ($Name + ': Failure stages changed order.') }
    if ($index -eq 0) {
      if ($stage.status -ne 'FAILED' -or $stage.exitCode -ne 1 -or -not $stage.startedAt -or -not $stage.finishedAt) {
        throw ($Name + ': Preflight must record a timed failure with exit code 1.')
      }
    } elseif ($stage.status -ne 'NOT_RUN' -or $null -ne $stage.startedAt -or $null -ne $stage.finishedAt -or $null -ne $stage.exitCode) {
      throw ($Name + ': Downstream stages must remain NOT_RUN with no execution evidence.')
    }
  }
  if ($report.artifacts -isnot [array] -or $report.artifacts.Count -ne 0) { throw ($Name + ': Failed bootstrap must record artifacts=[].') }
  $runtimeKeys = @($report.runtime.PSObject.Properties.Name | Sort-Object)
  $expectedRuntimeKeys = @('requiredNodeRange','npmVersion','npmSource','nodeSha256','npmCliSha256','launchMode' | Sort-Object)
  if (($runtimeKeys -join ',') -ne ($expectedRuntimeKeys -join ',') -or $report.runtime.requiredNodeRange -ne '>=24.15.0 <25') {
    throw ($Name + ': Failure report must contain the minimal runtime object and required Node range.')
  }
  foreach ($key in @('npmVersion','npmSource','nodeSha256','npmCliSha256','launchMode')) {
    if ($null -ne $report.runtime.$key) { throw ($Name + ': Bootstrap must not claim an unmeasured runtime value.') }
  }
  foreach ($privateValue in @($fixtureName, 'bootstrap-fixture-private-secret', 'bootstrap-fixture-private-computer', 'bootstrap-fixture-private-user', 'YIKE_PILOT_AUTH_SECRET')) {
    if ($rawReport.Contains($privateValue)) { throw ($Name + ': Failure report leaked private path or environment data.') }
  }
  if ($rawReport -match '"(?:env|environment|execPath|nodePath|npmPath|computerName|username)"\s*:') {
    throw ($Name + ': Failure report must not add path or environment fields.')
  }
  $manualPath = Join-Path $reportFiles[0].DirectoryName 'WINDOWS_ACCEPTANCE.md'
  $manual = Get-Content -LiteralPath $manualPath -Raw -Encoding UTF8
  if (-not $manual.Contains($report.runId) -or $manual.Contains('{{RUN_ID}}')) { throw ($Name + ': Manual acceptance template must use this run ID.') }
  if (-not $result.Output.Contains('>=24.15.0 <25')) { throw ($Name + ': Bootstrap error must display the required Node range.') }
  Write-Output ('PASS: {0}; failure report preserves nine stages, UNTESTED, empty artifacts and privacy.' -f $Name)
}

try {
  # Parse the actual installer identity entry using Windows PowerShell's parser.
  # This is syntax coverage only, not a fabricated running installed process.
  $parseTokens = $null
  $parseErrors = $null
  $null = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $desktopSource 'scripts/verify-windows-install.ps1'), [ref]$parseTokens, [ref]$parseErrors)
  if ($parseErrors.Count -ne 0) { throw 'Installed identity script has PowerShell syntax errors.' }
  # Use a real supported Node binary. Get-Command in the child is deliberately not mocked.
  $candidates = if ($NodeExecutable) { @($NodeExecutable) } else {
    @(Get-Command node -CommandType Application -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
  }
  $sourceNode = $null
  foreach ($candidate in $candidates) {
    $version = & $candidate -p 'process.versions.node' 2>$null
    if ($LASTEXITCODE -eq 0 -and $version -match '^24\.(\d+)\.\d+$' -and [int]$Matches[1] -ge 15) {
      $sourceNode = $candidate
      break
    }
  }
  if (-not $sourceNode) { throw 'This regression requires a real Node >=24.15.0 <25 executable.' }
  $unsupportedCandidates = if ($UnsupportedNodeExecutable) { @($UnsupportedNodeExecutable) } else {
    @(Get-Command node -CommandType Application -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
  }
  $unsupportedNode = $null
  $unsupportedVersion = $null
  foreach ($candidate in $unsupportedCandidates) {
    $version = & $candidate -p 'process.versions.node' 2>$null
    if ($LASTEXITCODE -eq 0 -and $version -match '^\d+\.\d+\.\d+$') {
      $parts = $version.Split('.')
      if ($parts[0] -ne '24' -or [int]$parts[1] -lt 15) {
        $unsupportedNode = $candidate
        $unsupportedVersion = $version
        break
      }
    }
  }
  if ($UnsupportedNodeExecutable -and -not $unsupportedNode) { throw 'UnsupportedNodeExecutable must be a real Node outside >=24.15.0 <25.' }

  $desktopFixture = Join-Path $fixtureRoot 'desktop with spaces'
  $scriptDirectory = Join-Path $desktopFixture 'scripts'
  $docsDirectory = Join-Path $desktopFixture 'docs'
  $firstDirectory = Join-Path $fixtureRoot 'first node with spaces'
  $secondDirectory = Join-Path $fixtureRoot 'second node with spaces'
  New-Item -ItemType Directory -Path $scriptDirectory, $docsDirectory, $firstDirectory, $secondDirectory | Out-Null
  Copy-Item -LiteralPath (Join-Path $desktopSource 'scripts/build-windows.ps1') -Destination $scriptDirectory
  Copy-Item -LiteralPath (Join-Path $desktopSource 'docs/WINDOWS_ACCEPTANCE_TEMPLATE.md') -Destination $docsDirectory
  foreach ($directory in @($firstDirectory, $secondDirectory)) {
    Copy-Item -LiteralPath $sourceNode -Destination (Join-Path $directory 'node.exe')
  }
  # Only this marker script can run downstream: the fixture has no npm build chain.
  $markerScript = @'
console.log('BOOTSTRAP_FIXTURE ' + JSON.stringify({
  executable: process.execPath, arguments: process.argv.slice(1), cwd: process.cwd()
}));
process.exit(Number(process.env.YIKE_BOOTSTRAP_FIXTURE_EXIT));
'@
  $utf8 = New-Object System.Text.UTF8Encoding($false)
  $evidenceScript = Join-Path $scriptDirectory 'windows-build-evidence.mjs'
  [System.IO.File]::WriteAllText($evidenceScript, $markerScript, $utf8)
  $bootstrapScript = Join-Path $scriptDirectory 'build-windows.ps1'

  $scenarios = @(
    @{ Directories = @($firstDirectory, $secondDirectory); ExitCode = 0 },
    @{ Directories = @($secondDirectory, $firstDirectory); ExitCode = 37 }
  )
  foreach ($scenario in $scenarios) {
    $searchPath = $scenario.Directories -join ';'
    $discovery = Invoke-FixturePowerShell '-Command "Get-Command node -CommandType Application | Select-Object -ExpandProperty Source"' $searchPath
    $discovered = @($discovery.Output.Trim() -split '\r?\n')
    $expectedNode = Join-Path $scenario.Directories[0] 'node.exe'
    if ($discovery.ExitCode -ne 0 -or $discovered.Count -ne 2 -or $discovered[0] -ne $expectedNode) {
      throw 'Fixture must expose exactly two real Node applications in the requested PATH order.'
    }

    $result = Invoke-FixturePowerShell ('-File "' + $bootstrapScript + '" -ExpectedCommit ' + $candidateCommit) $searchPath $scenario.ExitCode
    if ($result.ExitCode -ne $scenario.ExitCode) {
      throw ('Expected downstream exit code {0}, got {1}. {2} {3}' -f $scenario.ExitCode, $result.ExitCode, $result.Output.Trim(), $result.Error.Trim())
    }
    $lines = @($result.Output.Trim() -split '\r?\n')
    if ($lines.Count -ne 1 -or -not $lines[0].StartsWith('BOOTSTRAP_FIXTURE ') -or $result.Error) {
      throw 'Expected exactly one downstream marker and no stderr.'
    }
    $invocation = $lines[0].Substring('BOOTSTRAP_FIXTURE '.Length) | ConvertFrom-Json
    if ($invocation.executable -ne $expectedNode) { throw 'Bootstrap did not invoke the first Node application on PATH.' }
    if ($invocation.arguments.Count -ne 3 -or $invocation.arguments[0] -ne $evidenceScript -or $invocation.arguments[1] -ne '--expected-commit' -or $invocation.arguments[2] -ne $candidateCommit) {
      throw 'Bootstrap did not preserve the script path containing spaces as one argument.'
    }
    if ($invocation.cwd -ne $desktopFixture) { throw 'Bootstrap did not use its desktop directory.' }
    if (Test-Path -LiteralPath (Join-Path $desktopFixture 'out')) { throw 'Supported Node unexpectedly produced bootstrap failure evidence.' }
    Write-Output ('PASS: first PATH Node invoked once; spaced script argument intact; exit code {0} preserved.' -f $scenario.ExitCode)
  }
  $failureChecks = @()
  try {
    $emptyDirectory = Join-Path $fixtureRoot 'empty node search path'
    New-Item -ItemType Directory -Path $emptyDirectory | Out-Null
    $discovery = Invoke-FixturePowerShell '-Command "if (Get-Command node -CommandType Application -ErrorAction SilentlyContinue) { exit 9 }; exit 0"' $emptyDirectory
    if ($discovery.ExitCode -ne 0 -or $discovery.Output -or $discovery.Error) { throw 'No-Node fixture unexpectedly resolves a Node application.' }
    Assert-BootstrapFailure 'no Node on PATH' $emptyDirectory 'NODE_NOT_FOUND' $null
  } catch { $failureChecks += $_.Exception.Message }
  if ($unsupportedNode) {
    try {
      $unsupportedDirectory = Join-Path $fixtureRoot 'unsupported first node with spaces'
      New-Item -ItemType Directory -Path $unsupportedDirectory | Out-Null
      Copy-Item -LiteralPath $unsupportedNode -Destination (Join-Path $unsupportedDirectory 'node.exe')
      $searchPath = @($unsupportedDirectory, $firstDirectory) -join ';'
      $discovery = Invoke-FixturePowerShell '-Command "Get-Command node -CommandType Application | Select-Object -ExpandProperty Source"' $searchPath
      $discovered = @($discovery.Output.Trim() -split '\r?\n')
      if ($discovery.ExitCode -ne 0 -or $discovered.Count -ne 2 -or $discovered[0] -ne (Join-Path $unsupportedDirectory 'node.exe')) {
        throw 'Unsupported-Node fixture must resolve the old real Node before the supported Node.'
      }
      Assert-BootstrapFailure ('unsupported first Node ' + $unsupportedVersion) $searchPath 'NODE_24_15_REQUIRED' $unsupportedVersion
    } catch { $failureChecks += $_.Exception.Message }
  } else {
    Write-Output 'SKIP: unsupported first Node regression; no real unsupported Node executable was found.'
  }
  if ($failureChecks.Count) { throw ($failureChecks -join [Environment]::NewLine) }
  Write-Output 'PASS: Windows bootstrap regression (2 scenarios).'
} catch {
  Write-Output ('FAIL: ' + $_.Exception.Message)
  exit 1
} finally {
  if (Test-Path -LiteralPath $fixtureRoot) {
    $resolvedFixture = (Resolve-Path -LiteralPath $fixtureRoot).ProviderPath
    if ($resolvedFixture -ne [System.IO.Path]::GetFullPath($fixtureRoot) -or
        -not $resolvedFixture.StartsWith($temporaryParent + '\', [StringComparison]::OrdinalIgnoreCase) -or
        [System.IO.Path]::GetFileName($resolvedFixture) -ne $fixtureName) {
      throw 'Refusing to remove a path outside this generated fixture directory.'
    }
    Remove-Item -LiteralPath $resolvedFixture -Recurse -Force
  }
}
