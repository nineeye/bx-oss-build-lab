# PUBLIC SYNTHETIC WINDOWS-ONLY QA. No Ansim commercial source, secrets, user data, or malicious samples.
# Does not grant product Windows PASS. All files/processes disposable, own process IDs only.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$results = [System.Collections.Generic.List[object]]::new()
$root = Join-Path $env:RUNNER_TEMP ('ansim_public_synthetic_' + $env:GITHUB_RUN_ID)
New-Item -ItemType Directory -Force -Path $root | Out-Null
function Require([bool]$condition,[string]$message) { if (-not $condition) { throw $message } }
function Case([string]$name,[scriptblock]$body) {
  try {
    & $body
    $script:results.Add([ordered]@{name=$name;state='PASS';reason='' })
    Write-Host ('CASE_PASS ' + $name)
  } catch {
    $script:results.Add([ordered]@{name=$name;state='FAIL';reason=$_.Exception.GetType().Name })
    Write-Host ('CASE_FAIL ' + $name + ' ' + $_.Exception.GetType().Name)
  }
}
try {
  Case 'WINDOWS_X64_RUNNER' {
    Require ($env:RUNNER_OS -ceq 'Windows') 'not native Windows'
    Require ([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString() -ceq 'X64') 'not x64'
    Require ($env:GITHUB_REPOSITORY -ceq 'nineeye/bx-oss-build-lab') 'wrong repository'
  }
  Case 'UNICODE_SPACES_CONTENT_AND_HASH' {
    $dir = Join-Path $root '한글 경로 and spaces'
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
    $a = Join-Path $dir '합성 fixture.txt'
    $b = Join-Path $dir '검증 copy.txt'
    [IO.File]::WriteAllText($a,'ONLY_BENIGN_PUBLIC_FIXTURE',[Text.UTF8Encoding]::new($false))
    Copy-Item -LiteralPath $a -Destination $b
    Require ((Get-FileHash -LiteralPath $a -Algorithm SHA256).Hash -ceq (Get-FileHash -LiteralPath $b -Algorithm SHA256).Hash) 'hash mismatch'
  }
  Case 'ZIP_EXTRACT_HASH_RESTORE' {
    $src = Join-Path $root '원본 files'
    $dst = Join-Path $root '독립 복원'
    New-Item -ItemType Directory -Path $src -Force | Out-Null
    [IO.File]::WriteAllText((Join-Path $src '한글 data.txt'),'RESTORE_SYNTHETIC_V1',[Text.UTF8Encoding]::new($false))
    $expected=(Get-FileHash -LiteralPath (Join-Path $src '한글 data.txt') -Algorithm SHA256).Hash
    $zip=Join-Path $root 'test-synthetic.zip'
    [IO.Compression.ZipFile]::CreateFromDirectory($src,$zip)
    [IO.Compression.ZipFile]::ExtractToDirectory($zip,$dst)
    $actual=(Get-FileHash -LiteralPath (Join-Path $dst '한글 data.txt') -Algorithm SHA256).Hash
    Require ($actual -ceq $expected) 'restore hash mismatch'
  }
  Case 'NATIVE_PROCESS_EXIT_NONZERO' {
    $p=Start-Process -FilePath $env:ComSpec -ArgumentList @('/d','/c','exit 9') -PassThru -Wait -NoNewWindow
    Require ($p.ExitCode -eq 9) 'exit code lost'
  }
  Case 'OWN_PROCESS_TIMEOUT_AND_CANCEL' {
    $p=Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile','-NonInteractive','-Command','Start-Sleep -Seconds 12') -PassThru -WindowStyle Hidden
    try {
      Require (-not $p.WaitForExit(300)) 'expected child to remain running'
    } finally {
      if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction Stop }
      Require ($p.WaitForExit(4000)) 'owned process still running'
    }
  }
  Case 'LARGE_BENIGN_FILE_SHA256' {
    $large=Join-Path $root 'safe-2MiB.dat'
    $bytes = [byte[]]::new(2*1024*1024)
    [IO.File]::WriteAllBytes($large,$bytes)
    $h=(Get-FileHash -LiteralPath $large -Algorithm SHA256).Hash
    Require ($h.Length -eq 64) 'invalid sha256'
  }
  $failed=@($results | Where-Object {$_.state -ne 'PASS'}).Count
  $report=[ordered]@{
    schema='ANSIM_C442_PUBLIC_WINDOWS_SYNTHETIC_ONLY_V1'
    run_id=$env:GITHUB_RUN_ID
    attempt=$env:GITHUB_RUN_ATTEMPT
    commit=$env:GITHUB_SHA
    native_windows=($env:RUNNER_OS -ceq 'Windows')
    test_count=$results.Count
    failed=$failed
    cases=$results
    commercial_code_uploaded=$false
    actual_ansim_product_tested=$false
    installer_tested=$false
    yara_magika_tested=$false
    restic_kopia_tested=$false
    defender_compat_tested=$false
    customer_release_approved=$false
    conclusion=$(if($failed -eq 0 -and $results.Count -eq 6){'PUBLIC_SYNTHETIC_PASS'}else{'PUBLIC_SYNTHETIC_FAIL'})
  }
  Write-Host ('ANSIM_C442_PUBLIC_QA_RECEIPT ' + ($report|ConvertTo-Json -Depth 8 -Compress))
  if ($failed -ne 0 -or $results.Count -ne 6) { exit 1 }
} finally {
  Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}
