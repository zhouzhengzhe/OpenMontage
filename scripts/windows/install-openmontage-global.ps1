[CmdletBinding()]
param(
    [string]$Home = "D:\SoftDocument\CodexProject\OpenMontage",
    [switch]$SkipDependencies
)

$ErrorActionPreference = "Stop"
$Home = (Resolve-Path -LiteralPath $Home).Path
$VenvPython = Join-Path $Home ".venv\Scripts\python.exe"
$RemotionDir = Join-Path $Home "remotion-composer"
$EnvFile = Join-Path $Home ".env"
$ProjectsDir = Join-Path $Home "projects"
$BinDir = Join-Path $env:USERPROFILE ".local\bin"
$GlobalLauncher = Join-Path $BinDir "openmontage.cmd"
$GlobalSkillDir = Join-Path $env:USERPROFILE ".codex\skills\openmontage"

if (-not (Test-Path -LiteralPath (Join-Path $Home "AGENT_GUIDE.md"))) {
    throw "Invalid OpenMontage home: $Home"
}

if (-not $SkipDependencies) {
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        & python -m venv (Join-Path $Home ".venv")
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create Python virtual environment"
        }
    }

    & $VenvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to upgrade pip"
    }

    & $VenvPython -m pip install -r (Join-Path $Home "requirements.txt") piper-tts pytest pytest-asyncio httpx2 socksio
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

    Push-Location $Home
    try {
        & npm.cmd install --no-save --no-package-lock hyperframes@0.7.57
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to install HyperFrames 0.7.57"
        }
    }
    finally {
        Pop-Location
    }
}

New-Item -ItemType Directory -Force -Path $ProjectsDir, $BinDir, $GlobalSkillDir | Out-Null
if (-not (Test-Path -LiteralPath $EnvFile)) {
    Copy-Item -LiteralPath (Join-Path $Home ".env.example") -Destination $EnvFile
}

Copy-Item -LiteralPath (Join-Path $Home "scripts\windows\openmontage.cmd") -Destination $GlobalLauncher -Force
Copy-Item -LiteralPath (Join-Path $Home "scripts\windows\openmontage\SKILL.md") -Destination (Join-Path $GlobalSkillDir "SKILL.md") -Force
$GlobalSkillAgents = Join-Path $GlobalSkillDir "agents"
New-Item -ItemType Directory -Force -Path $GlobalSkillAgents | Out-Null
Copy-Item -LiteralPath (Join-Path $Home "scripts\windows\openmontage\agents\openai.yaml") -Destination (Join-Path $GlobalSkillAgents "openai.yaml") -Force

[Environment]::SetEnvironmentVariable("OPENMONTAGE_HOME", $Home, "User")
[Environment]::SetEnvironmentVariable("OPENMONTAGE_PROJECTS_DIR", $ProjectsDir, "User")
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
$PathParts = @($UserPath -split ";" | Where-Object { $_ })
if (-not ($PathParts | Where-Object { $_.TrimEnd("\") -ieq $BinDir.TrimEnd("\") })) {
    [Environment]::SetEnvironmentVariable("Path", (($PathParts + $BinDir) -join ";"), "User")
}

$env:OPENMONTAGE_HOME = $Home
$env:OPENMONTAGE_PROJECTS_DIR = $ProjectsDir
$env:Path = "$BinDir;$env:Path"

$Identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
& icacls.exe $EnvFile /inheritance:r /grant:r "${Identity}:(F)" "*S-1-5-32-544:(F)" "*S-1-5-18:(F)" | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Failed to restrict .env ACL"
}

Write-Output "OpenMontage global installation complete."
Write-Output "Home: $Home"
Write-Output "Launcher: $GlobalLauncher"
Write-Output "Skill: $GlobalSkillDir"
Write-Output "Restart Codex to discover the new skill."
