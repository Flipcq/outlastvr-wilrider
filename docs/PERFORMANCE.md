# Performance work - measuring before and after

*Where the frame time goes, what has been optimised, the measurement protocol and the phase-by-phase
change log. Everything is anchored to `file:line` in the real code, and the switches are the `[Perf]`
section of `runtime/outlastvr.ini`.*

The mod renders **two views per frame** in one `ViewFamily`, which is exactly what UE3 does for split
screen - and Epic's own guidance is blunt about what that costs:

> "The two big rendering thread costs are determining visibility and then submitting draw calls to the
> GPU. (…) the cost is doubled in split screen!"
> — [Render Thread Profiling and Optimization](https://docs.unrealengine.com/udk/Three/RenderThreadProfilingHome.html)

So every change below is judged against **draw calls**, **processed primitives** and **render thread
time**, never against how it looks. Each item either has a number next to it from the mod's own log, or
is waiting for one.

---

# Part 1 - Diagnosis and roadmap

> **Status of this part.** Part 1 is the *diagnosis written before any of the work started*:
> the plan behind the phases. The phases it proposes are now **implemented** - see the
> "Roadmap of phases (implemented)" table and the per-phase sections below in this same file,
> plus Part 3 for the field fixes. Nothing in Part 1 is pending work; the few items that were
> investigated and deliberately **not** shipped say so in their own section (§ Phase 7, B3/B4).
> Read Part 1 for the reasoning, not for a to-do list.

## 1. How a frame works today (and where the costs are)

```
game thread ── Hook_CalcSceneView (ol_ue3.cpp:7227) ── 2× o_CalcSceneView (L/R eye)
                                                    └─ OLXR_FrameCommit + OLInteract_Tick (ol_interact.cpp:3123)
render thread ── Hook_GetViewPoint (ol_ue3.cpp:6751) per eye  (pose, lean, IPD)
               ── draws (2× the whole game) ── per-draw hooks (d3d9_proxy.cpp:870-886)
                    ├─ the occlusion test boxes ARE the answer: per-eye, no wait ([OCCLPEREYE])
                    └─ InitViews: PVS lookup, the 2nd eye reuses the 1st eye's answer ([PVSSHARE])
               ── Hook_Present (d3d9_proxy.cpp:901)
                    ├─ PaceToHeadset()      ← waits for the worker to consume (ol_xr.cpp:5085)
                    ├─ PublishBackbuffer()  ← StretchRect bb → shared D3D9Ex frame (ol_xr.cpp:2844)
                    ├─ monitor mirror       (d3d9_proxy.cpp:308, 30 fps)
                    └─ o_Present            (window, IMMEDIATE)
worker XR ── xrWaitFrame → beginFrame → SyncInput → pose
          ── ConsumeUpload → ExWorkerTake: samples the shared frame in place (no copy; [PERF-A3])
          ── BlitHalfToEye ×2 → GammaDraw (shader + cached SRV + CopyResource) (ol_xr.cpp:4166/3873)
          ── xrEndFrame (up to 4 layers: projection + flip screen + HUD + focus)
```

The repo already measured the bottleneck (`docs/PROJECT-BASELINE.md`, the Test 43 notes): post-processing effects change nothing — the limit is the render thread submitting 2× the draw calls. Strategy: cut per-eye render CPU and redundant work in the delivery path, without touching image quality.

## 2. Already optimized (don't repeat)

| Already done | Where | Measured gain |
|---|---|---|
| D3D9Ex + shared frames (no readback) | d3d9_proxy.cpp:1285 | 46 → 74-81 fps |
| [TEXSHADOW] texture shadow in RAM | d3d9_proxy.cpp:1329 | 136 freezes of 0.6 s → 0 |
| [MIRRORFPS] monitor at 30 fps | d3d9_proxy.cpp:953 | +1.6 ms/frame |
| [OCCLSKIP] occlusion boxes not drawn, immediate answer | d3d9_proxy.cpp:1246 | +7-12% |
| [HELDFRAME] don't re-blit repeated frame | ol_xr.cpp:~5711 | ~40% of frames |
| Hook SetVertexShaderConstantF removed (14k calls/frame) | d3d9_proxy.cpp:1525 | gives back cycles |
| [LENSFIT] per-eye frustum | ol_ue3.cpp:7092 | same cost, more sharpness |
| [NATIVEEYE] replay off (kNativeEyeReplayEnabled=false) | d3d9_proxy.cpp:273 | — |
| [OCCLPEREYE] one real occlusion answer per eye, no waits (phase 5) | d3d9_proxy.cpp:1662 (Hook_QueryGetData) | real culling back instead of force-visible; see phase 5 |
| [OCCLPROVE] a "culled" must be proven to be this box's answer (phase 5.1) | d3d9_proxy.cpp:1643 (OcclCullProven), :1662 | **the fix for the blink**: a query object two views drew into (or one already read this cycle) can never hide a prop |
| [OCCLHOLD] two "culled" in a row before a prop may vanish (phase 5.1) | d3d9_proxy.cpp:1643 (OcclCullProven) | no single noisy GPU frame blinks a prop out; ships ON with OcclPerEye=0 |
| [OCCLGUARD] prove+hold on the ENGINE's own reads (phase 5.2) | d3d9_proxy.cpp (Hook_QueryGetData, `OcclTrackingOn`) | the culling comes back through `OcclForce=0` **without** the per-eye table; ships ON, inert while OcclForce=1 |
| [PVSSHARE] the 2nd eye reuses the 1st eye's PVS answer (phase 5) | ol_ue3.cpp (Hook_PvsGet) | half the lookups; independent of OcclPerEye |
| [UNIONFRUSTUM] one frustum for both eyes (phase 5) | ol_xr.cpp (OLXR_LensFitTangents) | independent of OcclPerEye; **opt-in**, costs picture margin |
| [VISREUSE] one verdict for the 2nd eye, no boxes (phase 5.2: independent of OcclPerEye) | d3d9_proxy.cpp (`VisReuseLive`, `OcclTrackingOn`) | **opt-in**: needs UnionFrustum; measured cost/benefit still pending a session |
| [OVERSCAN] rendered margin beyond the lens (phase 7) | ol_xr.cpp (`OlrOverscan`, `OlrSubmitFov`) | **the fix for the black borders on a fast turn**: `[Stream] EdgeOverscanDeg`, ships 0 |
| [FSR1] EASU + RCAS enlargement (phase 7) | ol_xr.cpp (`kBlitHlsl`, `tune.y = 2`) | `[XR] Upscaler=2`: better picture per frame at RenderScale < 100% |
| [B9] per-eye draw counters + draw-list fingerprint (phase 7) | d3d9_proxy.cpp (`CountDraw`, `FingerprintDraw`) | measurement only; `[Perf] DrawFingerprint=0` |

## 3. Opportunities by (impact ÷ risk)

### A. Cheap, safe, near-immediate gain

| # | What | Where | Why it gives gain | Risk |
|---|---|---|---|---|
| A1 | timeBeginPeriod(1) at startup, + THREAD_PRIORITY_TIME_CRITICAL and EcoQoS opt-out (SetThreadInformation(ThreadPowerThrottling)) on the XR worker thread, + optional process priority | OLXR_Init (ol_xr.cpp:2053) and LogWriter; no timeBeginPeriod/SetThreadPriority exists in the project today (grep empty) | PaceToHeadset uses Sleep(1): since Win10 2004 timer resolution is per-process, and without it Sleep(1) can sleep up to ~15.6 ms → blowing the 1.25×period budget and causing jitter. EcoQoS can demote the compositor thread on power-managed machines | very low |
| A2 | Replace YieldProcessor() spin + PaceToHeadset lock with event wait (WaitOnAddress on g_pubSeq) | ol_xr.cpp:5089-5097 | in the last 1.5 ms before the deadline, the game render thread burns CPU spinning (~100% of one core) competing with the draws | very low |
| A3 | Eliminate the 36 MB per-frame CopyResource in ExWorkerTake (create one SRV per slot and bind directly into the blit) + cache the SRV GammaDraw creates every call | ol_xr.cpp:2902 and 3503 (CreateShaderResourceView per eye per frame, with comment "don't cache by pointer" — the safe solution is cache by swapchain image index, cleared on rebuild, see DestroyEyeSwapchains) | VRAM bandwidth: 36 MB/frame ≈ 2.6 GB/s | medium — **DONE in phase 4** ([PERF-A3], `[Perf] SharedFrameDirect=1`) |
| A4 | Per-frame snapshot of flags read in each draw call: OcclDrawSkipped() → OLUE3_OcclBypassOn() (cross-TU call), MirrorUiDraw → OLUE3_StereoMode/SplitActive | d3d9_proxy.cpp:866-886, 766 | 2k–6k draws × 2 eyes = up to ~12k calls/frame, each with 6–8 volatile reads and 2–3 non-inlinable calls | low |
| A5 | Hook_SetRenderTarget does GetBackBuffer (AddRef/Release) on every RT switch | d3d9_proxy.cpp:443-452 | cache the backbuffer pointer (invalidated on Reset) | very low |
| A6 | Camcorder HUD: only resend the dynamic strip when text changes | ol_xr.cpp ~3975 (UpdateSubresource 1920×160×4 = 1.2 MB/frame) | upload + glyph rebuild every frame | very low |
| A7 | OLUE3_ObjScanStep: adaptive budget with QPC (e.g. stop at 0.3 ms) instead of fixed 4000 objects/frame | ol_ue3.cpp:2111, 2156 | SEH-guarded scan of 4000 objects every frame on the game thread | low |
| A8 | Take the monitor mirror off the render thread (draw on the D3D11 bridge, which already has the frame) | d3d9_proxy.cpp:308, 974 | 2 full-frame StretchRects on the render thread, and stops dirtying the shared backbuffer | low |

### B. Medium gains — need A/B testing on the null headset

| # | What | Detail / how to validate |
|---|---|---|
| B1 | Per-eye occlusion instead of "everything visible" | Today OcclForce=1 + OcclSkip=1 trades real culling for "always visible". Fix properly = map query→(eye, index) in Hook_CreateQuery/Hook_QueryGetData, keeping previous-frame answer, without wait=TRUE. Expected result: the +7-12% of OcclSkip and culling back. A/B: `occlskip 0`. **DONE in phase 5** ([OCCLPEREYE], `[Perf] OcclPerEye=0`): one real answer per eye, reads never wait, force-visible and box skipping stand down. Ships OFF because the first session with it on reported props blinking — **that blink is fixed in phase 5.1** ([OCCLPROVE] `[Perf] OcclProve=1`: a "culled" is only believed when the value provably describes the box the engine just drew — one result slot, one issue, no re-read; plus [OCCLHOLD] two zeros in a row). Re-enable to A/B. |
| B2 | 2nd eye reuses 1st eye's PVS | Hook_PvsGet (ol_ue3.cpp) already in place; cache per-frame the result from eye L and return it to R. **DONE in phase 5** ([PVSSHARE], `[Perf] PvsShare=0`): keyed by the call's state pointer, dropped at every Present. Ships OFF — it was one of the two changes in play in the 2026-11-05 blink report; turn it on by itself (with OcclPerEye=0) to judge it alone. **Depends on nothing else** (phase 5.2 audit): it touches the engine's precomputed visibility, not the occlusion queries, so it runs with OcclForce either way. Recommended ON in the phase-5.2 profile. |
| B3 | Do eye blits before xrWaitFrame | Capture was already moved out of the deadline for this reason (ol_xr.cpp:5140); the blits (BlitHalfToEye) still run inside the compositor window (ol_xr.cpp:5770+). Opening the window tends to reduce dropped frames/ASW. **Investigated in phase 7, NOT done**: the blits need the frame/pose `ConsumeUpload` produces, and acquiring a swapchain image before `xrBeginFrame` risks `XR_ERROR_CALL_ORDER_INVALID`; doing it properly means splitting the worker frame into two phases with the image held across the wait, in the one path that must never deadlock. See §Phase 7. |
| B4 | Single swapchain with arraySize=2 | Official recommendation (MS OpenXR best practices: "avoid a separate swapchain per eye / double-wide — runtime post-processing"). Today there are 2 swapchains (ol_xr.cpp:3113-3130). Gain depends on the runtime: measure in VDXR, SteamVR and Link. **Investigated in phase 7, NOT done**: it changes the acquire/release protocol for both eyes at once and cannot be verified without a headset; a mistake freezes one eye or swaps the views. See §Phase 7. |
| B5 | Fewer composition layers | In-game with camcorder in hand: projection + flip screen + HUD + focus = 4 layers (ol_xr.cpp:6154-6196). Draw HUD/focus inside the eye image (the blit already exists) eliminates compositor work per layer — test visually for loss of depth adjustment. **Measured in phase 7, not changed**: `[PERF] composition layers: N/frame avg` is now reported, which is the prerequisite; folding the HUD into the eye image changes its position relative to the lens and needs a headset to judge. |
| B6 | FSR1 (EASU + RCAS) on the D3D11 blit | The blit is already a PS 4.0 with gamma LUT and custom CAS (ol_xr.cpp:3233). Swapping bicubic+sharpen for EASU+RCAS (pure HLSL, MIT, GPL-3.0 compatible like ImGui/MinHook) allows RenderScale 0.70-0.85 with better quality → real GPU gain for those who are GPU-bound (Quest 3 at 1.0 = 9.1 MP/frame). **DONE in phase 7** (`[XR] Upscaler=2` / menu "FSR 1"): a faithful port of `ffx_fsr1.h`, 12-tap EASU with dering + RCAS clip solve, every tap through the seam clamp, only when actually scaling up. The shipped shader is compiled by `tests/perf_pipeline_test.py` with `fxc`, so a broken shader cannot ship. |
| B7 | "Performance" profile in launcher | Expose via ConsoleCommand (the con channel already exists, see `docs/PROJECT-BASELINE.md`): DynamicShadows (+6% measured), MaxDrawDistanceScale, Decals, ParticleLODBias, with restore on exit and an ini behind it (house rule). **DONE in phase 6** ([Content] Profile, `[CONTENT]` log tag): two lists plus a Restore list, all engine console lines, applied once gameplay is live and re-applied after a level load; the launcher row is FULL DETAIL / PERFORMANCE / PERFORMANCE+. Ships OFF — content trade. |
| B8 | Render directly into the swapchain image (typeless RTV) | Eliminates g_blitTmp + CopyResource (ol_xr.cpp:3547) = another 36 MB/frame. There was an old garbled-image case; the most likely hypothesis is wrong sRGB view — test only as an isolated experiment, with automatic fallback. **DONE in phase 4** as the experiment it was meant to be: `[Perf] DirectSwapchain=1` (off by default), format + colour space taken from the image (OlrDirectViewFormat), scratch draw + copy on any refusal |

### C. Structural — biggest gain, requires reverse engineering (research spike)

| # | What | Why it's the biggest gain available |
|---|---|---|
| C1 | Reuse eye L visibility for eye R (ComputeViewVisibility): copy PrimitiveVisibilityMap + dynamic element lists | The two eyes are ~3 cm apart: the visible set is practically identical. Skipping the 2nd eye's culling cuts about half of per-frame visibility CPU. First step: instrument (QPC) ComputeViewVisibility cost per eye and print in [PERF] — without numbers, don't touch it. **PARTLY DONE in phase 5** ([VISREUSE], `[Perf] VisReuse=0`, opt-in): the half of visibility the mod owns (the D3D9 occlusion verdicts) is reused, with a self-check on the pairing; the engine's own frustum cull per view is untouched, and the [PERF] line now measures both passes |
| C2 | Intermediate step for C1: union frustum (L ∪ R) on both passes | Classic multi-pass technique (Unity "optimized multi-pass"): guarantees identical sets → makes C1 trivially valid; alone it doesn't save CPU. **DONE in phase 5, opt-in** ([UNIONFRUSTUM], `[Perf] UnionFrustum=0`): both halves are built with ONE frustum (union of both lenses widened by the stereo offset) and the blit crops it back per eye |
| C3 | Dynamic shadows once per frame (share shadow maps between eyes) | DynamicShadows off = +6%: pure duplicated cost per eye. Confirm with stat scenerendering — UE3 already shares the shadow map between views |
| C4 | Pose latency | There's already 1-period prediction — don't repeat without new data (only makes sense with blits out of the deadline, B3) |

### D. Duplicate work in Unreal Engine 3

**D.0 — How to prove it, using the engine's own tools**

Epic documents that, with two views, render thread cost doubles, and the two metrics that matter are Processed Primitives and Mesh draw calls. The `stat splitscreen` stat gives processed primitives, mesh draw calls and particle draw calls; the mod already has the `con` channel (see `docs/PROJECT-BASELINE.md`).

| Command (via con) | What it answers |
|---|---|
| stat unit | ms of Game / Draw (render thread) / GPU — tells which side is the limit now |
| stat splitscreen | processed primitives × mesh draw calls × particle draw calls |
| stat initviews | time and effectiveness of visibility culling |
| stat scenerendering | how much of render thread is in RenderViewFamily |
| stat sceneupdate | repeated AddLight/AddPrimitive |
| TRACKPARTICLERENDERINGSTATS → DUMPPARTICLERENDERINGSTATS | which particle systems cost (two reports in logs folder) |

Suggested mod instrumentation (per-frame counters, [PERF] pattern): CalcSceneView, UpdateSkelPose, GetFovAngle, PvsGet, OcclUpdate, NativePlayerMove, GetViewPoint.

**D.1 — "Are components updated twice per frame?" — answer is almost always no**

| System | Times per frame | Evidence |
|---|---|---|
| World / component / particle Tick (UParticleSystemComponent::TickComponent) | 1× | Update is per component on the game thread (TickGroup=TG_DuringAsyncWork, bSkipUpdateDynamicDataDuringTick in class defaults — UE3 source) |
| Animation / UpdateSkelPose (mod hooks 0x6FFC90) | 1× per component | it's the game thread update (ol_ue3.cpp:2786-2791); CalcSceneView only builds the FSceneView |
| CalcSceneView | 2× (the mod calls it) + N× if SceneCapture present | ol_ue3.cpp:7307-7315 |
| Culling / visibility (ComputeViewVisibility, ProcessVisible(ViewIndex,…)) | 2× | FSceneRenderer::ProcessVisible(INT ViewIndex, DWORD& ViewVisibilityMap, …) — class docs |
| Base pass / draw calls (RenderDPGBasePassStaticData(DPGIndex, FViewInfo& View)) | 2× | idem — it's the cost measured in the repo |
| Shadow maps (CreateWholeSceneProjectedShadow, GatherShadowsForPrimitives(…, BYTE ValidViews, …)) | 1× per family | ValidViews + per-view dependency show shared shadow map |
| Dynamic elements (skeletal: bone palette upload; particles: instances/LOD) | 2× (per view) | what generates a draw call per view |
| Post-process, fog volumes, translucency, decals, light shafts, distortion | 2× (RenderView per view) | idem |

⚠️ Correction: the "+6%" measured with DynamicShadows off is probably the base shadow cost, not a second shadow map render per eye. Before investing in "shadows once per frame", confirm with stat scenerendering — UE3 already shares the shadow map between views.

**D.2 — What the mod code duplicates (and can cut now)**

| # | Finding in code | Why it costs | Action |
|---|---|---|---|
| D-1 | Hook_SkelUpdate → PoseApplyVisible(comp) runs for every skeletal component in the level | the solver gate + counter + three global restores run for every component | exit with a mesh pointer read; restores still happen 1× per frame |
| D-2 | Hook_GetViewPoint calculates lean vector per eye | the lean vector is constant for the frame | share the lean vector between both eyes (per-eye body kept: costs ~300 ns, not worth rewriting the hook) |
| D-3 | GetFovAngle called several times per frame | repeated getter | cache indexed on three entries (frame, engine value, zoom) |
| D-4 | Player lights identified on every SetRotation | repeated lookup | identify once (NvLightCache) |
| D-5 | Objects scanned fixed: 4000/frame | SEH-guarded scan on the game thread | adaptive budget with QPC (A7) |

**D.5 — Official two-view lever not yet used by the mod: DetailMode**

Epic: "The next best method is setting a component's DetailMode to High, which will cause it to not be rendered at all in splitscreen. (…) Removing components in this way is the most effective for performance, because it reduces 'Processed primitives' and 'Mesh draw calls'."

In game: `con scale set DetailMode 1` (Medium) → every mesh marked High detail (vegetation, papers, debris, decoration, some effects) stops being processed in both views. Testable today via the con channel, measurable with stat splitscreen, reversible, visual cost assessable in 2 minutes. Less aggressive alternative (documented in the same text): aggressive MaxDrawDistance / cull distance — reduces draw calls but not processed primitives.

**DONE in phase 6** as the `[Content]` profile (see §Phase 6): `Commands1` runs `scale set DetailMode 1`, `Commands2` the same plus shadows/decals, and `Restore` puts every value back. It ships OFF because it is a content trade; the launcher row (B7) is the player-facing control.

**D.6 — Two hypotheses already dead (don't repeat)**

- Outlast custom occlusion tracker (PrimitiveSceneProxyOcclusionTracker, 0x29AEF0): hook installed, calls = 0 in gameplay, force ON changed nothing (ol_ue3.cpp:6915-6923).
- PVS bypass (GetPrecomputedVisibilityData, 0x8A7810): forced for whole windows, flicker unchanged (ol_ue3.cpp:6937-6948). The hook remains useful only for [FRAMETAG].
- What fixed two-view flicker was forcing hardware occlusion query results to "visible" (OcclForce + OcclSkip) — exactly item B1.

**D.7 — Where category D fits in execution order**

1. D.0 — instrumentation + stat splitscreen/stat initviews (1 session, zero risk). Before anything.
2. D-1 to D-5 — cheap gates on hooks that run per-component/per-query (immediate gain in NPC scenes, zero image risk).
3. D.5 — DetailMode as performance option, together with B7.
4. D.4 — only after DUMPPARTICLERENDERINGSTATS; if particles don't appear on top, discard.
5. C1/D.3 — visibility reuse between eyes (the only big structural gain left), with D.0 instrumentation measuring the target.

## 4. Measurement plan (without it, everything else is a guess)

The repo already has [PERF] (frame/present/grab/copy/pace/upload), [XRTIMING], [HITCH], [EXSTAT] and the SteamVR null headset. Three numbers are still missing:

1. GPU vs CPU: present avg/max already indicates GPU-bound (blocking Present), but a D3D11_QUERY_TIMESTAMP_DISJOINT around the blits is missing → real GPU cost of the bridge (2 eyes + copies).
2. Per-stage render thread cost: timer inside Hook_CalcSceneView (2 views) vs. rest of frame.
3. Draw calls per frame (g_uiSeen/g_occlSkippedDraws give a hint; a dedicated counter in Hook_DrawIndexedPrimitive closes the account) — this is the metric that validates A4, B1, C1.

**Protocol:** null headset, PaceToHeadset=0 + MaxSmoothedFrameRate=300 (as in `docs/PROJECT-BASELINE.md`), 3 fixed game points (door, corridor, theater screen), 3 runs, median. Then confirm on a real Quest 3 with [HITCH].

## 5. Suggested execution order

1. Instrumentation (§4) — 1 session, zero risk.
2. A1, A2, A4, A5 — hitches and per-draw CPU, without touching image. Validation: [PERF]/[HITCH] before/after.
3. A3, A6, A7, A8 — wasted bandwidth and CPU.
4. B1, B2 — the ones that change how the game draws → A/B via ini (OcclPerEye=0, PvsShare=0, both off by default; turn on one at a time to A/B). **Phase 5.2 revises the order**: first try `OcclForce=0` + `OcclusionSkip=0` + `OcclGuard=1` + `UnionFrustum=1` + `VisReuse=1` + `PvsShare=1` (the profile in §Phase 5.2) — that is the culling coming back without the per-eye table; leave `OcclPerEye=0` and make it the last A/B.
5. B6 (FSR1) and B7 (performance profile) — what the player feels as "more FPS".
6. C1/C2/C3 — only after the numbers, one at a time (house rule: "change one mechanic at a time").

## 6. Not worth it (already discarded by repo data)

- Post-processing quality (DOF, SSAO, bloom, light shafts): measured, changes nothing — the render thread is the limit.
- Single-pass stereo / multiview / SPS: requires instancing/vertex amplification and D3D11 in the renderer — impossible with UE3/D3D9 without rewriting the RHI. The viable path is C1 (visibility reuse), which attacks the same account from another side.
- Re-enabling AllocViewStateRva/SharedStateRva (runtime.ini:25-32): the file itself warns against it.
- Depth buffer submission (XR_KHR_composition_layer_depth) for positional reprojection: would require copying D3D9 depth every frame, and the README says to disable ASW/motion smoothing in this game — gain doesn't pay off.

## 7. External references used

- Khronos OpenXR Guide — Frame Submission: mandatory xrWaitFrame/xrBeginFrame pairing, late update/late latch, and why to submit the exact pose used for rendering (the mod already does — [FRAMETAG]).
- Microsoft — OpenXR best practices: pick the first swapchain format offered, use one projection, avoid dual layers/swapchain per eye, and the runtime post-processing warning (basis of B4/B5).
- MS — Surface sharing between Windows graphics APIs: D3D9Ex↔D3D11 sharing is unsynchronized (the mod already manages it with event queries) and format/mip/array restrictions (why A8R8G8B8, 1 mip, no MSAA in ol_xr.cpp:2802).
- VR/AR Wiki — Single-pass stereo rendering: two passes cost ~2× CPU/driver/geometry; and Unity's optimized multi-pass trick (shared shadow map + single cull against combined frustum) → exactly the design of C1/C2/C3.
- Bruce Dawson — Windows Timer Resolution: The Great Rule Change: since Win10 2004 timeBeginPeriod is per-process, so each app must request 1 ms resolution (A1).
- MS — SetThreadInformation / ThreadPowerThrottling: THREAD_POWER_THROTTLING_EXECUTION_SPEED = EcoQoS; must not be used on real-time/front threads — hence the explicit opt-out (A1).
- GPUOpen — FidelityFX FSR 1.0: pixel-shader upscaler (EASU + RCAS), MIT — fits in the existing D3D11 blit (B6).

---

## Roadmap of phases (implemented)

**Status, verified 2026-11-05 on `stable-1.2.2-launcher-rework`:** phases 1, 2, 3 and 4 are all in the tree and all of their switches are live (`tests/perf_switches_test.py`, `tests/perf_threading_test.py` and `tests/perf_framepath_test.py` pass, and the `[PERF]` report prints the phase-2 counters). Phase 5 (B1, B2, C2, C1) is implemented below and covered by `tests/perf_visibility_test.py`; phase 5.2 (the dependency audit, `[OCCLGUARD]` and C1's independence) is in the same file and the same test.

**Phase 1 — Instrumentation and diagnosis (no behavior change)**

- CPU/GPU and frametime measurement; draw call counters; visibility and render profiling (`stat splitscreen`, `stat initviews`, `stat scenerendering`).
- Draw hooks in d3d9_proxy.cpp (draw calls submitted + swallowed by [OCCLSKIP]).
- Hook_CalcSceneView in ol_ue3.cpp (µs inside the two CalcSceneViews).
- Per-frame counters for UpdateSkelPose, GetFovAngle, PVS and occlusion tracker.
- GPU of the mod's own commands (eye blits + copies) via D3D11_QUERY_TIMESTAMP_DISJOINT.
- `docs/PERFORMANCE.md` with the full protocol and Epic targets.

**Phase 2 — CPU optimization (each with a [Perf] switch, default = optimized path)**

- A4 DrawFastFlags: 3 cross-module calls per draw call → 1 snapshot per Present.
- A5 BackBufferCache: GetBackBuffer (COM, AddRef/Release) on every RT switch → pointer comparison; invalidated on Reset and new device.
- D1 SkelFastGate: solver gate exits with a mesh pointer read; restores still happen 1× per frame.
- D2: lean vector is constant per frame, shared between both eyes.
- D3 FovCache: getter cached (frame, engine value, zoom).
- D4 NvLightCache: player lights identified once.
- A6 HudSmart: dynamic strip (1.2 MB) only redrawn/sent when a readout changes.
- A7 ObjScanBudgetUs=250: object scan limited by time, not 4000 objects/frame.

**Phase 3 — Delivery path and XR thread**

- A1: timeBeginPeriod(1) per process; XR thread at THREAD_PRIORITY_TIME_CRITICAL + EcoQoS opt-out; ABOVE_NORMAL process available but disabled by default.
- A2: WaitOnAddress instead of spin (PaceToHeadset / ConsumeUpload); render thread blocks on g_conSeq instead of spinning with YieldProcessor().
- A8: monitor mirror off the render thread (worker draws directly into a DXGI bitblt swapchain on the same HWND, DXGI_PRESENT_DO_NOT_WAIT; live fallback if monitor not active).
- New [Perf] switches: TimerResolution=1, ThreadPriority=1, ProcessPriority=0, PaceWait=1, BridgeMirror=1 (all with optimized path as default), documented in runtime/outlastvr.ini.

**Phase 4 — Memory and GPU**

- A3, first half: the 36 MB per-frame copy is gone. `[EXSHARE]` used to `CopyResource` the opened shared frame into `g_uploadTex` before every blit; the blits now sample the shared texture itself. Every consumer of "this frame's pixels" reads one pointer, `FrameTex()` (null = the old upload texture, i.e. the CPU-readback lane, `[ZEROCOPY]`, and the fallback).
- A3, second half: the view cache. `CachedSrv`/`CachedRtv` keep one `ID3D11View` per (texture, kind, format) instead of `GammaDraw` creating and releasing one per eye per frame. The old comment refused to cache "by texture pointer" (a rebuilt swapchain frees the texture and the allocator reuses the address); the entry now holds a *reference* to its texture, so the identity cannot be recycled, and `ViewCacheClear()` runs in `DestroyEyeSwapchains` (before `destroySwapchain`), `RebuildForSize` and on every new `[EXSHARE]` generation. The MonitorDraw render-target view is deliberately NOT cached: a cached reference to a DXGI back buffer blocks `ResizeBuffers`.
- A3, ordering: the shared slot is only handed back when the frame's draws are queued, not when the copy runs — `ExDirectRelease()` ends the slot's D3D11 event query one frame later (`ExWorkerTake` → next frame), and `ExWorkerTick` skips the slot being read (its query still reads as signalled from an earlier frame — that check is the one that keeps the game from overwriting a live read). `RebuildForSize` releases it immediately, because a size change means the picture is unusable anyway.
- B8: `[Perf] DirectSwapchain` (default **0**, opt-in) draws the eye blit straight into the acquired swapchain image and skips `g_blitTmp` + `CopyResource`. `OlrDirectViewFormat` takes the view format *and* the colour space from the destination image: a typeless image gets an explicit format (null-desc views are illegal on typeless resources), an sRGB/UNORM mismatch is impossible by construction, anything outside the B8G8R8A8 family or not a render target is refused, and the frame falls back to the scratch draw + copy. That is the diagnosis of the old garbled-image case, expressed as code.
- New [Perf] switches: SharedFrameDirect=1 (the in-place read, on by default with its own automatic fallback), ViewCache=1 (one view per texture; 0 = the pre-1.2.2 view-per-call), DirectSwapchain=0 (isolated experiment), documented in runtime/outlastvr.ini with a boot line each (`[PERF-A3]` / `[PERF-B8]`).
- Tests: `tests/perf_framepath_test.py` compiles the real cache and the real `OlrDirectViewFormat` against a stub D3D11 layer (view identity, reuse over 60 frames, refcount, refusal of a wrong-space view, eviction, clear, and the ViewCache=0 churn) and then checks the source for the ordering rules above.

**Phase 5 — UE3 visibility (the two eyes stop sharing one verdict)**

Both of the game's visibility machines were written for ONE picture per frame, and VR makes two. Phase 5 gives each eye its own answer where the mod owns the decision, and it makes the two views agree where it does not.

- B1 — `[OCCLPEREYE]`, `[Perf] OcclPerEye=0` (**ships OFF**). Until now the fix for the same-frame flicker was blunt: `OcclForce=1` made *every* hardware occlusion answer "lots of pixels visible" (nothing is ever culled) and `OcclusionSkip=1` stopped drawing the test boxes. B1 replaces that with the real thing: `Hook_QueryGetData` (d3d9_proxy.cpp:1662) keeps the last real answer **per eye** in a fixed 512-slot table keyed by the query object, strips `D3DGETDATA_FLUSH` from the poll so a read **never waits**, and answers a query the GPU has not finished with *that eye's previous frame* — the one-frame-old answer UE3 is built around. A query's very first read, and any query whose answer stops arriving for `kOcclStaleLimit` reads, still asks the device the way the engine did, and a table that runs out of slots asks the device too (never a wrong verdict). While it is on, `OcclForce`'s force-visible and `OcclusionSkip`'s box skipping **stand down by themselves** — the boxes ARE the query's pixels, so skipping them would answer "nothing visible". The `draws` number in `[PERF]` therefore goes back up against a 1.2.2 log: the boxes are drawn again, and that is the answer being produced, not a regression. It ships OFF because the first headset session with it on (2026-11-05) showed props blinking — **phase 5.1 below is the fix for that blink**, so turn it on with `OcclProve=1` and `OcclHold=1` (both ship ON) to A/B it.
- Which eye is asking: the render thread has no eye flag (`g_eyePhase` lives on the game thread). `EyeOfView` (ol_ue3.cpp) compares the renderer's copy of the view against the committed **LEFT** view's matrices — the same 128 bytes `[FRAMETAG]` already uses, bit for bit — off the `[PVS]` hook, and publishes the answer as `g_olRenderEye` (one load, no call). `Hook_SetViewport` (device vtable 47) mirrors the engine's viewport as a second opinion, but only a viewport that really covers **one half of the frame** counts as that statement (`OcclEyeFromViewport`, d3d9_proxy.cpp:1440) — a shadow map, a scene capture or the mod's own UI quad is some other size and would have named the wrong eye. With no committed key nothing can match, so the tracker answers "the other eye" and every per-eye path keeps ONE set of answers — the shape it replaced. It can be useless; it cannot invert the eyes.
- B2 — `[PVSSHARE]`, `[Perf] PvsShare=0` (**ships OFF**). `GetPrecomputedVisibilityData` picks a baked cell from the view origin; the eyes are 6 cm apart, so they normally pick the same cell — and when they do not, the two views get two different verdicts for the same mesh, which is the "prop winks in one eye" family. The second eye now reuses the first eye's answer for the same call, keyed by the call's **state pointer** (so the pairing does not depend on the order the renderer walks primitives in). The table is invalidated once per Present by `OLUE3_PerfFrameBoundary()` (called from the proxy's Present hook, on the render thread), so a cell pointer from an older frame is never handed out. It ships OFF because it was one of the two changes in play in the 2026-11-05 blink report — turn it on by itself (with OcclPerEye=0) to judge it alone, isolated from the occlusion verdicts.
- C2 — `[UNIONFRUSTUM]`, `[Perf] UnionFrustum=0` (**opt-in**). `OLXR_LensFitTangents` returns the **same** frustum for both halves when on: the union of the two lens frusta, widened horizontally by the stereo offset at `[Perf] UnionNearUU` (default 10 game units = 10 cm) and vertically by the plain union (the eyes share their height). Both views then cull the same world. The blit asks `OLXR_LensFitTangents` per half and crops the wider picture back onto each eye's own lens (`BlitFitToEyeTan` already does that maths), so the geometry is unchanged — the cost is that each eye gets its lens out of a bigger image, i.e. part of the sharpness LENSFIT bought. It ships OFF for exactly that reason.
- C1 — `[VISREUSE]`, `[Perf] VisReuse=0` (**opt-in, and idle without UnionFrustum**). The second eye stops drawing its own occlusion test boxes (`OcclDrawSkipped` skips them for eye 1 only) and takes the first eye's verdicts **in call order**. Call order is only a usable pairing if the two passes ask the same questions, so the code checks exactly that: the list is offered only to a frame whose two passes made the same number of reads **in the previous frame** (`g_visPairOk`), falls through to the device otherwise, and the first frame after a change reuses nothing. Two more guards keep a mis-detection from being catastrophic: the boxes are skipped only in a frame where the tracker really reported the primary view (`g_sawPrimaryEye`, cleared at every Present), and the live gate is the per-Present flag snapshot (`kFF_VisReuse`, set only while `OLXR_UnionFrustumOn()` is true) — so the two keys can be loaded in any order.
- Measurement (`[PERF]`, one new line): `occl per-eye: N fresh + N stale (no wait) + N first-read, N reused, N no slot | pass L x us R y us | pvs shared N, asked N | view eye primary/secondary N/N | verdict changes L x R y/frame, held N (unproven N)`. One QPC pair per eye **pass**, not per query (the queries are thousands a frame); taken and cleared, so nothing is reported twice. `held` counts the "culled" answers that were refused; `unproven` counts the ones refused because the value could not be proven to be that box's at all — that is the number that says whether the two views are really fighting over one query object.
- Tests: `tests/perf_visibility_test.py` compiles the real per-eye decision code, the real table, the real read path (`Hook_QueryGetData`), the real C1 pairing, the real eye tracker and the real PVS cache against stubs, and then checks the source for the rules above (per-eye first, boxes kept, C1 gated on C2, caches dropped at Reset / new device / Present, the union being half-independent, the blit asking per half, a "culled" only from a proven value).
- Defaults: `OcclPerEye=0`, `OcclHold=1`, `OcclProve=1`, `OcclGuard=1`, `PvsShare=0`, `VisReuse=0`, `UnionFrustum=0`, `UnionNearUU=10` — in `runtime/outlastvr.ini`, next to a boot line each (`[OCCLPEREYE]`, `[OCCLHOLD]`, `[OCCLPROVE]`, `[OCCLGUARD]`, `[PVSSHARE]`, `[VISREUSE]`, `[PERF-UNIONFRUSTUM]`). Phase 5.2 additionally logs `[PHASE52]` at boot, naming which of the three owners has the occlusion queries.

**Phase 5.1 — the blink (the 2026-11-05 field report): what it was, and why it cannot happen again**

With `OcclPerEye=1` the player saw props blinking in front of him. Two defects, one of them a wrong premise:

- **The premise was wrong.** Phase 5 assumed "a D3D9 query object belongs to one view, so its eye is stable". This very file says the opposite eighteen hundred lines earlier (d3d9_proxy.cpp:1378): *"the query handles come from a pool shared per scene and recycled per frame — with TWO views per frame the second view can fetch results that belong to other queries, so its verdicts are garbage and props strobe."* A D3D9 occlusion query is **one result slot**: it holds the answer for the box that was drawn into it **last**. When both views drew into the same object before anybody read it, the value that arrived was the second eye's box, and phase 5 filed it as the asking eye's answer. A "0 pixels" produced by another box then reached the engine as this eye's verdict, and the engine culled a prop that was right in front of the player — for one frame.
- **The stabiliser latched.** `OcclHoldKeep` compared a new zero with the verdict the engine had been **told**, not with the previous real answer. Once a prop had been told "visible", every later zero was compared with that held "visible" and held again, for ever: nothing could ever be culled again (the `held` counter ran high while the culling was gone), while the queries whose *first* answer arrived as a zero were reported raw — exactly the ones that blinked.

The rule now, in one place: `OcclCullProven` (d3d9_proxy.cpp:1643), and `[Perf] OcclProve=1` ships ON. A "culled" is published only when **all** of these hold:

1. the answer says 0 pixels;
2. the value was produced by **this** eye's box — every BEGIN/END records `pendEye` on the object, and a value is filed against its owner, never against the eye that merely asks;
3. the object was opened **exactly once** since its value was last read (`issues`) and has not been read yet in this cycle (`readers`) — one slot can only make one statement, and a second BEGIN or a repeat read means the value on offer describes something else;
4. with `OcclHold=1` (ships ON), this eye's previous **real** answer was a zero too, so a single noisy GPU frame can never blink a prop out. "Visible" is always believed at once — a wrong "visible" only costs pixels.

Anything else is answered with `0x7FFFFF` ("lots of pixels"), which is exactly what `OcclForce` has been telling the engine since 1.2.1. A value that may describe another box is **not even fetched**: the read returns "lots of pixels" at once, so a contended object costs neither a wait nor a blink. The honest consequence, and the reason `unproven` is on the `[PERF]` line: while the two views fight over one query object the per-eye path culls nothing at all (correct, and no blinking); as soon as each view owns its object the culling is back on its own. `OcclEyeFromViewport` (d3d9_proxy.cpp:1440) was also tightened: only a viewport that really covers one half of the frame names the eye — a shadow map, a scene capture or the mod's own UI quad used to be read as "the left eye", which filed that eye's answers wrongly. A recycled D3D address is now fully re-initialised at `CreateQuery` (`OcclSlotInit`), not just its `have` flags.

`tests/perf_visibility_test.py` compiles the **real `Hook_QueryGetData`** against a stub device and drives it: two views drawing into one object never produce a "culled" (even with the GPU answering "0 pixels"), one view per object culls on the second zero, and a fresh visible answer is passed on immediately. `[Perf] OcclProve=0` restores the pre-5.1 raw shape and reproduces the blink on demand, which is the A/B for the proof itself.

**Phase 5 caveats (read before judging it on a headset):** the mechanism is proved in code, not in a session. The 2026-11-05 blink now has a named cause and a code-level guarantee against it (phase 5.1 above), but it still needs the visual pass: `OcclPerEye=1` with `OcclProve=1` and `OcclHold=1` in a heavy area, then read the `[PERF]` line — `unproven` near zero means the game really does give each view its own query object (so the culling is worth keeping), a high `unproven` means it does not, and then the per-eye path is buying nothing and `OcclPerEye=0` is the honest setting. `PvsShare=0` ships off — it was one of the two changes in play in the blink report; turn it on by itself (with `OcclPerEye=0`) to judge it alone. `UnionFrustum` costs picture margin per eye (measure with `draws` and the GPU line); `VisReuse` needs `UnionFrustum=1` to do anything at all, and its pairing needs the `stat initviews` numbers from a heavy area before it could ship on.

**Phase 5.2 — the dependency audit: which switch ever needed `OcclPerEye`?**

The field wish was to keep `PvsShare` + `VisReuse` + `UnionFrustum` on, keep `OcclProve`/`OcclHold` as protections, and leave `OcclPerEye` off until a session proves it safe. The audit says that is possible, and it found one real dependency plus one dead end:

| Switch | Depended on `OcclPerEye`? | Why |
|---|---|---|
| `UnionFrustum` (C2) | **No** | It only changes `OLXR_LensFitTangents` (one frustum for both halves) and the blit crop. It never touches a query. |
| `PvsShare` (B2) | **No** | It keys the PVS hook by the call's state pointer, in `ol_ue3.cpp`, on its own table. Different engine machine from the occlusion queries. |
| `VisReuse` (C1) | **Yes, as coded — fixed here** | `VisReuseRecord`/`VisReuseTake` and the second eye's box-skip all sat inside `if (occl && g_occlPerEye)`. At `OcclPerEye=0` the list was never written and the skip never ran: the switch was dead code. |
| `OcclProve` / `OcclHold` | **read only by the per-eye path** | Inert at `OcclPerEye=0`. That is why they could not protect anything in the shipped configuration. |

But independence alone was not enough. With the shipped `OcclForce=1` + `OcclusionSkip=1`, every occlusion answer is already replaced by "visible" and the test boxes are already not drawn — so `VisReuse` (which removes the second eye's boxes) and `OcclProve`/`OcclHold` (which judge a "culled") have nothing left to do. **A configuration that uses them must also put the engine back in charge of the culling**: `OcclForce=0` + `OcclusionSkip=0`. That is the real change of this phase, and it is why the new `OcclGuard` exists.

- `[OCCLGUARD]`, `[Perf] OcclGuard=1` (**ships ON, inert while `OcclForce=1`**). It applies the phase-5.1 rule — prove the "culled", then require two zeros in a row — to the **engine's own** occlusion reads, with no per-eye table at all. The engine keeps drawing its boxes and keeps its own waits exactly as it always did; the only thing that changes is the judgement passed back to it. A value that another view drew into is not even fetched: the engine is told `0x7FFFFF` at once, so it costs neither a wait nor a blink. A wrong verdict can therefore only ever cost pixels, never a prop. This is the "culling is back" path that does **not** use the mechanism implicated in the 2026-11-05 report.
- **The ownership decision is one predicate.** `OcclTrackingOn()` is true when the per-eye table, the guard or C1 needs the bookkeeping — and the guard deliberately backs off while `OcclForce` owns the queries, so the shipped default stays exactly as cheap as it was (no table, no eye tracking, one branch per query).
- **C1 is now independent.** `VisReuseLive()` is `VisReuse && (UnionFrustum gate from the per-Present snapshot) && sawPrimaryEye && visPairOk` — it does not read the per-eye switch. The second eye's boxes are skipped in both modes, and the second eye is served the first eye's list in both modes. Two guards remain because this is the switch that can hide a prop: it only acts in a frame that really reported the primary view, and only after the previous frame's two passes asked the **same number of questions** (otherwise call order is not a pairing, and a missing box would answer "0 pixels" for something nobody tested). When the list is not armed the second eye is told "lots of pixels" — never a fabricated cull, never a device read for boxes that were not drawn. That read still advances the call counter, so the very next frame can arm the pairing.
- **The `[PERF]` line is the judge.** `reused N` proves C1 is serving; `held N` proves the guard refused culls; `pvs shared N` proves PVS sharing; `unproven N` must stay low (a high count means the second eye is asking for answers nobody recorded — i.e. the two passes are not pairing, and C1 is buying nothing).
- **Known caveat, stated honestly:** the guard keeps the phase-5.1 rule verbatim, including "the value must have been produced by the eye that is asking". UE3 reads a query's previous answer at the *start* of the next view's work, so the eye at read time can differ from the eye that drew the box. When that happens the rule refuses the "culled" and reports "visible" — safe, but it means the guard may cull less than the ceiling. The `held`/`unproven` numbers on the `[PERF]` line are exactly how a session finds out: if `held` is almost equal to the number of zero answers, the identity is stale at read time and the honest conclusion is that the engine's query pattern does not give the guard enough to work with — at which point `OcclPerEye` (which records the owner at BEGIN, when the viewport is certainly right) becomes the only remaining lever, and the picture decides whether it is worth it.

**The recommended profile (in `runtime/outlastvr.ini`, "PHASE 5.2" block at the end of the phase-5 section):**

```
[Stage3]  OcclForce=0          the engine culls for real
[Render]  OcclusionSkip=0      the boxes must be drawn: they ARE the answer
[Perf]    OcclGuard=1          prove + hold on the engine's reads (the safety net)
[Perf]    UnionFrustum=1       both eyes cull the same world (needed by VisReuse)
[Perf]    VisReuse=1           the second eye keeps one verdict and draws no boxes
[Perf]    PvsShare=1           the second eye's PVS comes from the first
[Perf]    OcclPerEye=0         stays OFF: the mechanism that blinked is not used
[Perf]    OcclProve=1, OcclHold=1   the protections, now applied by OcclGuard
```

`OcclPerEye=1` then becomes the **last** experiment, on its own, with the profile above as the baseline — if it adds measurable culling on top (read `unproven`), keep it; if the picture blinks, nothing above is lost.

**A/B without editing the ini:** with `[Debug] DevBridge=1`, the whole profile is one command written to `%LOCALAPPDATA%\OutlastVR\dev\cmd.txt`:

```
visprofile 1     -> OcclForce=0, OcclusionSkip=0, OcclGuard=1, OcclProve=1, OcclHold=1,
                    UnionFrustum=1, VisReuse=1, PvsShare=1, OcclPerEye=0
visprofile 0     -> back to the shipped configuration
```

and each piece individually: `occl 0|1`, `occlskip 0|1`, `occlguard 0|1`, `occlpereye 0|1`, `pvsshare 0|1`, `visreuse 0|1`, `unionfrustum 0|1`, `unionnear <uu>`. That is the A/B protocol: flip one thing, read the `[PERF]` line and the picture, flip it back.

**Build/test status:** `tests/perf_visibility_test.py` now also compiles and drives the real `Hook_QueryGetData` **with `OcclPerEye=0`**: it asserts that `VisReuseLive()` never reads the per-eye switch, that each of its three gates really gates, that the guard leaves `OcclForce=1` alone, that with `OcclForce=0` a shared query object never hides a prop (the 2026-11-05 scenario, refused without the per-eye table), that two zeros in a row on one view's object do cull, and that a second eye whose boxes were skipped is never handed a device answer. `scripts/build.bat` builds clean and all four perf suites pass (`perf_switches`, `perf_threading`, `perf_framepath`, `perf_visibility`). Still missing: the headset session that measures whether `OcclForce=0` + `OcclGuard=1` actually wins frame time, and whether the picture is clean.


**Pending caveats:** missing visual test on a headset/real game session (the probe proves the mechanism, not the image); while A8 is active, present avg in the [PERF] report is 0 — that's the goal, not a regression. Phase 4 needs the same visual pass: `[PERF-A3] the shared frame is read in place` in the log says the copy is really gone, and `DirectSwapchain=1` must be judged on a headset (colour, seam, convergence shift) before it could ever become a default.

## Phase 6 — Content (D.5 DetailMode, D.4 particles, B7 launcher profile)

Phases 1–5 cut what the **mod** spends. Phase 6 cuts what the **game** draws. That is a different kind of optimization: it cannot be proved with a timer, only with `draws/frame` and a pair of eyes.

**The design rule: no offsets, no patching, no guessed UE3 names.** Every lever is a UE3 *system setting* the engine already understands, run through `PlayerController.ConsoleCommand` — exactly what the developer types after `con`. A wrong system name fails loudly in the log ("Command not recognized") instead of corrupting memory or the picture, and the whole profile is reversible by replaying a restore list. This is why phase 6 needed no reverse engineering at all.

### The four levers

| Lever | What it costs the game | What it buys | What the player sees |
|---|---|---|---|
| `scale set DetailMode 1` | High-detail props are not processed in a two-view frame | **the only lever that cuts processed primitives AND draw calls** (Epic) | vegetation, papers, debris, decoration disappear — rooms get emptier |
| `scale set ParticleLODBias 2` | particles switch to coarser LODs | particle draws are ~3× a mesh draw (Epic), so this is the cheap D.4 lever | fewer/thinner particles: dust, smoke, embers |
| `scale set DynamicShadows False` | no dynamic shadow update | the +6% the project baseline measured | flat light, lamps stop casting |
| `scale set MaxDrawDistanceScale 0.6` | far decoration is culled | fewer draw calls (not fewer processed primitives) | rooms pop in at a distance |
| `scale set Decals False` | no decal draws | decals are per-view work | blood, posters, grime vanish |

### What was built

- **`[Content]` in `runtime/outlastvr.ini`** — three command lists, `;`-separated (an ini value cannot hold a newline): `Commands1` (performance), `Commands2` (performance+, a superset by system, tightening `MaxDrawDistanceScale` to 0.5 and adding shadows + decals), and `Restore` (the engine's own defaults). `Profile=0` ships it off.
- **`[CONTENT]` in `ol_ue3.cpp`** — `ContentParseList` (trim, drop empty tokens, truncate instead of overflowing), `ContentApply` (runs a list, or the restore list when the profile turns off), and `ContentTick` (game thread, only once `OLUE3_GameplayActive()` is true, paced at 1.5 s, and **re-applied after a level load** because a level load re-creates the world and some system settings go with it). Boot lines print every parsed command, so a session's log states exactly what was applied.
- **A profile CHANGE restores first.** `Commands1` is a subset of `Commands2` by system, so stepping PERFORMANCE+ → PERFORMANCE would otherwise leave shadows and decals off for ever (list 1 never mentions them). `ContentApply` therefore replays `Restore` whenever the profile number changes, and only then - a level-load re-apply of the *same* profile stays idempotent and costs nothing. (This was a real bug the phase-6 test caught before it shipped.)
- **The console runner was refactored** — `Con_RunText(cmd, logOk)` is the shared body; the DevBridge's `con` and phase 6 both call it. A line that fails is always logged.
- **`[PERF] content profile N`** — every perf report names the profile in force, next to `draws/frame`, which is the number DetailMode and MaxDrawDistance must move (shadows and decals mostly do not: they are GPU work on draws that still happen). This is the measurement that decides whether the profile is worth its visual cost.
- **B7 launcher row** — "Performance profile" under a new `PERFORMANCE` group: `FULL DETAIL / PERFORMANCE / PERFORMANCE+`, writing `[Content] Profile` 0/1/2 with the player-visible cost spelled out in the help text. Uses the existing settings page machinery, so it inherits write-on-change, range clamping and the "Outlast is running" warning.
- **Live A/B** — DevBridge `content 0|1|2`, so a session can flip the profile without touching the ini or restarting.

### Why it ships OFF, and what would make it ship ON

It is a content trade, so the default must stay the picture the mod was tuned for. It becomes a default only if a session shows a frame-time win big enough to be worth visible missing props — and the honest way to judge that is the two numbers the repo already prints: `draws/frame` (must drop) and the frame-time line (must improve by more than the noise). `stat splitscreen` via `con` shows the processed-primitive side, which is the half DetailMode is unique in cutting.

### Tests

`tests/perf_content_test.py` compiles the **real** parser, `ContentApply` and `ContentTick` against a stub console and drives them: a `;`-separated profile becomes one command per entry; empty tokens are ignored; an over-long list truncates at `kContentMaxCmds` rather than overflowing; **turning the profile off replays the Restore list, never the performance list**; **switching profile restores first** (so stepping down from PERFORMANCE+ re-enables shadows and decals) while re-applying the same profile does not; the profile only applies in gameplay; and it re-applies after a level load but not inside the settle window. It also checks the shipped ini (DetailMode and ParticleLODBias in both lists, Restore covering every system, no duplicate values) and the launcher row (three choices, the 0/1/2 numbering, the help naming what disappears). `scripts/build.bat` and `launcher/build_launcher.cmd` both build clean, and all five perf suites pass.

### D.4 caveat, stated honestly

The project's own note says D.4 should only be acted on after `TRACKPARTICLERENDERINGSTATS` / `DUMPPARTICLERENDERINGSTATS` show particles on top. The profile includes `ParticleLODBias 2` because it is cheap and reversible, **not** because this build proved particles are the cost. If those reports show particles are not a large share, the honest move is to delete that one line from both lists — the mechanism does not depend on it.

## Phase 7 — The OpenXR delivery pipeline (B3, B4, B5, B6, B9 + the black borders)

Phases 1-6 cut the game's work. Phase 7 cuts the **delivery** work and fixes the one artefact this mod has fought since the beginning: black bars at the sides of the view on a fast head turn.

### The black borders: what they are, and the half that was missing

`docs/VR-RUNTIMES.md` already had the diagnosis right, and phase 7 adds the piece it named as missing. Every PC runtime **reprojects** the frame it was given: between the draw and the scan-out the head moved, so the compositor warps the image. The Khronos frame-submission guide says it plainly — reprojecting a frame rendered for the submitted pose leaves *"just black pulled in on the sides"*. A warp can move pixels; it cannot invent them.

Three things make it worse here, in order: the game presents below the headset's refresh (every synthesised frame is a full-frame warp); **nothing outside the submitted frustum exists**; and the link adds latency, so the runtime predicts further ahead.

`[Stream] EdgeFill=1`  fixed the first half: in `[FITFRUSTUM]` mode the eye image is wider than the picture, and the leftover margin used to be cleared to black — so the fill stretches the picture's own edge over it. The docs are explicit that this is **not enough** on a runtime that honours the declared FOV (SteamVR, VDXR): there the picture *is* the eye image, there is no leftover margin at all, and the first degree of unexpected motion is already black.

**`[Stream] EdgeOverscanDeg` (phase 7) is that missing half: real overscan.** The camera is asked for a frustum wider by N degrees on every edge, the blit maps that wider picture into the same eye image, and the projection layer **declares the wider frustum**. The lens still sees exactly the angles it always did; what changes is that the submitted image now has rendered pixels where the warp used to find black.

Three properties make it safe, and the phase-7 test checks all three:

1. **Angle space, not tangent space.** `OlrOverscan` converts to angles, adds the degrees, converts back. Adding `tan(deg)` would widen least near 0 and most near 90 deg, which is not what "2 degrees more" means to a lens.
2. **The blit target and the declaration are the same function.** `OlrSubmitFov` is used by every fit call and by the projection layer, so they cannot disagree. If the blit targeted the lens while the layer declared the wider frustum, the picture would *shrink* inside the lens — the exact failure a careless implementation produces.
3. **It never runs unless the render got the wider frustum.** `OlrSubmitFov` widens only when `g_overscanLive && g_lensFitOn && g_fitFrustum` — the latch set by `OLXR_LensFitTangents`, which is where the widening is applied. With LensFit off, or the fitted path off, `EdgeOverscanDeg` does nothing at all instead of distorting the picture.

It is applied **after** the union frustum (C2), so the two widenings add rather than replace. Ships at `0` because the cost is real and honest: the same pixel budget spread over more degrees, i.e. part of the sharpness LensFit bought. `2-4` is the useful range. Live: menu slider "Edge margin", or DevBridge `overscan <deg>`.

**This does not fix a runtime that ignores the declared FOV** (Meta PC runtime): there `[FITFRUSTUM]` pre-warps the picture into the runtime's own lens frustum, and the margin comes from `EdgeFill` inside that image instead. The two mechanisms cover the two runtime families.

### B6 — FSR1 (EASU + RCAS)

`[XR] Upscaler=2`, menu "Upscaling: FSR 1". A faithful port of AMD's FidelityFX FSR 1 (MIT, GPUOpen `ffx_fsr1.h` v1.20210629):

- **EASU**, the 32-bit path: the 12-tap kernel is emitted as explicit integer offsets (no `gather4`; same texels, more portable), the direction/length accumulation is the reference's, and the **dering against the nearest 2x2 is kept** — without it the Lanczos-2 negative lobes ring on contrast edges.
- **RCAS** after it: the full clipping solve (`hitMin`/`hitMax` against the 4x ring), the `-0.1875` lobe limit, and the noise weighting, so it sharpens only where the signal cannot clip.
- The **seam clamp is applied to every tap** (`FsrPx`), so an FSR tap can never reach across the side-by-side seam into the other eye. That is the one way this could have been catastrophically wrong.
- **It only runs when scaling up.** `upMode = scalingUp ? g_upscaler : 0` — EASU is an upscaler; at 1:1 its 12 taps would add cost and softness for nothing.
- The Sharpening slider drives RCAS when FSR1 is selected (same slider, AMD's curve).

**The test compiles the embedded shader with `fxc`** (`ps_4_0` and `vs_4_0`), because a shader that does not compile is a black headset, not a slow one. The ported shader was compiled and iterated against `fxc` before it went in: 504 instruction slots.

### B5 — fewer composition layers

Measured, not changed. `[PERF] composition layers: N/frame avg, M max` now reports the layer count every 5 s, so a "fewer layers" change has a number to move. The in-game camcorder case is 4 layers (`projection + flip screen + HUD + focus`); drawing the HUD into the eye image would remove two, but it changes how the HUD is positioned relative to the lens and needs a headset to judge — it is not something to guess at. The measurement is the prerequisite the doc asked for.

### B9 — draw duplication between the eyes

The problem is real and now **measurable**, which is the whole deliverable of a first B9 pass:

- `[PERF] draws per eye: L N R M (R/L x.xx)` — the per-eye split of the draw counters, from `g_olRenderEye`. This turns "the render thread submits 2x the draws" from a claim into a number.
- `[PERF] draw lists: N/M identical` — with `[Perf] DrawFingerprint=1`, a rolling hash of each eye's draw sequence `(primitive type, vertex count, primitive count)` in call order is compared once per frame. **This is the measurement any reuse scheme stands on**: if the two passes are not the same sequence of the same things, call-order reuse is unsound and nothing may be built on it. Ships OFF because it costs two multiplies per draw.

**What the investigation concluded, and why no reuse was shipped:**

- Within UE3/D3D9 there is **no** way to share draw submission between the two views without rewriting the RHI. `DrawIndexedPrimitive` is a per-call D3D9 method; there is no command list, no instancing of a view, no multi-view extension in D3D9. Any "replay the first eye's commands for the second" scheme still issues every call — it only removes the CPU the engine spent *deciding* to issue it, which is what [VISREUSE] (phase 5) already does for the half of visibility the mod owns.
- The one structural lever left is C1's full visibility reuse (the engine's own `ComputeViewVisibility`), which needs the engine's `PrimitiveVisibilityMap` copied between views — reverse-engineering work, not a pipeline change, and explicitly out of scope for a pipeline phase.
- The honest output of B9 is therefore the instrumentation plus this conclusion, so the next attempt starts from data instead of assuming the two lists are identical.

### B3 and B4 — investigated, not shipped, and why

- **B3 (blits before `xrWaitFrame`)**: the blits need the frame and the pose that `ConsumeUpload` produces, and acquiring a swapchain image before `xrBeginFrame` risks `XR_ERROR_CALL_ORDER_INVALID` on runtimes that validate call order. Moving them would require splitting the worker's frame into two phases with the image held across the wait, which is a substantial restructure of the one code path that must never deadlock. **Not done**; the existing structure (capture out of the deadline, blits inside) is documented in the code.
- **B4 (one swapchain, `arraySize=2`)**: Microsoft's OpenXR guidance recommends it, but it changes the acquire/release protocol for both eyes at once and every runtime this mod has been tested on is proven with two swapchains. Doing it wrong means one eye freezes or the two views swap. **Not done** in a pass that cannot verify on a headset; the measurement (`per-eye swapchains ready`) and the fallback design are already in place for a future attempt.

### Tests

`tests/perf_pipeline_test.py` (new):

- extracts the embedded blit shader, un-escapes it and **compiles it with `fxc`** for `ps_4_0` and `vs_4_0`;
- checks EASU's 12 taps, the 4 corner evaluations, the dering, the `rsqrt` normalise, every tap going through the seam clamp, and RCAS's clipping solve and lobe limit;
- checks the upscaler is a three-mode setting that reaches the shader and is disabled at 1:1;
- checks the overscan is angle-space, writes back, has the tan guard, is applied after the union, that the blit target and the declaration use the same function, and that it cannot widen a declaration the render did not widen;
- checks B9's per-eye counters, fingerprint and `[PERF]` lines exist and ship OFF;
- checks the layer-count measurement and that every new ini key is both present and read.

All six perf suites pass (`perf_switches`, `perf_threading`, `perf_framepath`, `perf_visibility`, `perf_content`, `perf_pipeline`) and `scripts/build.bat` builds clean. Still missing, as for every phase: the headset session. `EdgeOverscanDeg` in particular is a *taste* setting — 2 degrees of margin against 1 degree of softness is a judgement only the player can make.

---

# Part 2 - The measurement protocol



---

# Part 3 - The field-fix change log

### Phase 8 — the six field fixes

| Fix | Ini | Where |
|---|---|---|
| logging can be turned off completely (no file, no writer, no formatting) | `[General] Log=1` | `d3d9_proxy.cpp` `OpenLog` / `Log`; `ol_ue3.cpp` probe CSV |
| interaction aim gets a bounded cone (a correction, not a replacement) | `[Input] AimAssistConeDeg=6`, `AimAssistMaxDeg=4` | `ol_ue3.cpp` `AimBend` / `Hook_NativePlayerMove`; `ol_interact.cpp` `OLInteract_AimAssistTarget` |
| a door swinging through Miles cannot pull a hand | — | `ol_interact.cpp` `s_pushPlane` (separate from the knob anchor) + `kAnchorMaxUU` in `[ANCHOR]` |
| the face-pinned camcorder can be grabbed again | — | `ol_interact.cpp` `CamRaise` reads the held grip; `Holster` does not undo it |
| HYBRID behaves as PHYSICAL except the walk stick's forward | `[Motion] ClimbMode` | `ol_interact.cpp` `ClimbIsPhysicalLike`, `ClimbStickRuleHybrid` |
| the camcorder HUD hides on the frame the menu opens | — | `ol_interact.cpp` `g_hudHiddenNow`; `ol_xr.cpp` `OLInteract_RefreshCamHudMenu` before the layer |

Covered by `tests/fixes_test.py`; `tests/climb_modes_test.py` now asserts HYBRID and PHYSICAL agree
on every rule except forward.

### Phase 9 — six legacy fixes

| Fix | Where | What was wrong |
|---|---|---|
| face-pinned camera can be grabbed, once | `ol_interact.cpp` `CamRaise`, `s_faceGrabbed` | the grab was a level check and the auto-pin re-adopted the camera every frame: grab → re-pin → grab, i.e. a continuous buzz with no grab |
| reload sound starts with the animation | `ol_ue3.cpp` `OLUE3_BeginBatteryReload` | `BlendInTime = 0.55` delays the montage's effective start, swallowing the t=0 sound notify. Now 0 (the IK eases the arm separately) |
| hand lands on the handle, oriented | `ol_interact.cpp` `s_doorHandleDir/Face`, `OLInteract_HandAnchorOrientation`; `ol_ue3.cpp` `WorldDirToComp` | the anchor gave position + yaw only, so the hand could sit on the knob facing anywhere |
| the lower animation plays | `ol_interact.cpp` `kFaceLowerAnimMs` | the pin released on the state change, handing the arm to IK ~0.9 s before the game's animation ended |
| palm-down fingers do not clip the door | `ol_interact.cpp` open-hand collision box | the radius used only the component along the panel normal, which collapses when the fingers lie across the panel |
| a light push moves the door gently | `ol_interact.cpp` `kPushGain`, `s_pushPerpPrev` | the push was a position solve (`(target−angle)/dt`), so a grazing hand commanded a large velocity |

Covered by `tests/legacy_fixes_test.py`.

### Phase 10 — hand, door and camera (second round)

| Fix | Where | What was wrong |
|---|---|---|
| open hand goes through the door | `ol_interact.cpp` `OLInteract_HandPushOut`; `ol_ue3.cpp` solver | **phase-8 regression**: the push plane was written and never read, so removing the arm anchor left an open hand with no collision at all. Now a penetration response: push the hand target out by its depth past the panel, nothing otherwise |
| hand way above the knob / inside the door | `ol_interact.cpp` handle anchor | anchored to the WRIST's height at grab time instead of the knob's Z; the handle's face offset was computed and discarded |
| grabbing from too far | `DoorGrabReachUU` | fixed 26 uu radius, now 8-45 and live |
| live calibration | menu DOORS: hand on knob up/toward/sideways, wrist off the door, grab reach, reset | asked for: the hand is not a modelled body, so it has to be dialled in |
| pronated fingers through the door | collision radius | used only the extent along the panel normal, which collapses when the fingers lie across it |
| doors silent after a save load | `ol_sound.cpp` `OLSound_WorldChanged`, `SoundOurObj` | a save retires every Wwise object; the mod kept posting to the retired ones |
| grab showed the lower animation | `ol_interact.cpp` face grab | the grab entered the lower state, so the model appeared at the eye and the arm played the lower for 900 ms first |
| R3 lowered instead of pinning | `ol_interact.cpp` `s_faceLockedAt` | a level grip check grabbed the camera straight back off the face on the frames around the pin |

Covered by `tests/legacy_fixes_test.py` and `tests/camera_and_sound_test.py`.

### Phase 11 — third round

| Fix | Where | What was wrong |
|---|---|---|
| snap turn turned the screen black | `ol_motion.cpp` `SnapTurn` | `OLXR_Blink(70)` was called **every frame** of the turn, re-arming a 70 ms black window 60-90x a second |
| both hands had no collision | `ol_interact.cpp` open-hand collision | phase 10 published the plane at 11 cm while `contact` fired at 7 cm: a limit cycle, no collision half the frames. Now a geometric test against the panel, independent of `contact` |
| no push | same | the push solver also reads `contact`; the geometric test restores it |
| handle placement | `OlInteract_HandGrabGuide` + solver | a knob-**center** guide point per hand, with an eased magnet, instead of a tuned anchor that moves with the door |
| door button sometimes dead | `d3d9_proxy.cpp` `LeftGripBlocksUse` | the fallback `gripL > 0.6` let a plain **sprint** swallow Use |
| camera grab felt late | `OLInteract_CamGrabSnap` | the IK target smoothing eased the hand in on the grab frame |
| FSR1 could never run | `ol_xr.cpp` `Upscaler` read | `... ? 1 : 0` collapsed the mode `2` back to `1` |

New defaults (ini + launcher): `TurnMode=0` (SMOOTH), `SmoothTurnDegPerSec=180`,
`FreezeCameraRotation=0`, `RaiseToEyeReachM=0.140`, `RenderScale=1.00`, `Upscaler=2` (FSR1),
`EdgeOverscanDeg=2.0`, `RoomscaleWalk=0`. (Round 3 shipped 0.120 / 0.80 / roomscale on; the
release defaults raised the camcorder distance to 14 cm, the render scale to 100% and turned
roomscale walking off - see the note under *Phase 12n* at the end of Part 3.)

Covered by `tests/round3_test.py`.

### Phase 12 — back to the shipped behaviour

Phase 11 was reverted for the hand, the camera and the blink: on a real headset those changes were
worse than what shipped. `old/` is the reference; the door block is functionally identical to it again.

| Reverted | Why | Where |
|---|---|---|
| one blink per turn | the black dip **is** the game's cover for a snap turn, meant to run for the whole turn | `ol_motion.cpp` `SnapTurn` |
| knob-height anchor + guide/magnet | the knob's Z is not the height the hand closes at; the magnet pulled the hand **off** real handles | `ol_interact.cpp` anchor; `OLInteract_HandGrabGuide` removed |
| lever-axis wrist roll | the shipped wrist only yaws with the swing | `ol_ue3.cpp`; `OLInteract_HandAnchorOrientation`, `WorldDirToComp` removed |
| geometric hand collision | reacted **a frame late** (the hand was through before it was recognised) | `ol_interact.cpp`; back to the contact-gated anchor |
| speed-based push | disturbed `anyPush`/`contact`, which the auto open/close finish is driven from | `ol_interact.cpp` push solver |
| grab latch / arming window / snap | the shipped fresh squeeze works, and every extra guard swallowed a real one | `ol_interact.cpp` `CamRaise`; `OLInteract_CamGrabSnap` removed |
| self-registered Wwise object | no listener relation, so its events played **nowhere**: silent doors | `ol_sound.cpp` `SoundPortalObj` |

Kept from phases 10-12 because they measured better:

| Kept | Why |
|---|---|
| `g_contactUU = 14` (menu **Hand collision range**, `[Motion] HandCollisionRangeUU`) | the shipped 7 uu is thinner than a palm, so the ring came late |
| pronated-hand contact radius (`acrossNormal` / `edgeRadius`, larger wins) | a palm-down hand no longer collapses to the edge radius |
| `kFaceLowerAnimMs = 900` | the game's own lower animation gets to finish before IK takes the arm back |
| `OLSound_OnWorldChanged()` | forgetting the cached Wwise ids on a world change is what keeps doors audible after a save load |
| `LeftGripBlocksUse` without the `gripL > 0.6` fallback | a sprint must never swallow Use |

Covered by `tests/round3_test.py`, `tests/legacy_fixes_test.py`, `tests/camera_and_sound_test.py` and
`tests/fixes_test.py` (all rewritten to assert the shipped behaviour, not loosened).

Four suites (`camcorder_hud_test`, `launcher_resolution_slider_test`, `mouse_use_test`,
`pad_press_test`) fail identically on the untouched `old/` tree: their harness stubs no longer match the
installed mingw-w64 headers (`_countof`, `wcsncasecmp`, `InterlockedExchange`, `LONG`). Toolchain drift in
the tests, not a regression in the mod.

### Phase 12b — the handle, the door's pull, the face grab and the defaults

| Fix | Where | What was wrong |
|---|---|---|
| hand inside the door on a grab | `ol_interact.cpp` handle anchor | the anchor used the knob's own depth (about 6 uu on a flush handle) — thinner than a hand. Now at least `g_pushDepthUU` (11 uu) |
| doors pulled the hand / arm | `ol_ue3.cpp` solver, `OLInteract_HandAnchorHand` | the handle gain moves the knob 2-3x faster than the hand; the anchor was followed unconditionally. Pull now eases off between 42 and 78 uu from the real hand |
| camcorder could not be grabbed off the face | `ol_interact.cpp` grab, auto-pin, `OLInteract_RightArmNative`, `OLInteract_CamVisual` | `H_IN_HAND` was set but the game's state stayed 1, so the auto-pin re-adopted it, the right arm stayed native and the model stayed hidden. The grab now asks the game to lower, and all three respect `H_IN_HAND` |
| arms appeared late at level start | `ol_interact.cpp` startup camcorder guard | a 1.5 s settle was required even when the camera was never raised. Now 200 ms unless `s_camSawUp` |

New defaults (ini + launcher + code fallbacks): 100% world size, blink while snapping **off**, walk
direction **BODY**, freeze camera rotation off, climbing **A BUTTON**, write log files **off**, body
alignment **2.0 s**.

Covered by `tests/phase12b_test.py`; `tests/fixes_test.py` section 1 now expects `Log=0`.

### Phase 12m — ledge walk: the game's move, gated on BOTH hands, and the left hand keeps hold

On top of `12l` (the walk stick goes to the game on a hanging ledge, in every climb mode), two rules:

**The ledge walk only runs with BOTH hands on the ledge.** The game's sideways walk is not started on a hand
that is not holding, so `OLInteract_FilterMoveStick` stops the stick while hanging (`lm 4/5`) unless
`s_hold[0] && s_hold[1]`:

```cpp
if (ClimbIsPhysicalLike(g_climbMode) && (s_lm == 4 || s_lm == 5) && !s_pc) {
    if (!(s_hold[0] && s_hold[1])) { *x = 0.0f; *y = 0.0f; return; }
}
```

It lives in the filter, **not** in `ClimbStickRule`, on purpose: that rule is compiled on its own by
`tests/climb_modes_test.py`, and keeping it the single rule PHYSICAL and HYBRID share is what stops the two
modes drifting apart. The refusal is logged once every 3 s with which hand is missing.

**The left hand does not let go of a ledge he cannot fall from.** Taking the auto-grabbed hand with the grip
used to make it fully the player's, so opening that grip dropped him. On a ledge the game will not let him
fall, so neither does the mod: if the left grip opens while the **right hand is not holding**, Miles keeps
his left hand on the ledge. With the right hand holding, the left is still releasable - which is exactly
what the two-hand ledge walk needs.

| Left grip | Right hand | Result |
|---|---|---|
| closed | holding | both hands on the ledge - the walk stick works (game's animation) |
| opened | holding | left hand lets go - one-handed |
| opened | not holding | Miles keeps his left hand on the ledge (no drop) |
| closed | not holding | normal |

`tests/climb_shimmy_test.py` covers these (sections 6 and 7) plus the `12l` rules.


### Phase 12l — DEFAULT: the ledge walk is the GAME's, on the stick, in every climb mode

Everything from the shimmy experiment is **removed** - the hand reader, the re-grab, the marker hand-over,
the per-hand reach limit, the stick walk, the "keep the left hand" latch and the right hand's edge
assignment. None of it is in the build.

**Walking along a ledge is a built-in Outlast move** (`LocomotionMode 4` hanging, `5` shimmying) with its own
animation. What blocked it was the mod: `ClimbStickRule` answered `CLIMB_STICK_LOCKED` for `lm == 4 || lm == 5`
("the hands move him"), so the walk stick was zeroed for the game and the move could never start.

```cpp
if (ladderHold) return CLIMB_STICK_FREE;   // a hand on a rung, feet on the floor
if (edgeCarry)  return CLIMB_STICK_LOCKED; // a hand-carried climb: the hands move him
return CLIMB_STICK_FREE;                   // ...including a hanging ledge: the GAME walks it
```

| Situation | Walk stick |
|---|---|
| Hanging from a ledge (`lm 4` / `5`) | **the game's own** - push sideways and Miles shimmies with the game's animation |
| Hand-carried climb (`edgeCarry`) | kept off - the hands move him |
| Ladder | unchanged: down-only mid-ladder, free at the top and with a hand on a rung |
| A BUTTON | unchanged (never touched this) |

This is the default in **PHYSICAL, HYBRID and A BUTTON**, which is the behaviour the player asked for the
release. `ClimbStickRuleHybrid` still falls back to the same shared rule, so the modes cannot drift.

`tests/climb_shimmy_test.py` now asserts the five rules above, including that none of the removed experiment
exists.


### Phase 12k — the hand drives the shimmy, and the grip re-grabs where the hand is

The log had shown `edges=2/2`, `ledges=6` and **no `[CLIMBSHIMMY]` line at all**. Two wrong readings were to
blame, and the player's description gave the right one:

> "move the left hand to the left while holding the edge throws the body to the right, and grabbing further
> from the previous segment plays Miles's standard ledge-walk move"

**The grip cannot be the input.** A hanging hand is anchored to `s_holdW` by the arm solver - that is what a
hold is - so the *grip* never moves and any test based on it reads 0 for ever. **The CONTROLLER does move**
(the grip only follows it while the arm can still reach). So the walk is read as:

| Step | What happens |
|---|---|
| the player moves a hand along the ledge | `ShimmyHandAlong` measures the **hand** against the grip it holds, along the edge's own direction |
| it passes `kShimmyReGrabUU = 22` uu | the grip **re-grabs where the hand is** - a clear new hold further along - and `ShimmyHandover` walks it over the marker chain |
| the grip would sit further than `kShimmyHandReachUU = 55` uu from the body | the hand takes **only what is left** and waits: that is the per-hand limit, and the body has to catch up before it can grab again |
| a grip re-grabbed | Miles is carried by that amount through the game's own **ledge-walk move** (`AActor::Move`), and **both grips travel with him** so the hands and the lip never separate |

`kShimmyMaxStepUU = 40` rejects a tracker pop as a reach. The walk is hand-driven again, so PHYSICAL and
HYBRID need nothing from the stick - the earlier stick-driven block and its dead predicate are gone.

**The left hand does not let go** (kept from the previous round): opening the left grip while the right hand
is not holding keeps Miles's hand on the ledge, because the game does not let him fall from there either.

Diagnostics, per event:

```
[OLVR][CLIMBSHIMMY] left hand re-grabbed 24 uu further along (segment 2)
[OLVR][CLIMBSHIMMY] Miles walked 24 uu along the ledge (segment 2)
[OLVR][CLIMBSHIMMY] the engine refused a 24 uu sideways step - a wall or the edge's end
[OLVR][CLIMBSHIMMY] cannot walk: no hand holds a ledge segment (ledges=6)
[OLVR][CLIMBGRAB] the left grip opened without the right hand holding - Miles keeps his hand on the ledge
```

`tests/climb_shimmy_test.py` covers the six rules above.


### Phase 12j — the shimmy is the STICK's, and the left hand refuses to let go

The log settled it: `edges=2/2`, `ledges=6`, and **not one `[CLIMBSHIMMY]` line** in the whole run.

**Why every hand-driven attempt failed.** A hanging hand is **anchored to `s_holdW`** by the arm solver -
that is the whole point of a hold. So the hand never travels in the room, `ShimmySlide` always measured 0,
and the hand-over never fired. Detecting the player's hand motion cannot drive a ledge walk. The old
`ShimmySlide` (per-hand room-position reference) is **deleted**.

**What it is now, as the player suggested:** the **walk stick's sideways push** walks the ledge.

* it slides **both grips** along the edge chain (`ShimmyHandover`, marker join `kShimmyJoinUU = 60`); if the
  chain ends, the hand slides along the current marker instead of refusing;
* a grip may only walk **`kShimmyHandReachUU = 55` uu** from the body - the "a hand can only walk so far"
  rule - and once it is at that limit the **body** follows (`AActor::Move`) and **takes both grips with it**,
  so the hands and the lip never separate;
* the step is **frame-rate independent** (`s_shimmyDt`, published by the tick) and only runs when
  `OLUE3_HeroMoveReady()`;
* it works in **PHYSICAL and HYBRID** - the stick is otherwise `CLIMB_STICK_LOCKED` on a ledge, so nothing
  is fighting it. The dead `ClimbShimmyStick` predicate is removed.

**The left hand no longer lets go.** Taking the auto-grabbed hand with the grip used to make it fully the
player's: opening that grip while the right hand was not holding dropped him. On a ledge he cannot fall
from, the game does not let him go either - so if the left grip opens and the right hand is **not** holding,
Miles **keeps his left hand on the ledge** (and the log says so, once). The hand is still the player's to
walk; it just cannot be released into a drop the game would refuse.

Diagnostics (per event, never per frame):

```
[OLVR][CLIMBSHIMMY] walked 1.6 uu along the ledge (stick +0.82, segment 2)
[OLVR][CLIMBSHIMMY] the engine refused a 1.6 uu sideways step - a wall or the edge's end
[OLVR][CLIMBSHIMMY] cannot walk: no hand holds a ledge segment (edges=-1/-1 ledges=6)
[OLVR][CLIMBGRAB] the left grip opened without the right hand holding - Miles keeps his hand on the ledge
```

The last two are the two ways a walk can do nothing, which is what the previous logs could not tell apart.

`tests/climb_shimmy_test.py` now covers the five rules above.


### Phase 12i — the shimmy was overwritten every frame, and the hang grab's filter

The log told the story: `[CLIMBSHIMMY] hands walked 0 uu ... (segment 2, handed over to 2)` - always **0**,
always back to **segment 2**.

| Fault | Where | What was wrong |
|---|---|---|
| the hand always lands on the same segment | `ol_interact.cpp` `PhysAutoCatch` | it re-snapped `s_holdW[0]`/`s_pcEdge[0]` to the nearest marker **every frame**, so the shimmy was undone one frame after it was made. It now re-aims only when the hand is new, when the edge was lost, or right after the shimmy moved him (`s_shimmyMoved`) |
| the slide always read 0 | `ShimmySlide` | the reference was the hand's room position but the **grip** was the thing being moved - and it was reset on every segment change, so a 0 came back out. It is a per-hand reference now, with a `kShimmyMaxStepUU` guard against tracker pops |
| the right hand could never walk | `PhysHang` | `s_pcEdge[1]` was **never assigned** - only the auto-catch set a segment. The right hand hung on its grip with no edge (the log: `edges=2/-1` while `grips=11`). It takes the nearest edge under that hand when the grip closes |
| "any impulse climbs him back up" | `PhysStroke` | the pull reference is measured against the head, so the body being carried along the ledge read as a PULL (A). The reference is re-taken while a shimmy is running and for 250 ms after (`s_shimmyMovedMs`) |
| the edge chain ended after one marker | `ShimmyHandover` | the join test was 20 uu; Outlast's marker ends do not meet that tightly, so the walk stopped. Now `kShimmyJoinUU = 60`, and when there is no neighbour the hand **slides along the current segment** instead of refusing |
| a hang ledge was late to grab | `PcFindLedge` | in the air it required the shipped "lip over his eyes" rule, so a lip **level with his eyes** - the one you jump at to hang from - was rejected for the first frames of the drop. A lip at/just under the eyes now counts as a hang lip; a platform genuinely over the eyes still takes the climb rule |

Diagnostics added (per event, never per frame):

```
[OLVR][CLIMBSHIMMY] left hand handed over: segment 2 -> 3 (slid 14.0 uu)
[OLVR][CLIMBSHIMMY] right hand slid 9.0 uu but the ledge ends there (segment 5 of 6)
[OLVR][CLIMBGRAB] the right hand took the ledge too (segment 3, 18 uu) - both hands can walk it
```

`tests/climb_shimmy_test.py` covers the hand-over, the hybrid stick, the immediate hang grab and the log.


### Phase 12h — ledge shimmy, and the late hang grab

**Shimmy (walking a ledge while hanging).** A hang holds ONE edge segment (`OLLedgeMarker` pairs are a
chain, so an edge is many segments). Walking along it is now the hands' job: a hand that slides sideways
along the edge hands over to the **next segment of the chain** (`ShimmyHandover`, walking both directions,
20 uu join tolerance) and Miles is carried by exactly the amount the hands travelled, through the engine's
own swept move (`AActor::Move`, `kShimmyBodyGain = 1.0`). The slide is read **against the head**
(`ShimmySlide`), so the game moving him cannot fake one, and only the component **along** the edge counts.
The auto-grabbed left hand is skipped until the player takes it with the grip, so the game's own catch is
never dragged sideways.

| Mode | Shimmy |
|---|---|
| PHYSICAL | hands only - take a hand off, put it further along, follow with the other |
| HYBRID | the same, **and** the walk stick's sideways push (`ClimbShimmyStick`, 2.5 uu/frame) |
| A BUTTON | unchanged (the game's own ledge walk) |

The stick path is deliberately narrow: HYBRID only, only where the stick is otherwise `LOCKED` (a ledge -
never a ladder), only `LocomotionMode 4/5`, and only past a 0.25 deadzone so a resting stick cannot walk
him off.

**The late hang grab.** `PhysAutoCatch` used to reach for a ledge on `move 4` (already hanging), `move 1`
(falling) or a *climb-up* special move. A ledge you jump at **to hang from** is entered as `move 2` with a
**hang** special move (`>= 40`, `bCanLedgeHang`), so the hand did not reach until the game had already put
him in the hang - the reported delay ("jumping UP catches instantly, a hang ledge takes a while"). The
catch now also runs on the hang move, from the frame the game enters it, so the hand is already on the edge
when the hang starts.

**Log, as requested.** `[CLIMBDIAG]` writes **one line per change** of the climbing picture - never per
frame:

```
[OLVR][CLIMBDIAG] mode=4 sm=0 state=3 holds=11 auto=00 ownedLeft=1 edges=2/5 ledges=37 hands:LR grips=11 move=ok ladder=0
[OLVR][CLIMBSHIMMY] hands walked 3 uu along the ledge (segment 2, handed over to 2) - Miles follows
[OLVR][CLIMBSHIMMY] the stick walks him 2 uu along the ledge (hybrid)
[OLVR][CLIMBGRAB] his left hand takes the ledge he jumps at to hang - the game's own catch follows
```

`mode`/`sm` come from the pawn (0 walk, 2 special move, 4 hang, 8 locker), `state` is the mod's climb state,
`holds`/`auto` are the two hands, `ownedLeft` says whether the player took the auto-grab, `edges` are the
ledge segments each hand is on and `ledges` how many are in range. A shimmy that does not move him, or a
hand that will not take the edge, reads straight off those.

Covered by the new `tests/climb_shimmy_test.py` (4 sections) plus the existing climbing suites.


### Phase 12g — B restored to old/, and the interference REMOVED (not patched)

The whole B pipeline was diffed function by function against `old/` and everything I had added was
**deleted**: `consumedDown`/`diagLast` in the sampler, the `[USEDIAG]` logging in `MouseUseContext`, the
sampler, `Hook_XiGetState` and `SyncInput`, and the extra guard in `PhysicalCrouch`. What remains:

| Function | State |
|---|---|
| `MapPadButtons`, `ReliablePadButtons`, `MenuTaps`, `LatchPresses`, `LatchForget` | `old/` verbatim |
| `MouseUseContext` | `old/` verbatim |
| `PhysicalCrouch` | `old/` verbatim |
| `OLMouseUse::Sample` | `old/` + one line (below) |
| `OLMouseUse::Cancel` | `old/` verbatim |
| `OLMouseUse::Release` | new: retries a release, never touches the press |
| `MouseUseWatchdog` | `old/` split in two: a real context loss `Cancel`s, a gap `Release`s |
| `OLProxy_MouseUseSample` | `old/` + a `missed` argument |
| `LeftGripBlocksUse` | **not** restored: `old/`'s `gripL > 0.6` fallback swallowed Use under sprint (already documented as "opening a door does not work every time") |

**The interference that was removed:** `ol_xr.cpp` reports "no sample" -
`OLProxy_MouseUseSample(0,0,0)` - whenever the session is not `FOCUSED` or a frame failed. Under Virtual
Desktop / Link that happens while the game is playing normally. `OLProxy_MouseUseSample` and
`MouseUseWatchdog` both ran **`Cancel`** in that case, which in `old/`:

* **released** the synthetic left mouse in the middle of a press, and
* re-armed the sampler so **the press could never become a click** - the press was eaten, and the player
  pressed B again.

That is the "I have to press B several times". Both call sites now only retry a pending **release**
(`Release`); `Cancel` stays for a state that really ended (a menu, lost focus, shutdown). A missing
sample also carries no information about the button any more instead of looking like "B released".

**The second, smaller one:** in `Sample`, a press that arrived while `canStart` ("gameplay is running")
was briefly false was latched by `previousDown` and dropped - the same shape, one frame wide. The press
now stays pending (`previousDown = false`) and clicks on the first frame the game will take it. A press
refused **on purpose** (`!allowed`: a menu, lost focus) is still spent, so it cannot fire when a menu
closes.

Covered by `tests/use_press_test.py`, which asserts the five cases (one click per press; a menu-refused
press never becomes a delayed click; a gap retries the release; `Cancel` still suppresses; a press held
across a gameplay gap clicks when gameplay returns) and also asserts the Python mirror still matches the
real header.


### Phase 12f — "I have to press B several times": the watchdog was spending the press

The frame-spike watchdog cancelled the Use press. `MouseUseWatchdog` runs when a sample is older than
200 ms - any hitch - and it called `Cancel`, which **marks the press spent**. When the press was an
*armed* one (B hit while `GameplayActive()` was briefly false, common around a locker / scripted move),
the cancel turned it into "already used, never clicked", and the player pressed again. A hold could also
be released in the middle of a press.

`Cancel` now means only "the state really ended" (a menu, lost focus, shutdown). A **missed sample** calls
the new `Release`, which just retries the release and never spends the press:

| Situation | Before | Now |
|---|---|---|
| 200 ms without a sample, press armed | press spent, never clicked | still armed, clicks when gameplay returns |
| 200 ms without a sample, click held | text left mouse released mid-press | release retried, hold untouched |
| a menu opens / focus lost | press spent (correct) | unchanged |
| a real click followed by a chance release | — | cannot become a second click |

Covered by `tests/use_press_test.py` (7 cases now, including 5 and 5b).

### The [USE] diagnostic log

`[General] Log=1` in `outlastvr.ini` now writes one line per physical B press, so a press that "did
nothing" can be read directly. Nothing runs per frame: presses are debounced to one line per 120 ms.

```
[OLVR][USE] B raw from the controller (edge 3)          <- the controller press reached the mod
[OLVR][USE] B down -> CLICKED | focused=1 menu=0/0 gripOwned=0(busy=0) gameplay=1 gripL=0.02 held=0
[OLVR][USEDIAG] B release -> left mouse held=0 pending=0
[OLVR][USEDIAG] use context BLOCKED (game=1 fg=0 menuMod=0 menuGame=0)   <- only when it CHANGES
[OLVR][USE] B down (pad) -> mapped=0x2000 add=0x0000 rem=0x0000 inMenu=0 layout=mouse gameplay=1
```

How to read the outcome word:

| Word | Meaning | Where the fault is |
|---|---|---|
| `ARMED` | gameplay was not running when B was pressed | the press is kept and fires when it returns; a *pattern* of these means the game is reporting "not gameplay" too often (the `gameplay=` flag plus the nearest `[SCENESTATE]` line says which) |
| `REFUSED` | focus, a menu, or a mod-owned left grip blocked it | read `focused`, `menu=%d/%d`, `gripOwned/busy`: a `gripOwned=1` that keeps appearing means the left grip is being taken by an interaction |
| `CLICKED` | the synthetic left click was sent | if the game still ignored it, the press reached Windows and the game did not react - that is a different bug |
| `B raw` missing entirely | the press never reached the mod | runtime / binding, not this code |


Two reports, one root cause in the Use sampler and one collision in the crouch layout.

**B did not get you out of the locker, and sometimes B did nothing the first time.**
In the mouse layout (`[Input] MouseUse=1`, the default) B is not a pad button at all: it is turned into a
**simulated left click**, so it runs through `OLMouseUse::Sample` in `src/ol_mouse_use.h`. That sampler
required `canStart` (= `OLUE3_GameplayActive()`) to click, and **recorded every sample as "previous"
whether the click happened or not**. `GameplayActive()` goes false for a frame or two around a transition
(the locker enter / exit move is a `SpecialMove`, and a scripted move / brief menu flag does the same), so
a press that landed in that gap was consumed with no click - and because the button was already down, no
new press edge was ever seen. Holding B therefore did nothing at all.

The press is now only *spent* when it was acted on, or refused **on purpose** (a menu, lost focus). One
that merely failed because gameplay was not running yet stays armed and fires on the first frame it is:

| Sample | Before | Now |
|---|---|---|
| B pressed while `GameplayActive()` is false | consumed, no click, never retried | kept armed; clicks as soon as gameplay runs |
| B pressed with a menu / no focus | consumed | consumed (must not click when the menu closes) |
| B held across a transition | dead | clicks once, on the first frame that allows it |
| B held a long time | one click | one click (unchanged) |

**A physical-crouch pulse could swallow a B press.** In the legacy layout (`MouseUse=0`) B is
`OLA_CrouchToggle` too, and `PhysicalCrouch` adds its own `0x2000` pulse. When the pulse landed on a B the
player was already holding, the two merged into a single press: that press produced one toggle and the
next B press looked like it did nothing. The pulse is now withheld while B is held (the crouch intent is
retried next frame), so the player's own press is always its own toggle.

Covered by the new `tests/use_press_test.py` (four behavioural cases over the sampler), which runs under
Python alone - no g++ needed.


The three camcorder paths the player named (pin with R3, take it off his face physically while pinned,
lower it with R3) are **the `old/` (V1) code again**, restored function by function:

| Function | State now |
|---|---|
| `CamHoldGesture` (R3 pin / raise / lower) | `old/` verbatim, plus one line (below) |
| `CamRaise` (the physical grab at the face) | `old/` verbatim |
| `Holster` | `old/` verbatim |
| `OLInteract_CamVisual` | `old/` branch order |
| `OLInteract_RightArmNative` | `old/` rules |
| `OLInteract_FaceCamBusy` | identical to `old/` already |

Everything added over the last rounds on that path is gone: `s_camGrabbedAtFace`, the "spend the squeeze"
hack, the `!s_camByGesture` grab guard, the forced `H_HOLSTERED` at the end of the lower and the separate
held branch in `CamVisual`. What is kept, because it is what `old/` needs too:

* **the lower's dwell** (`kFaceLowerAnimMs = 900`, kept from the shipped behaviour) — with the early
  `return` that holds the arm with the game for the animation;
* **`s_hState == H_IN_HAND` must win in `RightArmNative`** — `old/`'s rule returns 1 for the game's arm
  whenever the state is 1 and the hand is at the eye, and that includes the frames after a grab when the
  game's state lags. A camera in your hand has to be the controller's arm or the grab has no effect;
* **`OLInteract_CamInHandAtFace`** (not in `old/`) — the hand is hidden only while the camera is genuinely
  up at the eye, so raising it to look through never leaves the empty hand on screen.

The one line added to `CamHoldGesture` fixes the report that survived every earlier attempt:

> **Holding R3 to lower a camera pinned at his face**: the game's lower animation starts in
> `CamHoldGesture`, and the tick `return`s for its whole ~0.9 s dwell **before `Holster` runs**. So
> `s_camBlend` was never brought down during the animation: inheriting `H_IN_HAND` / blend 1 (from a
> physical face grab) the model was still *in the hand* when the animation ended and only then glided to
> the waist — "the camera still goes to Miles's hand after the lower animation finishes". The start of the
> lower now drops the hand state (`H_HOLSTERED`, `s_camBlend = 0`), so the end of the animation is the
> waist and there is no hand step at all. Releasing the grip afterwards keeps it on the hip.

Door: only the magnet's aim was touched. The guide point sat `-5 uu` below the knob's centre and pulled the
hand too far down ("it pulls too much toward the bottom of the knob"); it is now
`kHandleGuideDownUU = 2.0f`, so the palm covers the knob instead of hanging under it.

Covered by `tests/phase12b_test.py`, `tests/fixes_test.py`, `tests/camera_and_sound_test.py`,
`tests/legacy_fixes_test.py` and `tests/round3_test.py`, all back to asserting the V1 grab.


Four reports from playing, all of them in the camcorder/handle state machines.

| Report | Where | What was wrong |
|---|---|---|
| holding R3 to lower it ends in his hand, *then* glides to the waist | `ol_interact.cpp` `Holster` / `CamRaise` order, grab latch | the face grab set a grab latch and **left `s_gripEdge[1]` live**. The `Holster` runs *before* `CamRaise` in the tick, so on the next frame it saw `H_HOLSTERED` + a live squeeze, took it for a grab at the **hip** and set `H_IN_HAND` — the state that owns the camera and the one an R3 lower drags through the hand first. It also let a release of the stick click landing near a grab fire the grab and cancel the lower |
| the face grab stopped working | `ol_interact.cpp` `CamRaise` | the same collision: a lower (or the holster) took ownership between the squeeze and the grab, so the grab was cancelled on the frame it landed |
| the handle magnet stopped pulling the hand onto the knob | `ol_ue3.cpp` anchor apply | the solver had been changed to treat the published anchor as the final position while `ol_interact` still mixed it towards the controller by the hold amount — the two disagreed and the hand did not reach the knob. Restored to the shipped formula; the real fault was the hold amount (below) |
| the handle magnet works but takes too long | `ol_interact.cpp` anchor hold | the hold was ramped in at 18/s and, worse, released 300 ms after the grab, so a grab was seen arriving and then stopped being pulled altogether |
| the hand stays stuck to the knob after releasing the grip | `ol_interact.cpp` anchor hold | the released hold decayed at 9/s (~0.5 s) with the anchor still live, so the hand kept following the handle |
| the hand can be pulled off the knob while squeezing it | `ol_interact.cpp` anchor lifetime, let-go checks | the anchor was released **300 ms** after the grab "so the door passes through the hand", and a 60 cm hand-travel check let go of the knob outright |

What changed:

* **A face grab spends the squeeze.** `s_gripEdge[1] = false` on the grab frame, exactly as the hip grab
  does, so the `Holster` can no longer turn a grab at the face into an `H_IN_HAND` hold. This is the root
  of both camera reports: with it, the grab's state is just "grip closed on the camera" and the only
  hand → hip move is the holster's own glide.
* **A lower in flight outranks the grab.** The grab also requires `!s_camByGesture`, so releasing the
  stick click next to a grab can no longer cancel the lower.
* **The grab owns nothing.** The face grab has its own latch (`s_camGrabbedAtFace`); `s_hState` stays
  `H_HOLSTERED`, so an R3 lower always ends at the waist. `s_camBlend` is not forced, so letting go eases
  out of the hand at 1/0.28 s in one move.
* **Held means held.** One held branch in `OLInteract_CamVisual` (`s_hState == H_IN_HAND ||
  s_camGrabbedAtFace`) ahead of the raise/lower eye zone and the state-lag path, both of which also guard
  on the latch. Off the eye the model is in the hand at `blend = 1`; at the eye model and hand hide and
  only the screen shows. `CamInHandAtFace` requires `s_dEye < EyeLeave()`, so the controller hand is not
  thrown away while the game's state catches up.
* **The anchor is live, instant on, instant off.** The solve is the shipped one again (the knob mixed in by
  the hold amount). The hold is `1` on the grab frame, re-asserted every frame the grip holds the knob,
  the target is refreshed by the door tick (no stale point), and it is **dropped to 0 on the release
  frame** (`s_doorLetGoKnob`) instead of decaying for half a second. The arm's blend ramp is taken to 1 for
  a knob-holding hand via `OLInteract_HandAnchorKnob()`.
* **The knob is held while the grip is closed**, so the hand rides it as the door swings. A grab still
  ends on: the grip opening, the door being taken by the game, the body turning past `kLetGoTurnDeg`, or
  the knob leaving the arm's reach (`kLetGoReachUU`).

Covered by `tests/phase12b_test.py` (sections 2 and 3), `tests/fixes_test.py` (section 4),
`tests/camera_and_sound_test.py`, `tests/legacy_fixes_test.py` and `tests/round3_test.py` (sections 3 and
5), each updated to assert the new contract rather than loosened.

`[HITCH]` lists frames over 40 ms with the second they happened, next to whatever else the log says
happened then.

---

### Phase 12n — the release defaults, and the build tag

Three of the shipped defaults were still the round-3 tuning values, chosen when the point was to
prove the features rather than to hand someone the mod. For the release they are what a new player
should get on a fresh install:

| Key | Was | Now | Why |
|---|---|---|---|
| `[Motion] RaiseToEyeReachM` | `0.120` | `0.140` | 14 cm is the distance at which most people's controller actually sits when they bring the camcorder up; at 12 cm the picture only switched for players who pushed it further in than they naturally would |
| `[Render] RenderScale` | `0.80` | `1.00` | the full runtime-recommended size by default. 80% was a performance experiment; a first install should not silently start soft and let the player wonder why |
| `[Motion] RoomscaleWalk` | `1` | `0` | walking Miles around the room by stepping is not what a first-time player expects, and it moves the body under them. Off by default, one row in the launcher to turn on |
| `[Input] AimAssistConeDeg` | `6.0` | `6.0` (unchanged) | already the middle of the 4-8 range the key documents; left alone deliberately rather than changed for the sake of changing it |

All four exist in three places - `runtime/outlastvr.ini`, the launcher's `N_`/`T_` default, and the
code's own fallback - and all three were moved together, because a fresh install and a launcher
"reset" disagreeing is exactly the kind of bug that takes a session to notice. The code fallbacks
that had drifted were fixed with them: `g_eyeReach` was initialised to `0.15` while the ini said
`0.12`, and the `RoomscaleWalk` slot in `kOnDefault`/`g_on` was `1`.

**The build tag** moved from `OUTLAST1VR-BETA-1.2.0-20261102` to
`OUTLAST1VR-RELEASE-1.0.0-20261108`. `SysInfo.FriendlyBuild` now accepts `STABLE` as well as
`BETA`/`RELEASE` and renders the kind in lower case, so the launcher shows
`stable-1.0.0  (2026-11-08)` instead of `BETA 1.2.0  (2026-11-02)`. The `changelog` text after the
tag is deliberately kept: it is the only place a player can read what a given build contains.

Covered by `tests/round3_test.py` section 6, which asserts the ini value, the launcher default and
the presence of the roomscale row for each of the four - not just one of the three places.

