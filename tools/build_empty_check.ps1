$ErrorActionPreference = 'Stop'

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
. (Join-Path $PSScriptRoot 'ti_env.ps1')

$exampleRoot = Join-Path $env:MSPM0_SDK_INSTALL_DIR 'examples\nortos\LP_MSPM0G3507\driverlib\empty'
$buildDir = Join-Path $repoRoot 'build\empty_check'
$startup = Join-Path $env:MSPM0_SDK_INSTALL_DIR 'source\ti\devices\msp\m0p\startup_system_files\ticlang\startup_mspm0g350x_ticlang.c'
$compiler = Join-Path $env:TICLANG_ARMCOMPILER 'bin\tiarmclang.exe'

New-Item -ItemType Directory -Force -Path $buildDir | Out-Null

Push-Location $buildDir
try {
    & $env:SYSCONFIG_TOOL `
        --compiler ticlang `
        --product "$env:MSPM0_SDK_INSTALL_DIR\.metadata\product.json" `
        --output . `
        "$exampleRoot\empty.syscfg"

    Remove-Item -LiteralPath @(
        'empty.obj',
        'ti_msp_dl_config.obj',
        'startup_mspm0g350x_ticlang.obj',
        'empty.out',
        'empty.map'
    ) -ErrorAction SilentlyContinue

    $cflags = @(
        "-I$exampleRoot",
        "-I$buildDir",
        '@device.opt',
        '-O2',
        '-gdwarf-3',
        '-mcpu=cortex-m0plus',
        '-march=thumbv6m',
        '-mfloat-abi=soft',
        '-mthumb',
        '-Wall',
        "-I$env:MSPM0_SDK_INSTALL_DIR\source\third_party\CMSIS\Core\Include",
        "-I$env:MSPM0_SDK_INSTALL_DIR\source"
    )

    & $compiler @cflags -c "$exampleRoot\empty.c" -o 'empty.obj'
    & $compiler @cflags -c "$buildDir\ti_msp_dl_config.c" -o 'ti_msp_dl_config.obj'
    & $compiler @cflags -c $startup -o 'startup_mspm0g350x_ticlang.obj'

    & $compiler `
        '-Wl,-u,_c_int00' `
        'empty.obj' `
        'ti_msp_dl_config.obj' `
        'startup_mspm0g350x_ticlang.obj' `
        '-ldevice.cmd.genlibs' `
        "-L$env:MSPM0_SDK_INSTALL_DIR\source" `
        "-L$buildDir" `
        "$buildDir\device_linker.cmd" `
        '-Wl,-m,empty.map' `
        '-Wl,--rom_model' `
        '-Wl,--warn_sections' `
        "-L$env:TICLANG_ARMCOMPILER\lib" `
        '-llibc.a' `
        '-o' `
        'empty.out'

    Get-Item (Join-Path $buildDir 'empty.out')
}
finally {
    Pop-Location
}
