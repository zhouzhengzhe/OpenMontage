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
    }
    finally {
        Pop-Location
    }
}

New-Item -ItemType Directory -Force -Path $ProjectsDir, $BinDir, $GlobalSkillDir | Out-Null
if (-not (Test-Path -LiteralPath $EnvFile)) {
    Copy-Item -LiteralPath (Join-Path $InstallRoot ".env.example") -Destination $EnvFile
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

$CurrentSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$TrustedSids = @(
    $CurrentSid,
    [System.Security.Principal.SecurityIdentifier]::new("S-1-5-32-544"),
    [System.Security.Principal.SecurityIdentifier]::new("S-1-5-18")
)
$EnvAcl = [System.Security.AccessControl.FileSecurity]::new()
$EnvAcl.SetAccessRuleProtection($true, $false)
$EnvAcl.SetOwner($CurrentSid)
foreach ($Sid in $TrustedSids) {
    $Rule = [System.Security.AccessControl.FileSystemAccessRule]::new(
        $Sid,
        [System.Security.AccessControl.FileSystemRights]::FullControl,
        [System.Security.AccessControl.AccessControlType]::Allow
    )
    [void]$EnvAcl.AddAccessRule($Rule)
}
Set-Acl -LiteralPath $EnvFile -AclObject $EnvAcl

Write-Output "OpenMontage global installation complete."
Write-Output "Home: $InstallRoot"
Write-Output "Launcher: $GlobalLauncher"
Write-Output "Skill: $GlobalSkillDir"
Write-Output "Restart Codex to discover the new skill."
