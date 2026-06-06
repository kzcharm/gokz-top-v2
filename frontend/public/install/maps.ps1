$ErrorActionPreference = "Stop"

$ApiUrl = $env:GOKZ_MAPS_API_URL
if (-not $ApiUrl) {
  $ApiUrl = "https://api.gokz.top/v1/maps?limit=10000&is_validated=true"
}

$Bz2MaxBytes = 150000000
$PackageMapCountThreshold = 25
$PackageBytesThreshold = 1500000000
$DryRun = $env:GOKZ_MAPS_DRY_RUN -eq "1"
$AssumeYes = $env:GOKZ_MAPS_YES -eq "1"

function Confirm-Action($Message) {
  if ($AssumeYes) {
    return $true
  }
  $answer = Read-Host "$Message [y/N]"
  return $answer -in @("y", "Y", "yes", "YES", "Yes")
}

function Get-MapsDirCandidates {
  $cwd = (Get-Location).Path
  $candidates = @()

  if ((Split-Path $cwd -Leaf) -eq "maps" -and (Split-Path (Split-Path $cwd -Parent) -Leaf) -eq "csgo") {
    $candidates += $cwd
  }
  if ((Split-Path $cwd -Leaf) -eq "csgo") {
    $candidates += (Join-Path $cwd "maps")
  }

  $steamDefault = Join-Path ${env:ProgramFiles(x86)} "Steam\steamapps\common\Counter-Strike Global Offensive\csgo\maps"
  $steamUser = Join-Path $env:USERPROFILE "Steam\steamapps\common\Counter-Strike Global Offensive\csgo\maps"
  $candidates += $steamDefault
  $candidates += $steamUser

  $seen = @{}
  foreach ($candidate in $candidates) {
    if (-not $candidate) {
      continue
    }
    $full = [System.IO.Path]::GetFullPath($candidate)
    if (-not $seen.ContainsKey($full)) {
      $seen[$full] = $true
      $full
    }
  }
}

function Get-DetectedMapsDir {
  $candidates = @(Get-MapsDirCandidates)
  foreach ($candidate in $candidates) {
    if (Test-Path $candidate -PathType Container) {
      return $candidate
    }
  }
  if ($candidates.Count -gt 0 -and (Split-Path (Split-Path $candidates[0] -Parent) -Leaf) -eq "csgo") {
    return $candidates[0]
  }
  throw "Run this command from your csgo directory or csgo\maps directory."
}

function Invoke-Download($Url, $Destination) {
  if ($DryRun) {
    Write-Host "DRY RUN download $Url -> $Destination"
    return
  }
  Invoke-WebRequest -Uri $Url -OutFile $Destination -UseBasicParsing
}

function Get-7ZipPath {
  $command = Get-Command 7z -ErrorAction SilentlyContinue
  if ($command) {
    return $command.Source
  }
  $command = Get-Command 7zz -ErrorAction SilentlyContinue
  if ($command) {
    return $command.Source
  }
  $programFiles = @($env:ProgramFiles, ${env:ProgramFiles(x86)})
  foreach ($root in $programFiles) {
    if (-not $root) {
      continue
    }
    $candidate = Join-Path $root "7-Zip\7z.exe"
    if (Test-Path $candidate) {
      return $candidate
    }
  }
  return $null
}

function Get-PackageUrl($Maps) {
  foreach ($map in $Maps) {
    if ($map.download_url -and $map.download_url.Contains("/maps/")) {
      $index = $map.download_url.IndexOf("/maps/")
      return $map.download_url.Substring(0, $index) + "/packages/GlobalMaps.7z"
    }
  }
  return $null
}

function Test-MapNeedsUpdate($MapsDir, $Map) {
  $localPath = Join-Path $MapsDir ($Map.name + ".bsp")
  if (-not (Test-Path $localPath -PathType Leaf)) {
    return $true
  }
  return (Get-Item $localPath).Length -ne [int64]$Map.filesize
}

function Install-RawMap($Url, $Target) {
  $tempPath = Join-Path (Split-Path $Target -Parent) ("." + (Split-Path $Target -Leaf) + ".download")
  try {
    Invoke-Download $Url $tempPath
    if (-not $DryRun) {
      Move-Item -Force $tempPath $Target
    }
  } finally {
    Remove-Item -Force -ErrorAction SilentlyContinue $tempPath
  }
}

function Install-Bz2Map($SevenZip, $Url, $Target) {
  $targetDir = Split-Path $Target -Parent
  $tempBz2 = Join-Path $targetDir ("." + (Split-Path $Target -Leaf) + ".bz2")
  $tempBsp = Join-Path $targetDir ("." + (Split-Path $Target -Leaf))
  try {
    Invoke-Download $Url $tempBz2
    if (-not $DryRun) {
      & $SevenZip e -y "-o$targetDir" $tempBz2
      if ($LASTEXITCODE -ne 0) {
        throw "7z failed to decompress $tempBz2"
      }
      Move-Item -Force $tempBsp $Target
    }
  } finally {
    Remove-Item -Force -ErrorAction SilentlyContinue $tempBz2
    Remove-Item -Force -ErrorAction SilentlyContinue $tempBsp
  }
}

function Install-Map($MapsDir, $Map, $SevenZip) {
  $target = Join-Path $MapsDir ($Map.name + ".bsp")
  if ([int64]$Map.filesize -le $Bz2MaxBytes -and $SevenZip) {
    try {
      Write-Host "Downloading $($Map.name).bsp.bz2"
      Install-Bz2Map $SevenZip ($Map.download_url + ".bz2") $target
      return
    } catch {
      Write-Host "BZ2 failed for $($Map.name), using raw BSP: $($_.Exception.Message)"
    }
  }

  Write-Host "Downloading $($Map.name).bsp"
  Install-RawMap $Map.download_url $target
}

function Install-Package($MapsDir, $PackageUrl, $SevenZip) {
  $tempPath = Join-Path $MapsDir ".GlobalMaps.7z.download"
  try {
    Write-Host "Downloading GlobalMaps.7z"
    Invoke-Download $PackageUrl $tempPath
    if (-not $DryRun) {
      & $SevenZip x -y "-o$MapsDir" $tempPath
      if ($LASTEXITCODE -ne 0) {
        throw "7z failed to extract GlobalMaps.7z"
      }
    }
  } finally {
    Remove-Item -Force -ErrorAction SilentlyContinue $tempPath
  }
}

$mapsDir = Get-DetectedMapsDir
Write-Host "Detected CS:GO maps directory: $mapsDir"
if (-not (Confirm-Action "Update maps in this directory?")) {
  Write-Host "Cancelled."
  exit 1
}

New-Item -ItemType Directory -Force -Path $mapsDir | Out-Null
Write-Host "Fetching map list..."
$maps = Invoke-RestMethod -Uri $ApiUrl
$downloadableMaps = @($maps | Where-Object { $_.download_url })
$pending = @($downloadableMaps | Where-Object { Test-MapNeedsUpdate $mapsDir $_ })
$totalBytes = [int64]0
foreach ($map in $pending) {
  $totalBytes += [int64]$map.filesize
}

Write-Host "$($pending.Count) map(s) need download or update."
if ($pending.Count -eq 0) {
  exit 0
}

$sevenZip = Get-7ZipPath
$packageUrl = Get-PackageUrl $downloadableMaps
$preferPackage = $pending.Count -ge $PackageMapCountThreshold -or $totalBytes -ge $PackageBytesThreshold

if ($preferPackage -and $packageUrl) {
  if ($sevenZip) {
    Install-Package $mapsDir $packageUrl $sevenZip
    Write-Host "Map package extracted."
    exit 0
  }
  if (-not (Confirm-Action "7z is not installed. Download maps one by one instead?")) {
    Write-Host "Cancelled."
    exit 1
  }
}

foreach ($map in $pending) {
  Install-Map $mapsDir $map $sevenZip
}
Write-Host "Updated $($pending.Count) map(s)."
