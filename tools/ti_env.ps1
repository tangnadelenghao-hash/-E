$env:MSPM0_SDK_INSTALL_DIR = 'D:\TI\mspm0-sdk-proxy'
$env:TICLANG_ARMCOMPILER = 'D:\TI\ti-cgt-armllvm_4.0.0.LTS\ti-cgt-armllvm_4.0.0.LTS'
$env:SYSCONFIG_ROOT = 'D:\TI\sysconfig_1.28.0'
$env:SYSCONFIG_TOOL = Join-Path $env:SYSCONFIG_ROOT 'sysconfig_cli.bat'
$env:UNIFLASH_ROOT = 'D:\TI\uniflash_9.5.0'
$env:DSLITE = Join-Path $env:UNIFLASH_ROOT 'dslite.bat'

$toolPaths = @(
    (Join-Path $env:TICLANG_ARMCOMPILER 'bin'),
    $env:SYSCONFIG_ROOT,
    $env:UNIFLASH_ROOT
)

$env:Path = ($toolPaths + ($env:Path -split ';' | Where-Object { $_ })) -join ';'
