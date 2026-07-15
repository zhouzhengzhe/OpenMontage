[CmdletBinding()]
param(
    [Alias("Home")]
    [string]$InstallRoot = "D:\SoftDocument\CodexProject\OpenMontage",
    [switch]$SkipDependencies
)

$ErrorActionPreference = "Stop"
$InstallRoot = (Resolve-Path -LiteralPath $InstallRoot).Path
$VenvPython = Join-Path $InstallRoot ".venv\Scripts\python.exe"
$RemotionDir = Join-Path $InstallRoot "remotion-composer"
$EnvFile = Join-Path $InstallRoot ".env"
$ProjectsDir = Join-Path $InstallRoot "projects"
$BinDir = Join-Path $env:USERPROFILE ".local\bin"
$GlobalLauncher = Join-Path $BinDir "openmontage.cmd"
$GlobalSkillDir = Join-Path $env:USERPROFILE ".codex\skills\openmontage"
$BrowserFallbackPath = $null

if (Test-Path -LiteralPath $EnvFile) {
    $BrowserLine = Get-Content -LiteralPath $EnvFile | Where-Object {
        $_ -match '^\s*HYPERFRAMES_BROWSER_PATH\s*='
    } | Select-Object -First 1
    if ($BrowserLine) {
        $ConfiguredBrowserPath = (($BrowserLine -split '=', 2)[1]).Trim().Trim('"').Trim("'")
        if (Test-Path -LiteralPath $ConfiguredBrowserPath) {
            $env:HYPERFRAMES_BROWSER_PATH = $ConfiguredBrowserPath
        }
    }
}

if (-not (Test-Path -LiteralPath (Join-Path $InstallRoot "AGENT_GUIDE.md"))) {
    throw "Invalid OpenMontage home: $InstallRoot"
}

if (-not $SkipDependencies) {
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        & python -m venv (Join-Path $InstallRoot ".venv")
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create Python virtual environment"
        }
    }

    & $VenvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to upgrade pip"
    }

    & $VenvPython -m pip install -r (Join-Path $InstallRoot "requirements.txt") piper-tts pytest pytest-asyncio httpx2 socksio
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install Python dependencies"
    }

    Push-Location $RemotionDir
    try {
        & npm.cmd ci
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to install Remotion dependencies"
        }
    }
    finally {
        Pop-Location
    }

    Push-Location $InstallRoot
    try {
        & npm.cmd install --no-save --no-package-lock hyperframes@0.7.57
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to install HyperFrames 0.7.57"
        }
        & npx.cmd hyperframes telemetry disable
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to disable HyperFrames telemetry"
        }
        $BrowserReady = $false
        for ($Attempt = 1; $Attempt -le 3; $Attempt++) {
            & npx.cmd hyperframes browser ensure
            if ($LASTEXITCODE -eq 0) {
                $BrowserReady = $true
                break
            }
            if ($Attempt -lt 3) {
                Write-Warning "HyperFrames browser download failed; retrying ($Attempt/3)."
                Start-Sleep -Seconds (5 * $Attempt)
            }
        }
        if (-not $BrowserReady) {
            $ChromeCandidates = @(
                (Join-Path $env:ProgramFiles "Google\Chrome\Application\chrome.exe"),
                (Join-Path ${env:ProgramFiles(x86)} "Google\Chrome\Application\chrome.exe"),
                (Join-Path $env:LOCALAPPDATA "Google\Chrome\Application\chrome.exe"),
                (Join-Path $env:ProgramFiles "Microsoft\Edge\Application\msedge.exe")
            )
            $BrowserFallbackPath = $ChromeCandidates | Where-Object {
                $_ -and (Test-Path -LiteralPath $_)
            } | Select-Object -First 1
            if ($BrowserFallbackPath) {
                $env:HYPERFRAMES_BROWSER_PATH = $BrowserFallbackPath
                & npx.cmd hyperframes browser ensure
                $BrowserReady = $LASTEXITCODE -eq 0
                if ($BrowserReady) {
                    Write-Warning "Using the installed system browser because the pinned browser download failed."
                }
            }
        }
        if (-not $BrowserReady) {
            throw "Failed to install the HyperFrames rendering browser"
        }
    }
    finally {
        Pop-Location
    }
}

New-Item -ItemType Directory -Force -Path $ProjectsDir, $BinDir, $GlobalSkillDir | Out-Null
if (-not (Test-Path -LiteralPath $EnvFile)) {
    Copy-Item -LiteralPath (Join-Path $InstallRoot ".env.example") -Destination $EnvFile
}
if ($BrowserFallbackPath -and -not (Select-String -LiteralPath $EnvFile -Pattern '^\s*HYPERFRAMES_BROWSER_PATH\s*=' -Quiet)) {
    Add-Content -LiteralPath $EnvFile -Encoding utf8 -Value "`r`nHYPERFRAMES_BROWSER_PATH=`"$BrowserFallbackPath`""
}

Copy-Item -LiteralPath (Join-Path $InstallRoot "scripts\windows\openmontage.cmd") -Destination $GlobalLauncher -Force
Copy-Item -LiteralPath (Join-Path $InstallRoot "scripts\windows\openmontage\SKILL.md") -Destination (Join-Path $GlobalSkillDir "SKILL.md") -Force
$GlobalSkillAgents = Join-Path $GlobalSkillDir "agents"
New-Item -ItemType Directory -Force -Path $GlobalSkillAgents | Out-Null
Copy-Item -LiteralPath (Join-Path $InstallRoot "scripts\windows\openmontage\agents\openai.yaml") -Destination (Join-Path $GlobalSkillAgents "openai.yaml") -Force

[Environment]::SetEnvironmentVariable("OPENMONTAGE_HOME", $InstallRoot, "User")
[Environment]::SetEnvironmentVariable("OPENMONTAGE_PROJECTS_DIR", $ProjectsDir, "User")
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
$PathParts = @($UserPath -split ";" | Where-Object { $_ })
if (-not ($PathParts | Where-Object { $_.TrimEnd("\") -ieq $BinDir.TrimEnd("\") })) {
    [Environment]::SetEnvironmentVariable("Path", (($PathParts + $BinDir) -join ";"), "User")
}

$env:OPENMONTAGE_HOME = $InstallRoot
$env:OPENMONTAGE_PROJECTS_DIR = $ProjectsDir
$env:Path = "$BinDir;$env:Path"

$Identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
& icacls.exe $EnvFile /reset | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Failed to reset .env ACL"
}
& icacls.exe $EnvFile /inheritance:r | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Failed to remove inherited .env ACL entries"
}
& icacls.exe $EnvFile /grant:r "${Identity}:(F)" "*S-1-5-32-544:(F)" "*S-1-5-18:(F)" | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Failed to grant the restricted .env ACL"
}

$ProfilesCli = Join-Path $InstallRoot "scripts\openmontage_global_cli.py"
$ProfileArgs = @("profiles", "validate")
& $VenvPython $ProfilesCli @ProfileArgs
if ($LASTEXITCODE -ne 0) {
    throw "Failed to validate generation profiles"
}

Write-Output "OpenMontage global installation complete."
Write-Output "Home: $InstallRoot"
Write-Output "Launcher: $GlobalLauncher"
Write-Output "Skill: $GlobalSkillDir"
Write-Output "Restart Codex to discover the new skill."
