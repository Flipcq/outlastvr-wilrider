# Building from source

*How to compile the mod yourself. For players, see the [main README](README.md);
for how the code works, see [docs/TECHNICAL.md](docs/TECHNICAL.md).*

The build produces one file - `builds\d3d9.dll` - which is the `d3d9.dll` proxy the
game loads. Nothing else is compiled by this script.

## Requirements

| Requirement | Notes |
|---|---|
| **Windows 10 or 11, x64** | the mod is a 64-bit DLL loaded into `OLGame.exe` |
| **Visual Studio 2022** | Community, Professional, Enterprise, or the standalone Build Tools |
| **"Desktop development with C++"** workload | provides `cl.exe`, the Windows SDK and `vswhere.exe` |
| **A copy of Outlast (2013)** | needed to run the result, not to build it |

Nothing else is installed or downloaded. **MinHook** and **Dear ImGui** are vendored
in `third_party/` with their licenses, and the **OpenXR loader** is loaded with
`LoadLibrary` at runtime rather than linked.

The build locates Visual Studio through `vswhere.exe` (which ships with VS2017+), so it
does not assume a specific edition or install drive.

## Build

From the repository root:

```
scripts\build.bat
```

On success the last line is:

```
[build] OK -> "<repo>\builds\d3d9.dll"
```

On failure it prints `[build] compile/link FAILED` and exits with a non-zero code.

## What the script does

Everything below is in `scripts/build.bat`; this is only a map of it.

1. Runs `vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64`
   and calls `vcvarsall.bat x64` from whatever install it finds.
2. Checks that `third_party\minhook\src\hook.c` and `third_party\imgui\imgui.cpp` are
   present, and stops with a clear message if not.
3. Compiles the nine mod translation units plus Dear ImGui (core, DX9 backend) and
   MinHook (hde64, buffer, hook, trampoline) in a single `cl` invocation, with
   `-Fo` sending every `.obj` into `builds\` instead of littering `scripts\`.
4. Links with `/DEF:src\d3d9_proxy.def` (the proxy must export the Direct3D entry
   points) and writes `builds\d3d9.map`.

### Flags that matter, and why

| Flag | Reason |
|---|---|
| `/MT` | static CRT, so the proxy needs no `vcruntime` DLL in the game folder |
| `/LD` | build a DLL |
| `/O2` | optimise; this code runs inside the game's frame |
| `/EHsc` | C++ exceptions; `ol_menu.cpp` needs this and `cl` takes the **last** `/EH*` on the line, so ImGui and the menu are compiled together |
| `/EHa` elsewhere | the SEH guards are `/EHa`-only constructs |
| **no `d3d9.lib`** | the real `d3d9` is resolved with `LoadLibrary`/`GetProcAddress`; statically importing `d3d9.dll` from a DLL *named* `d3d9.dll` would be self-recursive |

Linked system libraries: `user32`, `gdi32`, `ole32`, `windowscodecs`, `shell32`,
`d3d11`, `dxgi`, `xinput`, `winmm`, `synchronization`.

## The launcher (optional)

`Outlast1VR.exe` is a separate C# program, built on its own with the .NET Framework
compiler that ships with Windows:

```
launcher\build_launcher.cmd
```

It is not needed to run the mod - it installs the settings and can start the game.
See [launcher/README.md](launcher/README.md).

## Tests

The test suites in `tests/` are Python scripts. Most of them read the source and assert
on it, so they run **without a headset and without compiling**:

```
python tests\fixes_test.py
python tests\climb_shimmy_test.py
python tests\locker_test.py
python tests\use_press_test.py
python tests\phase12b_test.py
python tests\round3_test.py
python tests\camera_and_sound_test.py
python tests\legacy_fixes_test.py
python tests\perf_pipeline_test.py
python tests\perf_threading_test.py
```

A few (`tests\climb_modes_test.py`, `tests\climb_phys_test.py`, and the perf/XR suites that
compile a fragment) use `g++` to check a self-contained rule; those need a MinGW `g++` on
`PATH` and are the only ones that fail on a machine without one. `launcher_resolution_slider_test.py`
additionally needs `mcs` and `mono`.

There is also `src/ol_devbridge.cpp` (`[Debug] DevBridge=1`), which exposes scripted input
(`key`, `move`, `use`, `teleport`) and state snapshots over a socket, so a whole interaction
can be driven and asserted with no headset attached.

### A rule this repository learned the hard way

`tests/` are written to **assert the behaviour that is wanted**, not the behaviour that
happens to be in the code. If you change a mechanic, change the test to describe the new
intent - and if a test is wrong, delete it rather than weaken it to pass.

## Installing the result

Copy `builds\d3d9.dll` into the game's `Binaries\Win64` folder, next to `OLGame.exe`,
together with everything in `runtime\` (`outlastvr.ini`, `openxr_loader.dll`, and the
license texts). `scripts\build.bat` stages all of it, so `runtime\` is the folder a
release ships.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `[build] vswhere.exe not found` | Visual Studio 2022 (or the Build Tools) is not installed |
| `[build] no VS install with the C++ toolset found` | VS is installed but without the "Desktop development with C++" workload |
| `[build] minhook not found` / `imgui not found` | the `third_party/` folder is missing or was not cloned |
| `error C1083: cannot open include file` | the SDK is missing; repair the VS workload |
| Build succeeds but the game does not load the mod | `d3d9.dll` is not next to `OLGame.exe`, or the game is the 32-bit build |
