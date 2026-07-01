$ErrorActionPreference = 'Stop'

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
. (Join-Path $PSScriptRoot 'ti_env.ps1')

$projectRoot = Join-Path $repoRoot 'firmware\oled_ssd1306'
$buildDir = Join-Path $repoRoot 'build\oled_ssd1306'
$startup = Join-Path $env:MSPM0_SDK_INSTALL_DIR 'source\ti\devices\msp\m0p\startup_system_files\ticlang\startup_mspm0g350x_ticlang.c'
$compiler = Join-Path $env:TICLANG_ARMCOMPILER 'bin\tiarmclang.exe'

New-Item -ItemType Directory -Force -Path $buildDir | Out-Null

Push-Location $buildDir
try {
    & $env:SYSCONFIG_TOOL `
        --compiler ticlang `
        --product "$env:MSPM0_SDK_INSTALL_DIR\.metadata\product.json" `
        --output . `
        "$projectRoot\oled_ssd1306.syscfg"

    Remove-Item -LiteralPath @(
        'main.obj',
        'ti_msp_dl_config.obj',
        'startup_mspm0g350x_ticlang.obj',
        'oled_ssd1306.out',
        'oled_ssd1306.map'
    ) -ErrorAction SilentlyContinue

    $cflags = @(
        "-I$projectRoot",
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

    & $compiler @cflags -c "$projectRoot\main.c" -o 'main.obj'
    & $compiler @cflags -c "$buildDir\ti_msp_dl_config.c" -o 'ti_msp_dl_config.obj'
    & $compiler @cflags -c $startup -o 'startup_mspm0g350x_ticlang.obj'

    & $compiler `
        '-Wl,-u,_c_int00' `
        'main.obj' `
        'ti_msp_dl_config.obj' `
        'startup_mspm0g350x_ticlang.obj' `
        '-ldevice.cmd.genlibs' `
        "-L$env:MSPM0_SDK_INSTALL_DIR\source" `
        "-L$buildDir" `
        "$buildDir\device_linker.cmd" `
        '-Wl,-m,oled_ssd1306.map' `
        '-Wl,--rom_model' `
        '-Wl,--warn_sections' `
        "-L$env:TICLANG_ARMCOMPILER\lib" `
        '-llibc.a' `
        '-o' `
        'oled_ssd1306.out'

    Get-Item (Join-Path $buildDir 'oled_ssd1306.out')
}
finally {
    Pop-Location
}
