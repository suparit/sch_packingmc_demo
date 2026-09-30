[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("firmware", "firmware-assets", "simulator", "simulator-assets")]
    [string]$Target = "firmware",

    [string]$TouchGfxRoot = "C:\TouchGFX\4.26.1",
    [string]$CubeIdeRoot = "C:\ST\STM32CubeIDE_2.1.1",
    [ValidateRange(1, 32)]
    [int]$Jobs = 8
)

$ErrorActionPreference = "Stop"
# DEST layout: firmware (formerly "NOXCORE") lives in the sibling project
# 02_HMI_Firmware, one level up from this script (Wab\01_DigitalTwin\..\02_HMI_Firmware),
# not two levels up in a NOXCORE subfolder as in the SOURCE checkout this script came from.
$NoxcoreRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\02_HMI_Firmware")).Path
$make = Join-Path $TouchGfxRoot "env\MinGW\msys\1.0\bin\make.exe"
$mingwBin = Join-Path $TouchGfxRoot "env\MinGW\bin"
$msysBin = Join-Path $TouchGfxRoot "env\MinGW\msys\1.0\bin"
$rubyBin = Join-Path $TouchGfxRoot "env\MinGW\msys\1.0\Ruby30-x64\bin"
$ruby = Join-Path $rubyBin "ruby.exe"

foreach ($required in @($NoxcoreRoot, $make, $mingwBin, $msysBin)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Required build path not found: $required" }
}

$armGcc = Get-ChildItem -LiteralPath $CubeIdeRoot -Recurse -File -Filter arm-none-eabi-gcc.exe -ErrorAction SilentlyContinue |
    Select-Object -First 1
if (-not $armGcc) { throw "arm-none-eabi-gcc.exe not found below $CubeIdeRoot" }
$armBin = $armGcc.Directory.FullName

$requiresAssets = $Target.EndsWith("-assets")
if ($requiresAssets -and -not (Test-Path -LiteralPath $ruby -PathType Leaf)) {
    throw "TouchGFX bundled Ruby not found: $ruby. Do not install global Ruby implicitly; pass the correct -TouchGfxRoot."
}

$oldPath = $env:PATH
$oldAdditionalLibraries = $env:ADDITIONAL_LIBRARIES
try {
    $pathParts = @($armBin, $mingwBin, $msysBin)
    if ($requiresAssets) { $pathParts += $rubyBin }
    $env:PATH = (($pathParts + $oldPath) -join [System.IO.Path]::PathSeparator)
    $env:ADDITIONAL_LIBRARIES = "ws2_32"

    & $armGcc.FullName --version | Select-Object -First 1
    & $make --version | Select-Object -First 1
    if ($requiresAssets) { & $ruby --version }

    switch ($Target) {
        "firmware" {
            # gcc/Makefile forwards only: all clean assets flash intflash. It has no
            # build_executable target, and adding one there would run the sub-makefile with
            # cwd=gcc/ instead of the application root that its relative paths assume.
            # Call the two sub-makefiles directly from the application root instead.
            & $make -C $NoxcoreRoot -r -f gcc/makefile_boot "-j$Jobs" build_executable
            if ($LASTEXITCODE -ne 0) { throw "Boot build failed with exit code $LASTEXITCODE." }
            & $make -C $NoxcoreRoot -r -f gcc/makefile_appli "-j$Jobs" build_executable
        }
        "firmware-assets" {
            & $make -C $NoxcoreRoot -f gcc/Makefile "-j$Jobs" all
        }
        "simulator" {
            $touchGfxProject = Join-Path $NoxcoreRoot "Appli\TouchGFX"
            & $make -C $touchGfxProject -r -f generated/simulator/gcc/Makefile -s "-j$Jobs" build_executable
        }
        "simulator-assets" {
            $touchGfxProject = Join-Path $NoxcoreRoot "Appli\TouchGFX"
            & $make -C $touchGfxProject -f generated/simulator/gcc/Makefile -s "-j$Jobs" all
        }
    }
    if ($LASTEXITCODE -ne 0) { throw "Build failed with exit code $LASTEXITCODE." }
} finally {
    $env:PATH = $oldPath
    $env:ADDITIONAL_LIBRARIES = $oldAdditionalLibraries
}
