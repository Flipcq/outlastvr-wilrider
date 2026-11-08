# VR runtimes, streaming and the submission path

*Everything that happens at the boundary between the mod (`src/`, `runtime/outlastvr.ini`,
`launcher/`) and the OpenXR runtime driving the headset: **SteamVR**, **Virtual Desktop (VDXR)** and
**Meta/Oculus PC runtime (Quest Link / Air Link)**. It is both the player-facing explanation - why the
picture behaves differently on each runtime, and what the "black vertical bars when I turn my head
quickly" actually are - and the technical reference for working on that boundary.*

Engine-side hooks (UE3, the D3D9 proxy) are referenced only where they touch a runtime.

Conventions used throughout: log tags appear as `[OLVR][TAG]`; ini keys as `[Section] Key=value`;
file:line references point at `src/`.

**Contents**

- **1-8 - Streaming and the black bars**: what the mod submits, why the runtimes differ, the black
  vertical bars, what the mod does about them, what the player can do, runtime recentering, the
  swapchain format, and how to report a problem.
- **9-19 - The runtime reference**: what a runtime is in this mod, how each one behaves, per-runtime
  quirks handled in code, format negotiation, the runtime-relevant ini keys, dependencies, testing
  without a headset, known incompatibilities and how to diagnose them, and where the log is.
- **Appendix - Diagnostics registry**: the entry format for recording a runtime event (date, phase,
  runtime, headset, log tags, evidence, conclusion).

---

> **Who wrote what, here.** The submission path itself (one projection layer per eye, the
> swapchain capture) is inherited from the upstream **StrikeZoneVR** mod. Everything this
> document describes about *the runtimes* - the per-runtime FOV decision (`[FOVMUTABLE]`),
> the edge fill (`[STREAMEDGE]`), the pose lead, the recenter re-anchor (`[REFCENTER]`) and
> the format negotiation (`[SWAPFMT]`) - was written for this fork. See
> [TECHNICAL.md](TECHNICAL.md#provenance---what-is-inherited-and-what-is-this-forks).

## 1. What the mod actually submits

The game renders one frame per eye with D3D9. The proxy copies each eye into an OpenXR swapchain
image and hands the runtime **one projection layer**, twice per frame: a declared `XrPosef` (where
the head was when the picture was drawn), a declared `XrFovf` (the angle the picture covers) and
the rectangle of the image it lives in.

Everything the headset does afterwards happens **in the runtime's compositor**, on the headset or
on the PC depending on the runtime. The mod has no further say.

## 2. Why the runtimes are not interchangeable

OpenXR lets an application declare whatever pose and FOV it wants, but it only *suggests* them to
the runtime:

> "However, applications may submit an `XrCompositionLayerProjectionView` which has a different
> view or FOV than that from `xrLocateViews`. In this case, the runtime will map the view and FOV
> to the system display appropriately."
> — OpenXR specification, quoted in the Khronos forum thread
> [Oculus runtime ignores Projection Layer View's pose](https://community.khronos.org/t/oculus-runtime-ignores-projection-layer-views-pose/110078)

Whether that mapping honours the declaration is reported per view configuration as
`XrViewConfigurationProperties::fovMutable`. Three real-world answers:

| Runtime | `fovMutable` | What it does with the mod's layer | Consequence |
|---|---|---|---|
| **Virtual Desktop (VDXR)** | true | honours the declared pose and FOV, supports quad and cylinder layers ([VDXR developer notes](https://github.com/mbucchia/VirtualDesktop-OpenXR/wiki/Developers)) | the mod's own symmetric ~88-100 deg render is shown as declared - this is what every build was tuned on |
| **SteamVR** | true | honours the FOV, but a projection view declared **wider** than its own per-eye frustum is rejected and the compositor shows nothing; its scene state machine also needs a projection layer under any quad/overlay frame | works, but every frame has to be cropped to the intersection with SteamVR's frustum, and quad-only frames (menus, cinema screen) need the black placeholder layer |
| **Meta PC runtime (Quest Link / Air Link)** | **false** | discards the declared FOV **and** the per-view pose; it composites the submitted rectangle into its own asymmetric lens frustum (Quest 3 through Link: -54/+40 deg, +44/-55 deg) | a symmetric render gets stretched/displaced per eye (the "double vision" and "a screen on each eye" reports), so the picture has to be pre-warped into the runtime's frustum before it is submitted |

Both quirks are already handled in `src/ol_xr.cpp`, and  asks the runtime instead of
guessing from its name: `[FOVMUTABLE]` reads `fovMutable` and feeds `OLR_DecideFitFrustum()`, which
turns `[FITFRUSTUM]` on exactly for the runtimes that throw the declaration away. Any runtime that
has never been tested now gets the correct treatment from its own answer.

What is left in the log tells you which path ran:

```
[OLVR][XRRUNTIME] name='SteamVR' metaFovCrop=0 steamVrFovCrop=1
[OLVR][FOVMUTABLE] the runtime says the projection FOV is mutable (a declared FOV is honoured)
[OLVR][FITFRUSTUM] off (auto, by the runtime's fovMutable flag), perEyePose=off
```

## 3. The black vertical bars during a fast head turn

They are not a bug in the mod's capture. Every PC VR runtime **reprojects** the frame it was given:
between the moment the game drew the picture and the moment the panel is lit, the head moved, so
the compositor warps the image to the latest pose at scan-out (SteamVR "reprojection"/motion
smoothing, Meta ASW, VD's SSW). A warp can shift and rotate pixels; it cannot invent what was never
drawn. From the Khronos [frame submission guide](https://github.com/KhronosGroup/OpenXR-Guide/blob/main/chapters/frame_submission.md):

> "If the app is rendering for the same pose that it submits with `xrEndFrame`, the XR system will
> be able to compensate by reprojecting the content in the correct place in the world with **just
> black pulled in on the sides**."

Turn faster or drop frames and the black crescent grows; stop and it closes again. The same report
appears for every VR app that runs under its headset's refresh rate, e.g. the
[MSFS/Reverb G2 thread](https://forums.flightsimulator.com/t/vr-black-flickering-borders-in-reverb-g2-when-turning-head/362184)
where the borders vanish when the frame rate goes up, and it is why
[ALVR was asked to render a wider FOV than the headset needs](https://github.com/alvr-org/ALVR/issues/1656)
in streaming setups.

Three things make it worse here, in order of how much they matter:

1. **The game presents below the headset's refresh.** Outlast is a 2013 UE3 title: 50-70 fps is
   normal, while a Quest 3 runs 72/90/120 Hz. Every second displayed frame is then the runtime's
   own synthesis, and each synthesis is a warp of up to a full frame of head motion. This is the
   dominant factor.
2. **Nothing outside the submitted frustum exists.** With the render matching the lens exactly
   (which is what `[Render] WideFov=1` does) there is *no* margin for the warp to pull from, so the
   first degree of unexpected motion is already black. Real engines keep a few degrees of rendered
   overscan for exactly this; OpenXR has no way to ask for it, so the margin inside the eye image
   is the only place it can live.
3. **The link itself.** Air Link/VD encode, ship and decode every frame: 20-40 ms on top of
   everything else, and the pose has to be predicted further ahead. On Quest Link the runtime also
   has `ASW`, which [halves the frame rate and synthesises the missing frames](https://developers.meta.com/horizon/documentation/native/pc/asynchronous-spacewarp/)
   when the GPU cannot keep up: ASW is the single most visible producer of edge artifacts on Link.

## 4. What this mod does about it 

- **`[Stream] EdgeOverscanDeg`  - the missing half, and the strongest lever.**
  Everything below fills a margin that already exists. On a runtime that honours the declared FOV
  there is no such margin: the picture *is* the eye image, so the first degree of unexpected motion
  is already black. This key makes the camera render **N degrees beyond the lens on every edge** and
  declares that wider frustum, so the warp has real pixels to pull instead of black. The lens sees
  exactly the angles it always did; the extra ring is outside it. `0` = off (byte-identical to the
  old frustum), `2-4` is the useful range. It costs sharpness (the same pixels spread over more
  degrees), which is the whole trade; it needs `LensFit` on, because LensFit is what feeds the
  frustum this widens. Menu: **Edge margin**. The widening is applied in angle space and used by
  *both* the blit and the layer declaration, so the two can never disagree and the picture can never
  shrink inside the lens.
- **`[Stream] EdgeFill=1`** - in `[FITFRUSTUM]` mode the eye image spans the runtime's lens
  frustum while the picture only covers the part the game actually rendered; the rest used to be
  cleared to black, and *that* black is what the warp smears into view. The blit now extends the
  picture's own edge texels over that margin (the same affine map, sampled with a clamping
  sampler), so the margin is a stretched continuation of the world instead of a black bar. The
  visible picture stays exactly where it was - only the previously-black margin changes. A picture
  that covers less than three quarters of the eye **on that axis** (a menu, a deliberately narrow
  camera) keeps its black field on that axis: stretching that far would be a smear, not an overscan
  margin. The decision is per axis because an asymmetric lens (Quest 3 through Link: -54/+40 deg)
  leaves a wide margin on one side and none on the other, and testing both axes together threw the
  free one away. `OLR_EdgeFill()`.
- **A diagnosis in the log when the fill is skipped**: `[OLVR][STREAMEDGE] kept black around the
  picture: it covers 58% of the eye horizontally and 55% vertically ...`, four times at most. If
  the bars are back, that line says whether the picture was too narrow for the fill or something
  else is going on.
- **`[Stream] PoseLeadPeriods`** - how many display periods ahead of the compositor's display time
  the pose handed to the camera is predicted. `1` is the shipped behaviour. `0` removes the lead
  entirely, for A/B testing a "the world lags behind my head" report. A runtime with a deep queue
  over a link (Quest Air Link at high bitrate) can benefit from `2`, but `1` is the default.
- **`[FOVMUTABLE]`** - the fit decision described in section 2, now taken from the runtime's own
  answer instead of its name.
- **A diagnosis in the log.** When the game delivers well under the headset's refresh, the mod says
  so once every 30 s, five times at most, with the numbers and the setting that fixes it:
  `[OLVR][STREAM] the game is handing over 58 fps to a 90 Hz headset, so most displayed frames are the runtime's own reprojection ...`.

## 5. What the player can do (biggest win first)

| Action | Why |
|---|---|
| Set the headset refresh to what the game can actually hold - 72 Hz, or 60/72 on a weak GPU | removes the synthesised frames that produce the bars at all |
| Quest Link / Air Link: turn **ASW off** (Oculus Debug Tool, "Asynchronous SpaceWarp" = Disabled) | ASW's synthesised frames are the artifact's worst case |
| SteamVR: disable **Motion Smoothing** for this app | the same mechanism, SteamVR's own version |
| Lower the eye resolution (`VR SETTINGS > PICTURE`, AUTO 85-90 % or a MANUAL size) | the game renders less per eye and holds a higher frame rate |
| Wireless: 5 GHz / Wi-Fi 6 AP in the same room, PC on cable; Air Link bitrate 100-150 Mbps, Virtual Desktop 60-90 Mbps | every millisecond on the link is extra warp |
| Keep `[Stream] EdgeFill=1` | what is left of the effect becomes a slight smear instead of a black bar |
| Raise `[Stream] EdgeOverscanDeg` to 2-4 (menu **Edge margin**) | renders real pixels outside the lens for the warp to pull from - the only cure when the runtime honours the declared FOV. Slightly softer picture |

## 6. When the runtime recenters itself (SteamVR "Recenter", the Oculus menu's "Reset View")

This is the other half of "it does not work well on SteamVR alone / on Link", and it has nothing to
do with streaming quality. Both runtimes let a player move the *origin of the play space* from
their own menu. OpenXR reports that as `XR_TYPE_EVENT_DATA_REFERENCE_SPACE_CHANGE_PENDING`, with
`poseInPreviousSpace` = the pose of the **new** origin expressed in the **old** space.

Until  this mod dropped that event on the floor. Everything it renders is relative to a
baseline it captured once, so a runtime recenter changed the raw pose, the relative pose changed
with it, and the asylum rotated or slid around the player - the exact opposite of what the button
says. On Quest Link that fights the "Reset View" in the menu; on SteamVR alone, where that
dashboard recenter is the only recenter a player has, it reads as "recenter does nothing / head
tracking is broken".

The fix is exact rather than a re-zero, so the runtime can move the player's chair without moving
their world:

```
baseQ' = conj(q) * baseQ          baseP' = Rot(conj(q), baseP - t)
```

which makes `conj(baseQ') * (c_new - baseP') == conj(baseQ) * (c_old - baseP)` for every point -
i.e. every relative pose the camera and the layer poses are built from is **identical** before and
after. Applied when the compositor reaches the `changeTime` the runtime named, logged as
`[OLVR][REFCENTER]`. If a runtime sends the event without a pose, the mod falls back to its own
recenter (re-zero), which is the only sane answer without geometry. `tests/stream_edge_fill_test.py`
checks the invariance numerically, including the orientation transform (the part that is easy to
get wrong and looks fine until you turn).

## 7. The swapchain format the runtime prefers (and what the mod now asks for)

OpenXR's performance guidance is to use the first colour format the runtime lists from
`xrEnumerateSwapchainFormats`, because anything else makes the compositor run a conversion pass
over every eye every frame - frame time, and therefore latency, spent outside the game's control.
Until  this mod asked for `B8G8R8A8_UNORM_SRGB` unconditionally and never looked.

**It now negotiates, within a box narrow enough to be safe:**

- `BGRA8` sRGB is still requested first, and on every runtime this mod has run on (VDXR, SteamVR,
  Oculus/Meta) it is offered - so nothing changes there, not one pixel.
- If a runtime does **not** offer it but does offer plain `BGRA8` UNORM, that one is requested
  instead. It is the *same byte layout*, so every `CopyResource`/`CopySubresourceRegion` in the
  pipeline stays format-legal, and the only thing that moves is where the sRGB transfer happens:
  an sRGB render target encodes on write, a UNORM one does not, so the blit's gamma LUT is built a
  second time carrying **pre-encoded** values (`SrgbFromLinear`) and bound for exactly those draws.
- If the runtime offers neither, the shipped request stands and the runtime substitutes, exactly as
  every earlier build did.
- Nothing else is ever selected: `R8G8B8A8` would swap red and blue in the non-shader fallback copy
  and 10-bit formats would need a different readback, so both are ignored.

The escape hatch back to the old behaviour is `[XR] RuntimeFormat=0`. The log says what happened:

```
[OLVR][SWAPFMT] the runtime offers 8 swapchain formats, first: 91,87,29,28,... | BGRA8_SRGB offered, BGRA8 offered
[OLVR][SWAPFMT] eye images will be B8G8R8A8_UNORM, not sRGB: the blit writes sRGB-encoded bytes itself ...
[OLVR][GAMMAFMT] eye swapchain: asked fmt=87 (B8G8R8A8_UNORM), runtime allocated fmt=87 (exact match)
```

The sRGB transfer pair is checked numerically in `tests/stream_edge_fill_test.py` (round trip to
1e-4, endpoints clamped), because a wrong constant there is a picture that is one gamma step off -
the exact failure this whole section exists to avoid.

## 8. Reporting it

`OutlastVR_Log.txt` already answers the questions that matter, so attach it:

- `[XRRUNTIME]` / `[FOVMUTABLE]` / `[FITFRUSTUM]`: which runtime, and which path was taken.
- `[OLVR][REFCENTER]`: whether you used the headset's own recenter, and whether the mod could
  compensate for it.
- `[OLVR][SWAPFMT]`: the formats the runtime offers (per-runtime performance/gamma differences).
- `[OLVR][STREAM]`: the game's frame rate against the headset's refresh.
- `[OLVR][XRTIMING]`: the compositor loop's cost and the real display step (13.9 ms = 72 Hz,
  11.1 = 90 Hz; steps of 22.2 ms mixed in mean every second frame is synthesised).
- `[OLVR][XRSUBMIT]`: the FOV and the rect actually declared per eye.

---

## 9. What a "runtime VR" is in this mod

The mod is a `d3d9.dll` proxy dropped next to `OLGame.exe`. Each frame the game renders both eyes side-by-side in one D3D9 frame (`ULocalPlayer::CalcSceneView` called twice, viewport rect and eye offset rewritten). The proxy splits the SBS frame, copies each eye into an OpenXR swapchain image, and submits to the runtime:

- one `XrCompositionLayerProjectionView` per eye — declared `XrPosef` (where the head was when the picture was drawn), declared `XrFovf` (the angle the picture covers), and the image rect;
- quad layers for narrow-FOV renders (menus, some cutscenes), shown as a world-locked "cinema screen" in a black void instead of being stretched across the headset.

After submission the mod has no further say: warping, reprojection and display are the runtime's compositor's job, on the headset or on the PC depending on the runtime. Everything a player sees on the headset after the submit point is the runtime's behaviour.

The runtime in use is detected from the registry `HKLM\SOFTWARE\Khronos\OpenXR\1\ActiveRuntime` (the launcher shows it as Virtual Desktop, SteamVR, Meta / Oculus or Other). OpenXR is loaded dynamically from `openxr_loader.dll` next to the game exe — no SDK link-time dependency.

---

## 10. Supported runtimes and how each one behaves

OpenXR lets an application declare whatever pose and FOV it wants, but it only *suggests* them to the runtime. Whether the declaration is honoured is reported per view configuration as `XrViewConfigurationProperties::fovMutable`. Three real-world answers:

| Runtime | `fovMutable` | What it does with the mod's layer | Consequence for the mod |
|---|---|---|---|
| **Virtual Desktop (VDXR)** | true | Honours the declared pose and FOV; supports quad and cylinder layers | The mod's own symmetric ~88-100 deg render is shown as declared — this is what every build was tuned on. |
| **SteamVR** | true | Honours the FOV, but a projection view declared **wider** than its own per-eye frustum is rejected (compositor shows nothing); its scene state machine also needs a projection layer under any quad/overlay frame | Every frame must be cropped to the intersection with SteamVR's frustum; quad-only frames (menus, cinema screen) need a black placeholder layer. |
| **Meta PC runtime (Quest Link / Air Link)** | **false** | Discards the declared FOV **and** the per-view pose; composites the submitted rectangle into its own asymmetric lens frustum (Quest 3 through Link: -54/+40 deg, +44/-55 deg) | A symmetric render gets stretched/displaced per eye ("double vision", "a screen on each eye"); the picture must be pre-warped into the runtime's frustum before submission. |

These answers are read live from `fovMutable` — the mod queries the runtime instead of guessing from its name (`[FOVMUTABLE]` → `OLR_DecideFitFrustum()` turns `[FITFRUSTUM]` on exactly for runtimes that throw the declaration away). Any runtime never tested now gets the correct treatment from its own answer.

Log evidence of which path ran:

```
[OLVR][XRRUNTIME] name='SteamVR' metaFovCrop=0 steamVrFovCrop=1
[OLVR][FOVMUTABLE] the runtime says the projection FOV is mutable (a declared FOV is honoured)
[OLVR][FITFRUSTUM] off (auto, by the runtime's fovMutable flag), perEyePose=off
```

---

## 11. How the mod submits each frame

- D3D9 renders both eyes side-by-side in one frame (`ULocalPlayer::CalcSceneView` called twice with rewritten viewport rect and eye offset ±halfIPD along the view-right vector).
- The proxy splits the SBS frame and copies each eye into an OpenXR swapchain image.
- One projection layer per eye is submitted: declared `XrPosef`, declared `XrFovf`, image rect. The declared FOV must match what was actually rendered — Outlast's FOV is ini-driven and changes at runtime (running FOV, camcorder zoom), so the live value is read per frame, never assumed to be 90.
- Narrow-FOV renders fall back to a big screen in a pitch-black void (cinema screen), head-locked with ease (`[Cinema] HeadLocked=1`, 56 deg at 3.2 m, ~1.1 s lag); a one-time 16x16 capture of the menu with value-noise wobble and grain melts the picture into black.
- Gamma: the game's brightness calibration and its ~2.2-gamma authoring are reconciled with the sRGB frame the compositor expects.
- Per-axis eye-image margin: filled with the picture's own edge rather than black (`[Stream] EdgeFill=1`), so the compositor's reprojection has pixels to pull in during fast head turns.

---

## 12. Per-runtime quirks handled in code (`src/ol_xr.cpp`)

| Tag | Meaning | Controlled by |
|---|---|---|
| `[XRRUNTIME]` | Active runtime name and per-runtime quirk flags (`metaFovCrop`, `steamVrFovCrop`) | detected from `ActiveRuntime` registry |
| `[FOVMUTABLE]` | Whether the runtime honours the declared projection FOV | `OLR_DecideFitFrustum()` from `fovMutable` |
| `[FITFRUSTUM]` | Whether the runtime's own asymmetric frustum fit is applied (Meta path) | `[XR] FitRuntimeFrustum=1` |
| `[SWAPFMT]` | Swapchain formats the runtime offers and which one was chosen | `[XR] RuntimeFormat=1` |
| `[REFCENTER]` | Headset-menu recenter folded into the pose baseline instead of moving the world; fallback to own re-zero if the runtime sends the event without a pose | runtime-dependent |
| `[STREAMEDGE]` / `EdgeFill` | Eye-image margin filled with the picture's own edge instead of black | `[Stream] EdgeFill=1` |
| `[STREAMPOSE]` | Head pose lead ahead of display timing | `[Stream] PoseLeadPeriods=1` |
| `[XRTIMING]` | Compositor loop cost and real display step (13.9 ms = 72 Hz, 11.1 ms = 90 Hz; steps of 22.2 ms mixed in mean every second frame is synthesised) | periodic `[PERF]` line |
| `[XRSUBMIT]` | The FOV and rect actually declared per eye | `src/ol_xr.cpp` submit path |
| `[STICKCENTER]` | Stick rest-point learning (Valve Index / Pimax "cannot walk" fix) | `src/ol_xr.cpp` |
| `[PADLATCH]` | Discrete buttons held 150 ms in the published snapshot so slow game polls cannot miss a press | `src/ol_xr.cpp` |

---

## 13. Swapchain format negotiation

OpenXR performance guidance: use the first colour format the runtime lists from `xrEnumerateSwapchainFormats` — anything else costs a compositor conversion pass on every eye, every frame.

- `BGRA8` sRGB (`B8G8R8A8_UNORM_SRGB`) requested first; offered by every runtime this mod has run on (VDXR, SteamVR, Oculus/Meta) → nothing changes, not one pixel.
- If a runtime does **not** offer sRGB but does offer plain `BGRA8` UNORM (same byte layout), that one is requested instead. Every `CopyResource`/`CopySubresourceRegion` stays format-legal; only where the sRGB transfer happens moves — an sRGB render target encodes on write, a UNORM one does not, so the blit's gamma LUT is built a second time carrying pre-encoded values (`SrgbFromLinear`).
- If the runtime offers neither, the shipped request stands and the runtime substitutes (pre-1.2.1 behaviour).
- `R8G8B8A8` would swap red and blue in the non-shader fallback copy, and 10-bit formats would need different readback — both are ignored, never selected.
- Escape hatch: `[XR] RuntimeFormat=0` restores the old unconditional `B8G8R8A8_UNORM_SRGB` request.

Log example:

```
[OLVR][SWAPFMT] the runtime offers 8 swapchain formats, first: 91,87,29,28,... | BGRA8_SRGB offered, BGRA8 offered
[OLVR][SWAPFMT] eye images will be B8G8R8A8_UNORM, not sRGB: the blit writes sRGB-encoded bytes itself ...
[OLVR][GAMMAFMT] eye swapchain: asked fmt=87 (B8G8R8A8_UNORM), runtime allocated fmt=87 (exact match)
```


---

## 14. Configuration — runtime-relevant keys in `runtime/outlastvr.ini`

```ini
[XR]
Enabled=1               ; 0 = run flat on the monitor with the mod loaded, no headset
NativeEyeResolution=1   ; submit at the OpenXR runtime's recommended per-eye resolution
Sharpness=0.000
Upscaler=2              ; 1 = bicubic enlargement + adaptive sharpening; 0 = Test 28 bilinear
SubmitThread=1
FitRuntimeFrustum=1     ; pre-warp into the runtime's frustum when fovMutable=false (Meta path)
RuntimeFormat=1         ; ask the runtime which eye-image format it offers (0 = pre-1.2.1 behaviour)
TextureShadow=1         ; textures keep a copy in ordinary memory (no area-load stalls)
D3D9Ex=1                ; extended D3D9 device; frames shared with the headset on the GPU (~74 fps path)
D3D9On12=1              ; D3D9-on-D3D12 layer; used when D3D9Ex=0
ZeroCopy=1              ; hand each frame to the headset on the graphics card (no CPU readback)
AsyncReadback=1         ; fallback copy path when ZeroCopy cannot be used
PaceToHeadset=1         ; one game frame per headset frame when the game is faster than the headset
FramePoseLatch=1        ; tag each frame with the exact pose it was drawn with (not the next frame's pose)

[Stream]
EdgeFill=1              ; fill eye-image margin with the picture's own edge instead of black
EdgeOverscanDeg=2.0     ; degrees of picture rendered beyond the lens (overscan trades sharpness for no black edges)
PoseLeadPeriods=1       ; display refreshes ahead for head-pose prediction

[Render]
AutoEyeResolution=1     ; 1 = AUTO (OpenXR recommended size per eye); 0 = MANUAL
EyeWidth / EyeHeight    ; MANUAL dimensions, 480-4096 per axis in 8-pixel steps
HighResRender=1         ; windowed backbuffer at 2x the runtime's recommended eye size

[Perf]
OcclForce / OcclusionSkip / OcclGuard / UnionFrustum / VisReuse / PvsShare / OcclPerEye / ...
                        ; visibility/culling switches — full story in docs/PERFORMANCE.md
```

The launcher's VR SETTINGS tape writes some of these back (`[Content] Profile`, `[Render] AutoEyeResolution`, `EyeWidth`, `EyeHeight`, ranges, etc.) via `WritePrivateProfileString`, preserving file comments. Before shipping a release, `outlastvr.ini` must have no `[Debug]` keys.

---

## 15. Dependencies

| Component | Role | Source / license |
|---|---|---|
| `openxr_loader.dll` | Official Khronos OpenXR loader (x64), loaded dynamically next to `OLGame.exe` | KhronosGroup/OpenXR-SDK, Apache-2.0 — **not built by this repo**, obtained separately |
| `d3d9.dll` | The mod itself — D3D9 proxy next to the exe | built by `scripts\build.bat` → `builds\d3d9.dll` |
| MinHook | vtable hooking (`CreateDevice`, `Present`, `Reset`) | `third_party/minhook`, BSD-2-Clause |
| Dear ImGui | In-headset settings menu (INSERT / grip + Menu) | `third_party/imgui`, MIT |

Build: Windows 10/11 x64, Visual Studio 2022 with "Desktop development with C++", then `scripts\build.bat` (single `cl.exe` invocation, `/MT`, no solution/CMake). Output: `builds\d3d9.dll` — build output, **not committed to the repo**.

Deploy: copy `builds\d3d9.dll` and everything in `runtime\` (`outlastvr.ini`, `openxr_loader.dll`, the license texts) into `<Outlast install>\Binaries\Win64\`, next to `OLGame.exe`.

---

## 16. Testing without a headset (runtime-relevant)

- **SteamVR null headset**: a real OpenXR session with no headset. Enable the `null` driver and set `forcedDriver=null` in SteamVR settings; point the mod at it per process with `[Debug] XrRuntimeJson=<SteamVR>\steamxr_win64.json`, leaving the system OpenXR runtime unchanged.
  - Pitfalls: with no room setup, SteamVR opens Room Setup and closes the game — create a standing chaperone first. Standby stops rendering, making numbers meaningless — set a long screen-off timeout and `pauseCompositorOnStandby=false`. Launching through Steam while SteamVR is already running can hang on a hidden VR prompt.
- **DevBridge** (`[Debug] DevBridge=1`): commands written to `%LOCALAPPDATA%\OutlastVR\dev\cmd.txt` — screenshot (`snap`, `xrsnap`), press pad buttons, fake both controllers (`hands 1`), wave the head, read/write UE3 objects via reflection (`src/ol_devbridge.cpp`).
- **Tests/** compile the real `src/` code against synthetic Windows/OpenXR stubs (needs `g++`) and assert logic rules: stick/trigger shaping, pad press timing, interaction-profile bindings, climb decisions, camcorder gestures, mouse/Use path. They prove logic, not hardware.

---

## 17. Known runtime incompatibilities and diagnosis

| Symptom | Likely runtime cause | Where to look / fix |
|---|---|---|
| Black vertical bars at the edge of view on a fast head turn | The runtime reprojects a frame with no spare margin; SteamVR/VDXR honour the declared FOV so there is no spare edge; Meta frustum misalignment stretches the symmetric render | `[Stream] EdgeFill=1`, `EdgeOverscanDeg=2.0`; see `docs/VR-RUNTIMES.md` §3 |
| "Double vision" / "a screen on each eye" | Meta PC runtime discards declared FOV/pose and composites into its own asymmetric lens frustum | `FitRuntimeFrustum=1`; confirm via `[FOVMUTABLE]` / `[FITFRUSTUM]` in the log |
| Blank / missing frames on SteamVR | A projection view declared wider than SteamVR's per-eye frustum is rejected | Crop to the frustum intersection; check `[XRRUNTIME]` `steamVrFovCrop` |
| Picture one gamma step off | Wrong swapchain format / sRGB transfer pair | `[SWAPFMT]`; `[XR] RuntimeFormat=0` escape hatch |
| Headset-menu recenter moves the world instead of recentering | The runtime sent the recenter event without a usable pose | `[REFCENTER]`; the mod falls back to its own re-zero |
| Cannot reach pause menu / settings (Valve Index) | `/input/system/click` may be unavailable for application use | Left trackpad force (`/input/trackpad/force`) bound as the menu on Index; `system/click` stays bound where delivered |
| Refused interaction-profile path drops the whole binding call | One path outside a runtime's allowlist fails `xrSuggestInteractionProfileBindings` for the whole call | Every profile suggested twice: full set, then without refusable paths (haptics, stick touch, system button, trackpad force) |
| Stick reads zero after being pushed (Index / Pimax) | Runtime reports "no thumb" while the stick is held down → wrong rest point learned | Stick past 0.45 always passes; no rest point is learned from a pushed stick (`[STICKCENTER]`) |
| A tap on jump/use never reaches the game | A press started and ended inside a slow frame; UE3 polls the fabricated pad on its own tick | `[PADLATCH]` — every discrete button held 150 ms in the published snapshot |


---

## 18. Log location and how to read it

- Player log: `%LOCALAPPDATA%\OutlastVR\OutlastVR_Log.txt` — overwritten every launch. Tagged with `[OLVR][TAG]` per feature; the launcher's VR SETTINGS has "Open the log folder".
- `[General] Log=0` in `outlastvr.ini` turns file logging off completely (no file created, no writer thread, nothing formatted). Turn it on before reporting a problem.
- Boot line `BUILD=` identifies the mod build.
- Always attach the log for runtime-related bugs, plus headset model and connection type (SteamVR, Virtual Desktop or Quest Link / Air Link).

---

---

# Appendix - Diagnostics registry

Every runtime-related event is recorded here: initialization failures, per-frame submit anomalies, format negotiation results, recenter behaviour, black-bar reports and per-runtime regressions. Reference `file:line` in `src/ol_xr.cpp` and `src/d3d9_proxy.cpp` where relevant.

### How to add an entry

| Field | What to write |
|---|---|
| Date | YYYY-MM-DD |
| Phase | initialization | execution | test | interaction | shutdown |
| Runtime | SteamVR / VDXR / Meta (Quest Link / Air Link) / null headset / unknown |
| Headset | model and connection (e.g. Quest 3 over Virtual Desktop) |
| Log tags | `[OLVR][TAG]` values observed (e.g. `[XRRUNTIME]`, `[FOVMUTABLE]`, `[FITFRUSTUM]`, `[SWAPFMT]`, `[REFCENTER]`, `[STREAMEDGE]`, `[STREAMPOSE]`, `[XRTIMING]`, `[XRSUBMIT]`) |
| Evidence | Concrete observation (log lines, ini values, behaviour, repro steps) |
| Assessment | Normal / anomaly / incompatibility / under investigation |
| Next action | Fix attempted, setting changed, test to run, file:line to inspect |

### Baseline entry (2026-07-11 — context established)

| Date | 2026-07-11 |
|---|---|
| Phase | initialization |
| Runtime | All supported (SteamVR, VDXR, Meta) |
| Headset | Meta Quest 3 streaming from PC via Virtual Desktop (primary dev/test headset) |
| Log tags | `[XRRUNTIME]`, `[FOVMUTABLE]`, `[FITFRUSTUM]`, `[SWAPFMT]`, `[REFCENTER]`, `[STREAMEDGE]`, `[STREAMPOSE]`, `[XRTIMING]`, `[XRSUBMIT]` |
| Evidence | - `openxr_loader.dll` (official Khronos x64 loader) loaded dynamically next to `OLGame.exe`; no SDK link-time dependency.<br>- Runtime detected from `HKLM\SOFTWARE\Khronos\OpenXR\1\ActiveRuntime`; launcher shows Virtual Desktop / SteamVR / Meta / Other.<br>- VDXR and SteamVR report `fovMutable=true` (declared FOV honoured); Meta PC runtime reports `false` (declared FOV/pose discarded, frustum fit applied).<br>- Swapchain negotiation: `BGRA8` sRGB requested first, offered by every runtime seen so far; `BGRA8` UNORM fallback; `R8G8B8A8` and 10-bit never selected.<br>- `[XR] RuntimeFormat=1` enables negotiation; `RuntimeFormat=0` restores pre-1.2.1 behaviour.<br>- Frame pose latched per drawn frame (`FramePoseLatch=1`); one game frame per headset frame (`PaceToHeadset=1`).<br>- `[Stream] EdgeFill=1` fills eye-image margin with picture edge instead of black; `EdgeOverscanDeg=2.0` renders extra degrees beyond the lens.<br>- Recenter from the headset menu folded into pose baseline (`[REFCENTER]`); fallback re-zero if the runtime sends no pose. |
| Assessment | Baseline: all three runtimes behave as documented in `docs/VR-RUNTIMES.md`. No anomaly at context-establishment time. |
| Next action | Use this section to log every runtime-related event from now on: initialization failures, per-frame submit anomalies, format negotiation results, recenter behaviour, black-bar reports, per-runtime regressions. Reference file:line in `src/ol_xr.cpp` and `src/d3d9_proxy.cpp` where relevant. |

---

## Related documentation

- `docs/TECHNICAL.md` - how the mod works inside (D3D9 proxy, OpenXR layer, engine hooks)
- `docs/PERFORMANCE.md` - the optimization work, the measurement protocol and the `[PERF]` log fields
- `docs/PROJECT-BASELINE.md` - baseline measurements and the change history, test by test
- `docs/ROADMAP.md` - open issues and what is known about each
- `runtime/outlastvr.ini` - every setting with its default and the engine addresses
- `BUILD.md` - building and deploying
- `launcher/README.md` - launcher operation and VR SETTINGS
- `docs/archive/` - superseded notes, kept for the record
- `src/ol_xr.cpp`, `src/d3d9_proxy.cpp` - runtime-facing code, with `[TAG]` section markers
