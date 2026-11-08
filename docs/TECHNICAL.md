# Outlast VR - technical overview

*How the mod works inside. For players, see the [main README](../README.md); to build it,
see [BUILD.md](../BUILD.md).*

A 6DOF VR mod for Outlast (2013), built as a `d3d9.dll` proxy loaded next to `OLGame.exe` -
no game-provided modding API exists for this engine build, so the mod hooks Direct3D 9
directly and reads UE3's own object/reflection tables at runtime to find what it needs,
rather than relying on an SDK.

## Provenance - what is inherited and what is this fork's

The proxy architecture, the same-frame stereo renderer and the launcher are **not** this
project's work. They come from the original GPL-3.0 Outlast VR mod by **StrikeZoneVR**,
which this repository continues:

| Inherited from the upstream mod | Added or reworked in this fork |
|---|---|
| The whole `d3d9.dll` proxy approach: hooking D3D9 to capture the frame, the occlusion-query workaround, splitting and submitting one frame per eye | The per-runtime FOV/format negotiation, the edge fill, the re-anchor on a runtime recenter (`[FOVMUTABLE]`, `[STREAMEDGE]`, `[SWAPFMT]`, `[REFCENTER]`) |
| Same-frame native stereo (`ULocalPlayer::CalcSceneView` called twice) | The performance phases 1-7 (see [PERFORMANCE.md](PERFORMANCE.md)) |
| The found-footage camcorder **launcher** (`launcher/`), its boot sequence, scanlines, grain and synthesised sound | Gameplay upper-body IK (`[VISIBLEIK]`) and the hand-interaction layer (`ol_interact.cpp`) |
| Motion controllers as a virtual XInput gamepad, the interaction-profile suggestions | `[PADLATCH]`, the two-pass profile suggestion, the Valve Index stick and menu fixes |
| The 6DOF head-tracking hook and the cinema screen for narrow FOV scenes | The camcorder face pin/raise/lower, the handle magnet, the climbing modes, the document and battery, the prompts |

The branding was removed from the fork (see the README's *Credits*), but the credit stands:
see [LICENSE](../LICENSE) and the README's *Credits* section.

⚠️ Experimental community mod. Not affiliated with Red Barrels. Use at your own risk.

Licensed under [GPL-3.0](../LICENSE).

## What it does

- **Real geometric stereo**, not reprojection - the engine renders both eyes side-by-side
  in one frame (`ULocalPlayer::CalcSceneView` called twice with the viewport rect and eye
  offset rewritten), which the proxy then splits and submits per eye. Getting this stable
  required finding and working around a D3D9 hardware-occlusion-query bug: the query pool
  is built for one view per frame, so a second view read back another query's stale result
  and skipped meshes that were plainly on screen.
- **6DOF head tracking** - position and rotation from OpenXR are injected into the game's
  own view-point hook, gated so only the render pass is affected (AI/aim/audio keep the
  gamepad's answer). Declared FOV to the compositor always matches what the engine actually
  rendered.
- **Motion controllers as a virtual gamepad** - an OpenXR action set is merged into the
  XInput state the game polls, so the game plays as normal with real controllers, glyphs
  included, no physical pad required. Interaction profiles are suggested for Touch, Index, WMR,
  Vive and the Khronos fallback, each in two passes (a runtime that refuses one path refuses the
  whole call, so the optional ones - haptics, touch sensors, Valve's system button - are retried
  without). A press is held for 150 ms in the published snapshot, so the game's own frame rate
  cannot swallow a tap, and a stick that is pushed always walks whatever a touch sensor claims.
- **Gameplay upper-body IK** - both arms follow their matching VR controllers during ordinary
  play, while menus, cinematics, camcorder zoom and native interactions retain authored arm
  animation ownership.
- **Cutscene and menu handling** - narrow-FOV renders (menus, some cutscenes) fall back to a
  big screen in a pitch-black void rather than stretching a narrow frame across the whole
  headset; the screen eases after the head (`[Cinema] HeadLocked=1`, 56 deg at 3.2 m, so it
  lags - 1.1 s - instead of sitting welded to the face) and a soft halo drawn from a one-time
  **16x16 capture** of the menu - with value-noise wobble and grain on top, so it reads as brushed texture instead of
  streaks or 8-bit banding - melts the picture into the black in its own palette. Some cutscene
  cameras render at full width like gameplay instead. The gradient itself is a front-end thing
  (`[Cinema] MenuGlow=1`): the pause/notes/documents menus inside a level are drawn without it.
- **Color/gamma correction** - the game's own brightness calibration and its ~2.2-gamma
  authoring are reconciled with the sRGB frame the compositor expects.
- **Each runtime gets the picture it actually wants** - the projection FOV is declared exactly as
  rendered, and the `fovMutable` flag decides whether that declaration is honoured (SteamVR, VDXR)
  or the frame has to be pre-warped into the runtime's own asymmetric lens frustum (Meta's PC
  runtime: Quest Link / Air Link). The margin the fit leaves is filled with the picture's own edge
  rather than black, so the compositor's reprojection has pixels to pull in when the head turns
  quickly (per axis). A recenter done in
  the headset's own menu is folded into the pose baseline instead of moving the world, and the
  eye-image format is negotiated with the runtime (BGRA8 sRGB wherever it
  is offered - every runtime so far - with the pre-encoded-LUT path for one that has only the
  non-sRGB variant). `[FOVMUTABLE]`, `[STREAMEDGE]`, `[STREAMPOSE]`, `[REFCENTER]`, `[SWAPFMT]` in
  `src/ol_xr.cpp`, explained in [VR-RUNTIMES.md](VR-RUNTIMES.md).

## Experimental areas

- **Hand/arm IK.** Position, elbow targets and controller orientation are written into the visible
  skeletal component's pose after the game finishes composing it (`[VISIBLEIK]`, the final pose
  composer at `base+0x6F8910`). It is enabled for gameplay testing and deliberately yields during
  authored interactions and cinematic cameras. The earlier experiment that tried to drive UE3's
  AnimTree SkelControls was proven inert for the first-person mesh and has been removed.

## Building

See [BUILD.md](../BUILD.md). Short version: Visual Studio 2022 with the C++ workload, then
`scripts\build.bat`. All dependencies are vendored in `third_party/` - nothing else to
install.

## Code map

The mod is one `d3d9.dll` built from nine translation units. Each one owns a layer:

| File | Lines | Owns |
|---|---|---|
| `src/d3d9_proxy.cpp` | ~3400 | The Direct3D 9 proxy itself: the exported entry points, the frame capture and blit, the occlusion-query workaround, the fabricated XInput pad, `MapPadButtons` (the controller layout), mouse-use synthesis, visibility/`[OCCLSKIP]`, the launcher's `--preview` support |
| `src/ol_xr.cpp` | ~7200 | The OpenXR layer: session and swapchains, per-runtime FOV/format negotiation (`[FOVMUTABLE]`, `[SWAPFMT]`), frame pacing and submission, the composition layers, the camcorder HUD strip, the streaming edge fill (`[STREAMEDGE]`), runtime recentering |
| `src/ol_ue3.cpp` | ~8100 | Everything that touches the engine: object/reflection scanning, the `CalcSceneView` stereo hook, the view-point hook, the visible-skeleton pose composer (`[VISIBLEIK]`), the console/profile plumbing, scene-state reflection, the dev console |
| `src/ol_interact.cpp` | ~3900 | Hand interaction: the armed-IK pipeline, the camcorder face pin/raise/lower, the doors and their handle magnet, climbing modes, the battery and document, the prompts |
| `src/ol_menu.cpp` | ~1000 | The in-game ImGui menu (Insert key) and the settings it reads and writes |
| `src/ol_motion.cpp` | ~320 | Physical crouch/lean from the headset pose, and the virtual-crouch pulse |
| `src/ol_sound.cpp` | ~390 | Sound: level-change notification, the camcorder and interaction cues |
| `src/ol_prompts.cpp` | ~230 | The in-headset control hints, including the controller-glyph tables |
| `src/ol_devbridge.cpp` | ~490 | The developer bridge (off by default): scripted input and state snapshots over a socket |

Headers of the same name sit next to each `.cpp`; `src/ol_xr_types.h` holds the OpenXR glue
and `src/ol_mouse_use.h` the mouse-use sampler (a header-only unit so the tests can compile
it).

### Where to look for a given symptom

| Symptom | Start at |
|---|---|
| A controller button does the wrong thing | `MapPadButtons` in `d3d9_proxy.cpp`, then the hint table in `ol_prompts.cpp` |
| A button is ignored in-game | `OLMouseUse::Sample` (`ol_mouse_use.h`), `OLProxy_MouseUseSample`, `MouseUseWatchdog` |
| Black bars at the edge of view | `[STREAMEDGE]` / `OLR_EdgeFill` in `ol_xr.cpp` - see [VR-RUNTIMES.md](VR-RUNTIMES.md) |
| Arms in the wrong place, or fighting the game | `[VISIBLEIK]` in `ol_ue3.cpp`, and the solver in `ol_interact.cpp` |
| Camcorder will not leave the face (or will not stay) | `CamHoldGesture`, `CamRaise`, `Holster`, `OLInteract_CamVisual` |
| Doors, the handle magnet, climbing, lockers | `ol_interact.cpp` (`Doors`, `PhysHang`, `PhysAutoCatch`) |
| Stutter, low frame rate | `[PERF]`, `[HITCH]` in the log; then [PERFORMANCE.md](PERFORMANCE.md) |
| Nothing renders / no head tracking | `[XR]` tags first; then [VR-RUNTIMES.md](VR-RUNTIMES.md) |

## Working on the code

### The log is the primary diagnostic

`%LOCALAPPDATA%\OutlastVR\OutlastVR_Log.txt`, rewritten every launch, off by default
(`[General] Log=1` in `outlastvr.ini`, or the launcher's TOOLS page). Every message carries
a tag such as `[CLIMBDIAG]`, `[DOORPHYS]`, `[FACECAM]`, `[USE]`. The tags and what they mean
are listed in the README's *Logging* section; the player-facing switch is described in
[BUILD.md](../BUILD.md).

**No tag should print per frame.** If you add instrumentation, print on a change, or at most
a few times, and say what the fields mean.

### House rules

- **Change one mechanic at a time**, and measure before and after if it is a performance
  change. [PERFORMANCE.md](PERFORMANCE.md) is the change log; it records what was tried,
  what was measured and what was rejected.
- **Never silently drop a player's input.** If a press cannot be used yet, keep it pending;
  do not consume it. Two separate "button does nothing" bugs came from that.
- **Do not write to game memory you do not own** unless the code already does, and gate it
  behind a scene-state check. One of the field bugs was the door physics pushing the locker
  the player was inside.
- **Prefer removing code over adding a guard** when a change turns out to be wrong; several
  fixes in the changelog are deletions.
- **Match the surrounding style**: `/EHa` SEH guards in the engine-facing units, tags in log
  messages, `static` at file scope, no new dependencies.

### Tests and build

Build instructions, the test suites that need nothing but Python, and the tests that need
`g++`/`mono` are all in [BUILD.md](../BUILD.md).

## Layout

| Path | What's there |
|---|---|
| `src/` | Mod source (the D3D9 proxy, UE3 hooks, OpenXR layer, ImGui menu) |
| `scripts/` | `build.bat` |
| `launcher/` | The `Outlast1VR.exe` launcher (C#, built by `launcher\build_launcher.cmd`) |
| `third_party/` | Vendored MinHook, Dear ImGui and the OpenXR loader, with their licenses |
| `docs/` | How the mod works, runtimes, performance, baseline and open issues |
| `docs/archive/` | Superseded notes, kept for the record |
| `tests/` | The Python test suites (see [BUILD.md](../BUILD.md)) |
| `runtime/` | The release folder: `outlastvr.ini`, `openxr_loader.dll` and the license texts |
| `builds/` | Build output (not in the repo - download the release zip instead) |

## License

GPL-3.0 - see [LICENSE](../LICENSE). Copyright (C) 2026 the Outlast VR authors.

Vendored dependencies keep their own licenses: MinHook (BSD-2-Clause) and Dear ImGui (MIT),
both under `third_party/` alongside their license files. Both are permissive licenses
compatible with GPL-3.0.
