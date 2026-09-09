param([string]$NodeExecutable)

$ErrorActionPreference = 'Stop'
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

try {
  # Use a real Node 24 binary. Get-Command in the child is deliberately not mocked.
  $candidates = if ($NodeExecutable) { @($NodeExecutable) } else {
    @(Get-Command node -CommandType Application -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
  }
  $sourceNode = $null
  foreach ($candidate in $candidates) {
    $version = & $candidate -p 'process.versions.node' 2>$null
    if ($LASTEXITCODE -eq 0 -and $version -match '^24\.\d+\.\d+$') {
      $sourceNode = $candidate
      break
    }
  }
  if (-not $sourceNode) { throw 'This regression requires a real Node 24 executable.' }

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

    $result = Invoke-FixturePowerShell ('-File "' + $bootstrapScript + '"') $searchPath $scenario.ExitCode
    if ($result.ExitCode -ne $scenario.ExitCode) {
      throw ('Expected downstream exit code {0}, got {1}. {2} {3}' -f $scenario.ExitCode, $result.ExitCode, $result.Output.Trim(), $result.Error.Trim())
    }
    $lines = @($result.Output.Trim() -split '\r?\n')
    if ($lines.Count -ne 1 -or -not $lines[0].StartsWith('BOOTSTRAP_FIXTURE ') -or $result.Error) {
      throw 'Expected exactly one downstream marker and no stderr.'
    }
    $invocation = $lines[0].Substring('BOOTSTRAP_FIXTURE '.Length) | ConvertFrom-Json
    if ($invocation.executable -ne $expectedNode) { throw 'Bootstrap did not invoke the first Node application on PATH.' }
    if ($invocation.arguments.Count -ne 1 -or $invocation.arguments[0] -ne $evidenceScript) {
      throw 'Bootstrap did not preserve the script path containing spaces as one argument.'
    }
    if ($invocation.cwd -ne $desktopFixture) { throw 'Bootstrap did not use its desktop directory.' }
    if (Test-Path -LiteralPath (Join-Path $desktopFixture 'out')) { throw 'Valid Node 24 unexpectedly produced bootstrap failure evidence.' }
    Write-Output ('PASS: first PATH Node invoked once; spaced script argument intact; exit code {0} preserved.' -f $scenario.ExitCode)
  }
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
