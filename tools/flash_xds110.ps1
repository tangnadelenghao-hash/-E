param(
    [string] $OutFile,
    [string] $Ccxml
)

$ErrorActionPreference = 'Stop'

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
. (Join-Path $PSScriptRoot 'ti_env.ps1')

if (-not $OutFile) {
    $OutFile = Join-Path $repoRoot 'build\empty_check\empty.out'
}

if (-not $Ccxml) {
    $Ccxml = Join-Path $env:UNIFLASH_ROOT 'deskdb\content\TICloudAgent\win\scripting\python\examples\debugger\mspm0g3507\mspm0g3507.ccxml'
}

if (-not (Test-Path -LiteralPath $OutFile)) {
    throw "Output file not found: $OutFile"
}

if (-not (Test-Path -LiteralPath $Ccxml)) {
    throw "CCXML file not found: $Ccxml"
}

& $env:DSLITE --config="$Ccxml" --flash --verify --run --verbose "$OutFile"
