# Public upstream binaries and synthetic data only.
# Windows native restic 0.19.1 + Kopia 0.23.1 backup/restore QA. NO commercial Ansim product.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$root = Join-Path $env:RUNNER_TEMP ('ansim_c442_oss_win_' + $env:GITHUB_RUN_ID)
$cases = [System.Collections.Generic.List[object]]::new()
New-Item -ItemType Directory -Force -Path $root | Out-Null
function Assert-True([bool]$ok,[string]$message) { if (-not $ok) { throw $message } }
function Check-Tool([string]$exe,[string[]]$arguments,[bool]$expectError=$false) {
  $output = (& $exe @arguments 2>&1 | Out-String).Trim()
  $status = $LASTEXITCODE
  if ($expectError) { Assert-True ($status -ne 0) 'NEGATIVE_TEST_ACCEPTED' }
  else {
    if ($status -ne 0) {
      $safe = $output.Replace($root,'[RUNNER_TEMP]')
      $safe = $safe.Replace($env:USERPROFILE,'[RUNNER_HOME]')
      $safe = ($safe -replace '[\\r\\n]+',' ').Trim()
      if ($safe.Length -gt 450) { $safe=$safe.Substring(0,450) }
      Write-Host ('OFFICIAL_NATIVE_COMMAND_FAILED exit=' + $status + ' detail=' + $safe)
      throw ('NATIVE_EXIT_' + $status)
    }
  }
  return $output
}
function Test-Case([string]$label,[scriptblock]$action) {
  & $action
  $script:cases.Add([ordered]@{name=$label;state='PASS'})
  Write-Host ('CASE_PASS ' + $label)
}
function Get-Official([string]$name,[string]$url,[string]$hash) {
  $archive=Join-Path $root $name
  Invoke-WebRequest -Uri $url -OutFile $archive -TimeoutSec 120 -MaximumRedirection 5
  $actual=(Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
  Assert-True ($actual -ceq $hash) 'OFFICIAL_ARCHIVE_SHA256_MISMATCH'
  $size=(Get-Item -LiteralPath $archive).Length
  Assert-True ($size -gt 1000000 -and $size -lt 50000000) 'OFFICIAL_ARCHIVE_SIZE_REJECTED'
  return $archive
}
function Files-Equal([string]$expectedRoot,[string]$actualRoot) {
  Assert-True (Test-Path -LiteralPath $actualRoot -PathType Container) 'RESTORED_DIRECTORY_MISSING'
  $left=@(Get-ChildItem -LiteralPath $expectedRoot -File -Recurse)
  $right=@(Get-ChildItem -LiteralPath $actualRoot -File -Recurse)
  Assert-True ($left.Count -eq 3 -and $right.Count -eq 3) 'FILE_COUNT_MISMATCH'
  foreach($f in $left) {
    $rel=[IO.Path]::GetRelativePath($expectedRoot,$f.FullName)
    $other=Join-Path $actualRoot $rel
    Assert-True (Test-Path -LiteralPath $other -PathType Leaf) 'RESTORED_FILE_MISSING'
    Assert-True ((Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash -ceq (Get-FileHash -LiteralPath $other -Algorithm SHA256).Hash) 'RESTORED_SHA_MISMATCH'
  }
  Assert-True (Test-Path -LiteralPath (Join-Path $actualRoot '빈 폴더') -PathType Container) 'EMPTY_DIR_MISSING'
}
$stage='INIT'
try {
  Test-Case 'WINDOWS_PUBLIC_RUNNER' {
    Assert-True ($env:RUNNER_OS -ceq 'Windows' -and $env:GITHUB_REPOSITORY -ceq 'nineeye/bx-oss-build-lab') 'RUNNER_OR_REPO_REJECTED'
  }
  $source=Join-Path $root '원본 한글 자료'
  $null=New-Item -ItemType Directory -Force -Path $source,(Join-Path $source 'nested'),(Join-Path $source '빈 폴더')
  [IO.File]::WriteAllText((Join-Path $source '한글 검증.txt'),'PUBLIC_SYNTHETIC_ONLY',[Text.UTF8Encoding]::new($false))
  [IO.File]::WriteAllBytes((Join-Path $source 'nested\binary.bin'),[byte[]](0..255))
  [IO.File]::WriteAllBytes((Join-Path $source 'nested\empty.bin'),[byte[]]@())
  $stage='RESTIC_DOWNLOAD_VERIFY'
  $resticZip=Get-Official 'restic_0.19.1_windows_amd64.zip' 'https://github.com/restic/restic/releases/download/v0.19.1/restic_0.19.1_windows_amd64.zip' 'da948ad707ed690426473aaba2046cd61f8f90f6f0e7dab6be0d5796531de67d'
  Test-Case 'RESTIC_OFFICIAL_PINNED_ZIP_SHA256' { Assert-True (Test-Path -LiteralPath $resticZip -PathType Leaf) 'NO_ZIP' }
  $resticBin=Join-Path $root 'restic_bin'
  Expand-Archive -LiteralPath $resticZip -DestinationPath $resticBin
  $restic=Join-Path $resticBin 'restic_0.19.1_windows_amd64.exe'
  Test-Case 'RESTIC_VERSION_WINDOWS' {
    Assert-True (Test-Path -LiteralPath $restic -PathType Leaf) 'RESTIC_EXE_MISSING'
    $version=Check-Tool $restic @('version')
    Assert-True ($version -match 'restic 0\.19\.1') 'RESTIC_VERSION_MISMATCH'
  }
  $repo=Join-Path $root 'restic_repo'
  $restore=Join-Path $root 'restic_restore'
  $pw=Join-Path $root 'restic_pw.txt'
  [IO.File]::WriteAllText($pw,([guid]::NewGuid().ToString('N')+[guid]::NewGuid().ToString('N')),[Text.UTF8Encoding]::new($false))
  $env:RESTIC_PASSWORD_FILE=$pw
  $env:RESTIC_CACHE_DIR=Join-Path $root 'restic_cache'
  $stage='RESTIC_NATIVE'
  Test-Case 'RESTIC_REPOSITORY_CREATE' { $null=Check-Tool $restic @('--repo',$repo,'init') }
  Test-Case 'RESTIC_BACKUP_SOURCE' { $null=Check-Tool $restic @('--repo',$repo,'backup',$source) }
  Test-Case 'RESTIC_FULL_REPOSITORY_CHECK' { $null=Check-Tool $restic @('--repo',$repo,'check','--read-data') }
  Test-Case 'RESTIC_RESTORE_SHA_AND_EMPTY_DIR' {
    $null=Check-Tool $restic @('--repo',$repo,'restore','latest','--target',$restore)
    $match=@(Get-ChildItem -LiteralPath $restore -Directory -Recurse | Where-Object Name -eq '원본 한글 자료')
    Assert-True ($match.Count -eq 1) 'RESTIC_RESTORE_SOURCE_UNIQUE_MISSING'
    Files-Equal $source $match[0].FullName
  }
  Test-Case 'RESTIC_WRONG_PASSWORD_REJECTED' {
    $wrong=Join-Path $root 'restic_wrong_pw.txt'
    [IO.File]::WriteAllText($wrong,'WRONG_PASSWORD_SYNTHETIC',[Text.UTF8Encoding]::new($false))
    $env:RESTIC_PASSWORD_FILE=$wrong
    try { $null=Check-Tool $restic @('--repo',$repo,'snapshots') $true }
    finally { $env:RESTIC_PASSWORD_FILE=$pw }
  }
  $stage='KOPIA_DOWNLOAD_VERIFY'
  $kopiaZip=Get-Official 'kopia-0.23.1-windows-x64.zip' 'https://github.com/kopia/kopia/releases/download/v0.23.1/kopia-0.23.1-windows-x64.zip' 'f0369d9657dbe47a1b8b6ff4e308c5958a4813b405d4e32ae9d81b3f2b3d8251'
  Test-Case 'KOPIA_OFFICIAL_PINNED_ZIP_SHA256' { Assert-True (Test-Path -LiteralPath $kopiaZip -PathType Leaf) 'NO_ZIP' }
  $kopiaBin=Join-Path $root 'kopia_bin'
  Expand-Archive -LiteralPath $kopiaZip -DestinationPath $kopiaBin
  $kopia=Join-Path $kopiaBin 'kopia-0.23.1-windows-x64\kopia.exe'
  $common=@('--disable-file-logging','--no-use-keyring','--no-persist-credentials','--no-progress')
  Test-Case 'KOPIA_VERSION_WINDOWS' {
    Assert-True (Test-Path -LiteralPath $kopia -PathType Leaf) 'KOPIA_EXE_MISSING'
    $version=Check-Tool $kopia @('--version')
    Assert-True ($version -match '0\.23\.1') 'KOPIA_VERSION_MISMATCH'
  }
  $env:KOPIA_PASSWORD=[guid]::NewGuid().ToString('N')+[guid]::NewGuid().ToString('N')
  $env:KOPIA_CONFIG_PATH=Join-Path $root 'kopia_config'
  $env:KOPIA_CACHE_DIRECTORY=Join-Path $root 'kopia_cache'
  $env:KOPIA_LOG_DIR=Join-Path $root 'kopia_logs'
  $env:USERPROFILE=Join-Path $root 'fake_home'
  $null=New-Item -ItemType Directory -Force -Path $env:USERPROFILE
  $kopiaRepo=Join-Path $root 'kopia_repo'
  $stage='KOPIA_NATIVE'
  Test-Case 'KOPIA_REPOSITORY_CREATE' { $null=Check-Tool $kopia ($common+@('repository','create','filesystem','--path',$kopiaRepo)) }
  $snapshotId=''
  Test-Case 'KOPIA_SNAPSHOT_CREATE' {
    $receipt=Check-Tool $kopia ($common+@('snapshot','create','--json',$source))
    $obj=$receipt|ConvertFrom-Json
    $script:snapshotId=[string]$obj.rootEntry.obj
    Assert-True ($snapshotId -match '^k[0-9a-zA-Z]{10,119}$') 'KOPIA_SNAPSHOT_RECEIPT_INVALID'
    Assert-True ($obj.rootEntry.summ.numFailed -eq 0) 'KOPIA_SNAPSHOT_ERRORS'
  }
  Test-Case 'KOPIA_CONTENT_VERIFY' { $null=Check-Tool $kopia ($common+@('content','verify','--full')) }
  Test-Case 'KOPIA_SNAPSHOT_VERIFY' { $null=Check-Tool $kopia ($common+@('snapshot','verify','--verify-files-percent=100')) }
  Test-Case 'KOPIA_RESTORE_SHA_AND_EMPTY_DIR' {
    $target=Join-Path $root 'kopia_restore'
    $null=Check-Tool $kopia ($common+@('snapshot','restore',$snapshotId,$target))
    Files-Equal $source $target
  }
  Test-Case 'KOPIA_WRONG_PASSWORD_REJECTED' {
    $oldPass=$env:KOPIA_PASSWORD;$oldCfg=$env:KOPIA_CONFIG_PATH
    $env:KOPIA_PASSWORD='WRONG_PUBLIC_SYNTHETIC'
    $env:KOPIA_CONFIG_PATH=Join-Path $root 'kopia_bad_config'
    try { $null=Check-Tool $kopia ($common+@('repository','connect','filesystem','--path',$kopiaRepo)) $true }
    finally { $env:KOPIA_PASSWORD=$oldPass;$env:KOPIA_CONFIG_PATH=$oldCfg }
  }
  Test-Case 'SYNTHETIC_SOURCE_UNMODIFIED' {
    Assert-True ([IO.File]::ReadAllText((Join-Path $source '한글 검증.txt')) -ceq 'PUBLIC_SYNTHETIC_ONLY') 'SOURCE_CHANGED'
    Assert-True ((Get-Item -LiteralPath (Join-Path $source 'nested\binary.bin')).Length -eq 256) 'SOURCE_BINARY_CHANGED'
  }
  Write-Host ('ANSIM_C442_UPSTREAM_NATIVE_RECEIPT '+(@{result='PASS';count=$cases.Count;failed=0;run_id=$env:GITHUB_RUN_ID;restic='0.19.1';kopia='0.23.1';native_windows=$true;upstream_only=$true;ansim_product_tested=$false;customer_release_approved=$false;cases=$cases}|ConvertTo-Json -Compress -Depth 5))
} catch {
  Write-Host ('ANSIM_C442_UPSTREAM_NATIVE_BLOCKED '+(@{result='BLOCKED_OR_FAIL';stage=$stage;passed=$cases.Count;reason_type=$_.Exception.GetType().Name;run_id=$env:GITHUB_RUN_ID;native_windows=$true;ansim_product_tested=$false;customer_release_approved=$false}|ConvertTo-Json -Compress))
  exit 1
} finally {
  Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}
