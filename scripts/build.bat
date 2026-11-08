@echo off
REM Build the Outlast FlatXR d3d9.dll proxy (x64, static CRT).
REM Output: builds\d3d9.dll
REM Prerequisites: Visual Studio 2022 (Community/Professional/Enterprise or the standalone
REM Build Tools) with the "Desktop development with C++" workload. See BUILD.md.
setlocal
cd /d "%~dp0"

REM Locate any VS2022 install via vswhere (ships with VS2017+ at this fixed path) instead of
REM assuming Community specifically or a fixed drive letter.
set VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe
if not exist "%VSWHERE%" set VSWHERE=%ProgramFiles%\Microsoft Visual Studio\Installer\vswhere.exe
if not exist "%VSWHERE%" ( echo [build] vswhere.exe not found - is Visual Studio 2022 installed? & exit /b 1 )

for /f "usebackq tokens=*" %%i in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set VSINSTALL=%%i
if not defined VSINSTALL ( echo [build] no VS install with the C++ toolset found & exit /b 1 )

call "%VSINSTALL%\VC\Auxiliary\Build\vcvarsall.bat" x64
if errorlevel 1 ( echo [build] vcvarsall failed & exit /b 1 )

set OUTDIR=%~dp0..\builds
if not exist "%OUTDIR%" mkdir "%OUTDIR%"

set SRC=%~dp0..\src

REM MinHook and Dear ImGui are vendored in this repo under third_party/ - nothing to fetch.
set MH=%~dp0..\third_party\minhook
if not exist "%MH%\src\hook.c" ( echo [build] minhook not found at "%MH%" & exit /b 1 )

REM ImGui (core + DX9 backend) for the Insert menu. Compiled straight in; imgui_impl_dx9 uses
REM the game's device pointer.
set IMGUI=%~dp0..\third_party\imgui
if not exist "%IMGUI%\imgui.cpp" ( echo [build] imgui not found at "%IMGUI%" & exit /b 1 )

REM /MT = static CRT so the proxy needs no vcruntime DLL in the game folder.
REM NO d3d9.lib on the link line: the real d3d9 is resolved via LoadLibrary/GetProcAddress.
REM Statically importing d3d9.dll from a DLL *named* d3d9.dll would be self-recursive.
REM d3d11.lib + dxgi.lib for the XR bridge device. The OpenXR loader is LoadLibrary'd at runtime.
REM ol_menu.cpp compiles with C++ EH (/EHsc) via its own translation unit; the rest use /EHa
REM for the SEH guards. cl accepts the last /EH* on the line, so build ImGui + menu together.
REM /Fo sends .obj files into builds/ instead of littering this scripts/ folder.
cl /nologo /O2 /MT /LD /EHsc /I"%MH%\include" /I"%MH%\src\hde" /I"%IMGUI%" /I"%IMGUI%\backends" ^
  /Fo"%OUTDIR%\\" ^
  "%SRC%\d3d9_proxy.cpp" "%SRC%\ol_xr.cpp" "%SRC%\ol_ue3.cpp" "%SRC%\ol_menu.cpp" "%SRC%\ol_motion.cpp" "%SRC%\ol_devbridge.cpp" "%SRC%\ol_interact.cpp" "%SRC%\ol_prompts.cpp" "%SRC%\ol_sound.cpp" ^
  "%IMGUI%\imgui.cpp" "%IMGUI%\imgui_draw.cpp" "%IMGUI%\imgui_tables.cpp" "%IMGUI%\imgui_widgets.cpp" ^
  "%IMGUI%\backends\imgui_impl_dx9.cpp" ^
  "%MH%\src\hde\hde64.c" "%MH%\src\buffer.c" "%MH%\src\hook.c" "%MH%\src\trampoline.c" ^
  /Fe:"%OUTDIR%\d3d9.dll" /link user32.lib gdi32.lib ole32.lib windowscodecs.lib shell32.lib d3d11.lib dxgi.lib xinput.lib winmm.lib synchronization.lib ^
  /DEF:"%SRC%\d3d9_proxy.def" /MAP:"%OUTDIR%\d3d9.map"
if errorlevel 1 ( echo [build] compile/link FAILED & exit /b 1 )

REM The release needs the license texts next to the binaries: the Apache-2.0 loader is
REM redistributed, and GPL-3.0 wants the license to travel with the work. Runtime copies are
REM generated from the single sources so they can never drift apart.
copy /y "%~dp0..\LICENSE" "%~dp0..\runtime\LICENSE.txt" >nul
copy /y "%~dp0..\third_party\third-party-notices.txt" "%~dp0..\runtime\THIRD-PARTY NOTICES.txt" >nul
echo [build] license texts refreshed in runtime\

REM The OpenXR loader is vendored in third_party\openxr\ and ships next to the game; copy
REM the release layout into runtime\ so the release folder is self-contained.
if exist "%~dp0..\third_party\openxr\openxr_loader.dll" (
  copy /y "%~dp0..\third_party\openxr\openxr_loader.dll" "%~dp0..\runtime\openxr_loader.dll" >nul
  echo [build] openxr_loader.dll staged into runtime\
)

echo [build] OK -^> "%OUTDIR%\d3d9.dll"
endlocal
