# OutlastVR Walrider

> **PC VR only.** The game runs on your PC and streams to your headset through SteamVR, Virtual Desktop, or Quest Link / Air Link. It does **not** run standalone on a Quest.

## Credits

This is an unofficial, fan-made project that brings **Outlast (2013) to PC VR**, transforming the original horror experience into an immersive virtual reality experience with **full head and hand tracking**.

This fork is based on the original [OutlastVR project by StrikeZoneVR](https://github.com/StrikeZoneVR-hub/OutlastVR). All credit for the original mod goes to its creator.

The launcher was originally created by **StrikeZoneVR**. This fork keeps its original look, with a few minor visual adjustments to the launcher.

## Installation

1. Download the latest release

2. Find your Outlast installation folder. In Steam, right-click **Outlast**, select **Manage**, then **Browse local files**.

3. Open `Binaries\Win64`.

4. Copy all files from the downloaded ZIP into that folder, alongside `OLGame.exe`.

5. Start your VR runtime (SteamVR, Virtual Desktop, or Quest Link / Air Link) and put on your headset.

6. Run `Outlast1VR.exe` and select **PLAY IN VR**.

Run the launcher again after Steam updates or verifies Outlast, because Steam can reset the game's settings files.

> **Windows blocked the launcher?** Windows Defender may incorrectly flag `Outlast1VR.exe` as a potential threat. If you encounter this warning, verify that the executable came from the official project release and review the detection before deciding whether to allow it. Running as administrator does not bypass this warning.

---

# Outlast Head Bob Remover

Removes **head bob** (camera sway) from Outlast, with an option to also remove the camera sway caused by **breathing** when Miles is standing still.

The patcher edits `OLGame.upk` in the `CookedPCConsole` folder, creates a backup of the original file, and allows you to restore it later.

## How to Use

1. Close Outlast

2. Extract `Outlast-HeadBob-Remover.exe` to:  
   `...\Steam\steamapps\common\Outlast\OLGame\CookedPCConsole\`

   (`OLGame.upk` must be in the same folder as the patcher.)

3. Run `Outlast-HeadBob-Remover.exe`.

4. Choose the desired options and click **Apply Changes**.

5. Launch the game.

6. To restore the original file, use **Restore Original File**.

For more information, visit the [Outlast Head Bob Remover GitHub repository](https://github.com/Flipcq/outlast-head-bob-remover)

---

# Controls


## Quest Controllers
| Left controller                                  | Right controller                                         |
| ------------------------------------------------ | -------------------------------------------------------- |
| Stick: Walk                                      | Stick: Turn (smooth or snap)                             |
| Stick click: Sprint                              | Stick click: Night vision; hold: raise camcorder to face |
| X: Crouch / Drop                                 | A: Jump / Climb / Vault                                  |
| Y: Reload camcorder battery                      | B: Use / Open / Close / Pick up                          |
| Trigger: Lean left / Look back                   | Trigger: Lean right / Look back                          |
| Menu: Pause                                      | Grip at right hip: Take camcorder                        |
| Left grip + Y: Documents                         | Both stick clicks: Recenter                              |
| Left grip + X: Notes                             | Grip at left shoulder: Confidential document             |
| Left trigger + Y: Notebook (documents and notes) | Left grip + Menu: **VR Settings**                        |

## Camcorder Controls

With the camcorder raised, push the right stick up or down to zoom.

Hold the right stick click (**R3**) to raise the camcorder using the game's original animation. It stays at Miles's face while your hand rests naturally.

Hold R3 again, or squeeze the right grip while the camcorder is at your face, to lower it. A short R3 click toggles night vision.

## Valve Index Controllers

Valve Index controllers use the same control layout, adapted to their native buttons:

- A/B buttons on both controllers

- Both thumbsticks

- Both grips

- Both triggers

The Valve system button is reserved for SteamVR and cannot be detected by the mod. Therefore, pause and **VR Settings** are assigned to a firm press on the left trackpad:

- Firm press on the left trackpad: Pause

- Left grip + firm press on the left trackpad: **VR Settings**

All other controls remain the same. Quest controller bindings are unchanged.

---

# New Features: How to Use Them

## Camcorder Handling

The camcorder can be physically picked up from its holster on Miles's right hip and brought up to his face.

You can also use **R3** to raise the camcorder in front of your face or lower it again. While the camcorder is raised, press R3 to lock it in place without having to keep holding it. Once locked, you can still physically grab the camcorder with your hand and move it away from your face.

## Doors

Interact with doors using your hands. Push heavy doors open directly, or grab their handles to pull them open or push them closed.

Door interactions use the same input as **Button B** (Left Mouse Button in the original game).

## Manual Battery Reloading

Physically reload the camcorder by taking a replacement battery from Miles's left hip and bringing it to the camcorder.

The reload uses the game's original battery replacement animation. Both arms and controller grips are temporarily locked during the process to prevent hand tracking from interfering with Miles's animation.

## Physical Document Interaction

Grab the document folder from Miles's left shoulder and hold it in front of you to access the document menu. The folder must remain in view for a few seconds to trigger the menu.

## Climbing

Climbing has three available modes: **Button Only**, **Hybrid**, and **Physical**.

- **Button Only:** Climbing is performed using the assigned button controls.

- **Hybrid:** Combines button-based climbing with physical hand interactions.

- **Physical:** Climbing is performed entirely with your hands. Analog-stick climbing is disabled for ladders, so you must physically use your hands to climb them. When jumping toward a higher platform, Miles automatically grabs the ledge with his left hand. Pressing the left controller's grip button releases control back to the player, allowing you to move your hand freely. You can also climb using both hands.

Ledge walking works the same way in all three modes: while hanging from a ledge, the walk stick moves Miles sideways along it using the game's animation, as long as **both** hands are holding the ledge. If one hand is released, the stick does nothing. Releasing the left grip while the right hand is not holding the ledge keeps Miles's left hand attached; he cannot fall from that position.

## Picture Quality and Upscaling

Two settings in the launcher's **VR SETTINGS → PICTURE** page decide how sharp the picture is and how hard the mod has to work. They are linked: the upscaler only matters when the render resolution is below 100%.

### Render resolution

**Render resolution** (`[Render] RenderScale`, menu: **Render resolution**) is the size the game draws each eye at, as a percentage of what your headset's runtime recommends. It ships at **100%** — the full recommended size.

Lowering it is the single biggest performance lever: 80% draws 64% of the pixels, and the missing pixels are reconstructed by the upscaler on the way to the headset. Use it when Outlast stutters; leave it at 100% if the frame rate is comfortable, because everything below 100% is reconstruction, not information.

This setting only applies in AUTO eye-resolution mode. In MANUAL you choose the pixel size directly and the resolution percentage is ignored.

### Upscaling

**Upscaling** (`[XR] Upscaler`, menu: **Upscaling**) chooses *how* that reconstruction is done. There are three modes, and the default is **FSR 1**:

| Mode        | What it does                                                                                                                                                                                                                                            |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **CLASSIC** | The earliest path: bilinear enlargement plus a 4-tap unsharp mask. Cheapest, softest, and it shows stair-stepping on thin edges.                                                                                                                        |
| **SHARP**   | Catmull-Rom bicubic resampling (9 bilinear taps, clamped to the 2×2 source texels so its negative lobes cannot ring), followed by contrast-adaptive sharpening — it sharpens hard where local contrast is low and backs off near edges that would halo. |
| **FSR 1**   | AMD's **FidelityFX Super Resolution 1.0** — the 12-tap EASU edge-adaptive enlargement with its dering step, followed by the RCAS clip-solve sharpener. Best picture per frame of the three.                                                             |

**Why FSR 1 is the default.** EASU is edge-aware: it reconstructs an edge along its dominant direction instead of blurring across it, which is exactly the failure mode of bilinear enlargement on this game's straight architecture — door frames, pipes, railings, the camcorder's own edges. RCAS then restores the detail EASU's enlargement softened, in a way that *clips* the sharpening against the local neighbourhood rather than adding to it — the clip-solve formulation — which is what keeps it from producing the white halos a plain unsharp mask does. In practice it means you can run a lower render resolution, or the same one with a cleaner picture, than either of the other two modes allows.

**It costs a little more GPU than SHARP** — a few extra taps per pixel in the blit — which is why SHARP exists at all for very tight frame times. The difference is small enough that FSR 1 is the default.

**It does nothing at 100%.** There is nothing to enlarge, so the cost is not paid and the picture is untouched. Leave it on FSR 1 and raise Render resolution to 100% if you would rather not use an upscaler at all — you get the native render without changing this setting.

### Sharpening

**Sharpening** (`[XR] Sharpness`, menu: **Sharpening**) ships **OFF**. It drives the sharpener of whichever upscaler is active: RCAS when FSR 1 is selected, the CAS-style pass in SHARP, and the unsharp mask in CLASSIC. With FSR 1 its effect is gentler than the number suggests, because RCAS already clips against local contrast. Raise it a step at a time; past about 0.5 fine texture starts to sparkle.

### Suggested combinations

| Situation                         | Render resolution | Upscaling                                                     |
| --------------------------------- | ----------------- | ------------------------------------------------------------- |
| Comfortable frame rate            | 100%              | **FSR 1** (no effect, no cost)                                |
| Occasional stutter                | 80–90%            | **FSR 1**                                                     |
| Tight frame times on an older GPU | 70–80%            | **FSR 1**, then try **SHARP** if you need the last few frames |
| You dislike any sharpening halo   | 100%              | **CLASSIC**, Sharpening 0                                     |

One interaction worth knowing: raising **Edge margin** (`[Stream] EdgeOverscanDeg`) spreads the same pixel budget over more degrees in order to remove the black bars on a fast head turn. That costs sharpness by design, so if the picture looks soft after turning Edge margin up, raise the render resolution rather than the sharpening.

---

# Improvements & Fixes

## 1. Bug Fixes

- **Shortcut Fixes:** Corrected shortcut assignments.

- **Camcorder Positioning:** Fixed incorrect camcorder positioning and alignment.

- **Door Closing Controls:** Fixed an issue that caused door-closing input to be registered unreliably.

- **Lens Flare Rendering:** Fixed an issue that caused lens flare effects to remain visible through walls.

- **Input Reliability:** Improved the reliability of jump and door interaction inputs to prevent occasional missed button presses. This improvement has not yet been fully tested.

## 2. Gameplay Improvements

- **Door Interaction:** Improved hand positioning and grip on door handles, added angular acceleration to door movement, and made doors easier to open. Door opening and closing sounds were also added.

- **Camcorder Handling:** Introduced a hybrid mode that allows players to hold the camcorder up to their face or lock it in position without physically holding it.

- **Head Bob Removal:** Removed head bobbing using a standalone patcher.

- **Camcorder HUD:** Redesigned the camcorder display to closely match the original game's HUD, with multiple customization options available in the launcher.

- **Battery Reload Animation:** Fixed the initial animation skip when starting a battery reload, ensuring the reload animation plays from the beginning.

## 3. New Features

- **Manual Battery Reloading:** Added physical battery interaction, allowing players to grab a replacement battery from Miles's left hip and bring it to the camcorder to reload.

- **Physical Document Interaction:** Added physical document handling, allowing players to grab the document folder from Miles's left shoulder and open the document menu by looking at it for a few seconds.

- **Head-Relative Menu Positioning:** The menu now dynamically follows the direction the player is looking, keeping it aligned with the headset's orientation for a more natural VR interaction.

- **Freeze Rotation:** Added an optional camera rotation lock. When enabled, the camera remains fixed in its current orientation while the right analog stick rotates Miles's body independently, allowing movement in different directions without changing the camera's orientation.

---

# Optimization

## Optimization Progress

**100% — 7 of 7 phases completed**

`███████` 7/7

| Phase   | Description                               | Status    |
| ------- | ----------------------------------------- | --------- |
| Phase 1 | Instrumentation & Performance Diagnostics | Completed |
| Phase 2 | CPU-Side Optimizations                    | Completed |
| Phase 3 | Threading & Synchronization               | Completed |
| Phase 4 | Memory & GPU Optimization                 | Completed |
| Phase 5 | UE3 Visibility Optimization               | Completed |
| Phase 6 | Content Optimization                      | Completed |
| Phase 7 | OpenXR Pipeline Optimization              | Completed |

The seven optimization phases are complete. This does not mean every investigated optimization is enabled or included in the shipped configuration: some features remain disabled by default, while others were investigated but not implemented. Their individual status is noted below.

## Phase 1 — Instrumentation & Performance Diagnostics

Established a performance profiling foundation to identify CPU/GPU bottlenecks and rendering inefficiencies.

- CPU/GPU utilization and frame-time monitoring.

- Draw call instrumentation.

- Visibility and rendering pipeline profiling.

- Unreal Engine profiling using:

  - `stat splitscreen`

  - `stat initviews`

  - `stat scenerendering`

## Phase 2 — CPU-Side Optimizations

Reduced redundant processing and unnecessary per-frame computations through targeted hooks, caching, and adaptive update strategies.

- **D-1:** `**Hook_SkelUpdate**` — Optimized skeletal update processing to reduce unnecessary CPU overhead.

- **D-2:** `**Hook_GetViewPoint**` — Optimized viewpoint retrieval and associated per-frame processing.

- **D-3: FOV Caching** — Avoided redundant Field of View calculations through caching.

- **D-4: Night Vision Flashlight Caching** — Reduced repeated Night Vision flashlight state and data processing.

- **A4: Flag Snapshots** — Introduced state snapshots to reduce repeated flag evaluation and synchronization overhead.

- **A5: BackBuffer Caching** — Avoided unnecessary repeated BackBuffer retrieval operations.

- **A7: Adaptive Object Scanning** — Implemented adaptive object scanning to reduce unnecessary scene-wide processing.

- **A6: Intelligent HUD Updates** — Reduced redundant HUD updates by refreshing elements only when necessary.

## Phase 3 — Threading & Synchronization

Reduced synchronization overhead and improved coordination between the XR processing and rendering pipelines.

- **A1: XR Thread Scheduling** — Optimized XR thread timer handling and thread priority.

- **A2: Spin-Wait Replacement** — Replaced CPU-intensive spin-wait synchronization with `WaitOnAddress`, allowing threads to wait more efficiently without continuously consuming CPU cycles.

- **A8: Mirror Rendering Decoupling** — Removed mirror rendering operations from the main render thread to reduce rendering-thread contention.

## Phase 4 — Memory & GPU Optimization

Removed per-frame GPU copies and rebuilt the bridge's resource handling so the same picture reaches the headset with less memory traffic.

- **A3: Shared Frame Sampled In Place** — `SharedFrameDirect`. The bridge samples the game's shared frame where it is instead of copying it into its own upload texture first. That copy was 36 MB per frame (approximately 2.6 GB/s at 72 FPS) for no benefit: the shared frame already has the format and size the eye blit reads, and the slot it comes from is not handed back before the draw. If the driver refuses this path, that frame automatically falls back to copying.

- **B5: Texture View Cache** — `ViewCache`. Keeps one `ID3D11ShaderResourceView` per texture, retained and released on every swapchain rebuild, instead of creating and releasing a view for every blit.

- **B8: Direct Swapchain Draw** — `DirectSwapchain`. The eye blit's shader draws directly into the acquired OpenXR swapchain image, removing the scratch image and `CopyResource` (another 36 MB per frame). The view format and colour space are taken from the image itself; if the driver refuses this path, it falls back to the scratch draw and copy. **Disabled by default while it is still being validated.**

- **Virtual-Texture Shadowing** — The game's textures keep a copy in ordinary memory, as the original game's D3D9 path did, so loading a new area no longer stalls the game while waiting on the graphics card.

- **D3D9Ex Path** — `[XR] D3D9Ex=1` runs the game on a real D3D9Ex device so frames stay on the GPU at the game's own speed. `[XR] D3D9Ex=0` falls back to the D3D9On12 + `ZeroCopy` path.

## Phase 5 — UE3 Visibility Optimization

Corrected the occlusion queries and precomputed visibility that the two-view frame got wrong, and removed duplicated visibility work between the eyes.

The engine decides what to draw using two per-frame systems: hardware occlusion queries and baked precomputed visibility. Both were designed for **one** view per frame. `OcclForce=1` handled this by disabling culling; the optimizations below address the underlying two-view issues.

- **B1: One Answer Per Eye** — `OcclPerEye`. Every occlusion query keeps a real answer **per eye**, and a read never waits: a query the GPU has not finished answers with that eye's previous frame. **Disabled by default; force-visible behaviour remains the default.**

- **C1: Visibility Result Reuse** — `VisReuse`. The second eye reuses the first eye's per-box verdicts in call order instead of drawing its own test boxes, guarded by the union frustum so both views cull the same region.

- **C2: Union Frustum** — `UnionFrustum` / `UnionNearUU`. Uses one frustum for both eyes, enabling visibility result reuse instead of using one frustum per eye.

- **Occlusion Proof** — `OcclProve` / `OcclGuard`. A `culled` answer is only trusted when the value provably describes the box the engine just drew, never one drawn by the other view or one already read during the current cycle. `OcclGuard` applies the same proof and hold to the engine's own reads.

- **Two-Answer Hold** — `OcclHold`. Requires two consecutive `culled` answers before a prop may disappear, preventing props from blinking in front of the player.

- **Shared PVS** — `PvsShare`. The second eye reuses the first eye's precomputed-visibility answer.

- **Draw List Comparison** — `[Perf] DrawFingerprint`. Compares the two eyes' draw sequences per frame (`[PERF] draw lists: N/M identical`), providing a measurement for the optimizations above.

## Phase 6 — Content Optimization

A dedicated content profile is applied once gameplay is live and reapplied after a level loads. It removes or reduces content that a two-view frame cannot afford to draw twice.

- **D.4: Particle LOD** — `scale set ParticleLODBias`. Raises the particle LOD bias because particles can require roughly three times the work of a mesh draw.

- **D.5: Detail Mode** — `scale set DetailMode`. Prevents high-detail props from rendering in a two-view frame.

- **Draw-Distance Scale** — `scale set MaxDrawDistanceScale`. Reduces distant decoration.

- **Optional Cuts** — `scale set DynamicShadows False` / `scale set Decals False`. The PERFORMANCE+ profile also disables dynamic shadows and decals.

- **B7: Launcher Profile** — `[Content] Profile` with `Commands1` / `Commands2` / `Restore`. FULL DETAIL (the original visual quality), PERFORMANCE, and PERFORMANCE+ are selectable in the launcher. Each line is a `scale set` console command; no offsets or patching are used. The full restore runs when the profile changes.

## Phase 7 — OpenXR Pipeline Optimization

Shortened the path from the game's frame to the headset's display step, and added the upscaler and black-border fix.

- **B6: FSR1 Upscaling** — `[XR] Upscaler=2` (menu: **FSR 1**). FidelityFX FSR1 in the blit shader: 12-tap EASU with dering plus the RCAS clip solve, seam-clamped and used only when enlarging. Below 100% **Render resolution** the game renders smaller while the headset still receives its full eye resolution; at 100% it steps aside and costs nothing. It ships as the default of the three modes — see [Picture Quality and Upscaling](#picture-quality-and-upscaling) for what each one does and when to pick another.

- **B9: Edge Overscan** — `[Stream] EdgeOverscanDeg` (menu: **Edge margin**). Renders N degrees beyond the lens and declares the wider frustum, so the compositor's reprojection can pull pixels instead of showing black during a fast turn. Ships at **2.0 deg**, the low end of the useful 2–4 range: it removes the bars at a cost in sharpness the eye will not usually notice, and the launcher can take it to 0 for the sharpest picture or up to 6 if the bars persist. The blit target and declared frustum use the same function so they cannot disagree.

- **Black-Border Fix** — `[Stream] EdgeFill`. The margin inside each eye image is stretched from the image's own edge instead of being left black, at no additional cost.

- **Dual-Eye Rendering in One ViewFamily** — Both eyes are rendered in a single frame pass (the stereo path), which is the target of the two-view optimization work. `[PERF] draws per eye` reports the left/right split so duplication can be measured.

- **B5: Composition Layer Count** — `[PERF] composition layers` reports the number of layers submitted per frame, making it possible to monitor and reduce the count.

- **Investigated, Not Implemented** — B3 (blits before `xrWaitFrame`) and B4 (one swapchain with `arraySize=2`) were investigated but deliberately **not implemented**. Both require a restructure that cannot be verified without a headset; the reasons are recorded in the developer notes.

---

# Logging & Troubleshooting

OutlastVR includes an optional logging system that writes session information to a plain text file named `**OutlastVR_Log.txt**`, stored in `%LOCALAPPDATA%\OutlastVR\`, alongside the launcher's settings file.

The log is overwritten every time the game starts and records timestamped events with their respective sources. Timestamps are measured in seconds from launch, making it easier to identify when and where an issue occurred.

Logging runs in the background to avoid interfering with gameplay. It also records every frame that takes longer than 40 ms.

### Enable or Disable Logging

Everything is managed through the launcher:

1. Run `**Outlast1VR.exe**`.

2. Open **VR SETTINGS** and go to the **TOOLS** tab.

3. Under **General**, toggle **Write log files** on or off.

4. Select **Open the log folder** to open `%LOCALAPPDATA%\OutlastVR` in Windows Explorer.

The log file appears after the next time you play.

The setting is stored in the `[General] Log` key in `outlastvr.ini` (`1` = enabled, `0` = disabled). Changes take effect the next time the game starts.

The in-game VR SETTINGS menu does not include this option; logging must be managed through the launcher.

For normal gameplay, logging is best left disabled and enabled only when troubleshooting issues.

## Reporting a Problem

Logging is off by default, so enable it before reproducing an issue. Without a log, diagnosing a problem may be more difficult.

1. Enable logging in the launcher.

2. Play until the problem occurs.

3. Close the game.

4. Attach `%LOCALAPPDATA%\OutlastVR\OutlastVR_Log.txt` to your report. Include where in the game the issue happened and how your headset is connected.

---

# Building from Source

Use **Visual Studio 2022** with the C++ workload, then run `scripts\build.bat`.

- BUILD.md — Build instructions, the test suites, and how to install the result.

- docs/TECHNICAL.md — How the mod works, the code map and the house rules for working on it.

- docs/ROADMAP.md — Open bugs and feature requests.

- docs/PERFORMANCE.md — Developer performance change log.

---

# Disclaimers

The project uses the following open-source components:

- [MinHook](https://github.com/TsudaKageyu/minhook) (BSD-2-Clause)

- [Dear ImGui](https://github.com/ocornut/imgui) (MIT)

- [Khronos OpenXR Loader](https://github.com/KhronosGroup/OpenXR-SDK) (Apache-2.0)

The full text of every one of these licenses is collected in a single file, `THIRD-PARTY NOTICES.txt`, which ships with the release next to `d3d9.dll` and `openxr_loader.dll`. The source lives in [`third_party/third-party-notices.txt`](third_party/third-party-notices.txt); the module itself is vendored unmodified in `third_party/openxr/`.

*Outlast is a game by Red Barrels. This is an unofficial, fan-made mod. It is not affiliated with or endorsed by Red Barrels, and it does not include any game files. You need your own copy of Outlast.*

---

# License

GPL-3.0 — Copyright (C) 2026 the Outlast VR authors. This fork keeps the license of the project it is based on; upstream attribution and third-party notices are in LICENSE.

The vendored libraries keep their own licenses (see `third_party/`).
