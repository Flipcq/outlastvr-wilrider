# Open issues and next steps

This is the state of the project: what is still open, what has been closed since the
original maintainer stepped back (October 2026), and what players have asked for.

Each open item says what is known so far and where to look in the code. Player logs are
the best evidence for any bug: `%LOCALAPPDATA%\OutlastVR\OutlastVR_Log.txt`, overwritten
every launch (see *The log* in the [README](../README.md)).

**Where the history lives.** This file keeps only the *open* work and a one-line index of
what was closed. The detail behind each "Done" line is in
[PROJECT-BASELINE.md](PROJECT-BASELINE.md) (per-test change log, including the tester
quotes each change answered) and [PERFORMANCE.md](PERFORMANCE.md) (the measured
performance work and the field-fix phases 8-12).

## On `main`, not in a release yet

Nothing at the moment.

## Closed since takeover (index)

Each line is a one-line pointer; the detail is in the two files above.

| Area | Closed |
|---|---|
| Input reliability | A press could fall between two game polls (`[PADLATCH]`, `LatchPresses`) and sprint silenced Use |
| Valve Index | Could not walk (`StickCenter`), no menu (left trackpad force), a refused path killed the whole profile |
| Notebook shortcuts | Split three ways: left grip + Y documents, left grip + X notes, left trigger + Y both |
| Document menu | Confidential document on the left shoulder, held and read to open the documents list |
| Camcorder | Upright GAME pose, right-stick hold to raise/lower, waist-shaped grab zone, grip+B and grip+X removed |
| Camcorder (field) | Grab off the face, the R3 lower ending in the hand instead of the holster, the visible lowering, the handle magnet, the hand leaving the knob |
| Doors and lockers | The door physics no longer pushes the locker the player is inside; `B` inside a locker reaches the game |
| Climbing | The ledge walk is the game's own move on the stick (all climb modes), gated on both hands; the left hand keeps hold; the hang-grab is immediate |
| Performance | Phases 1-7 complete; see [PERFORMANCE.md](PERFORMANCE.md) for what shipped and what was measured and rejected |

## Bugs players reported

- **Spotlights bleed through walls in the sewers.** Not investigated yet. The mod does not change
  the game's shadow settings, so first compare with the mod off at the same spot. Two of the mod's
  render changes are suspects:
  - `[OCCLSKIP]` / `OcclForce` (`src/d3d9_proxy.cpp`, `outlastvr.ini`): every occlusion query
    answers "visible".
  - `[LENSFIT]` (`src/ol_ue3.cpp`): each eye has its own off-centre frustum. This already cut the
    night-vision lamp's light once (`[NVEYES]`), so the light's screen bounds may be computed for
    a centred view.
- **Depth feels "a little off"**, and the **World size slider "messes with the IPD"**. World size
  (`[WORLDSIZE]`, `src/ol_ue3.cpp`) scales the eye distance and head movement together. That is how
  world scale works, but it changes the eye distance you feel. The eyes otherwise use the
  runtime's IPD.

  Ideas:
  - a separate eye-distance fine-tune that only changes depth;
  - show the detected IPD in the menu;
  - ask players which headset they use, and whether the world looks too big or too small.
- **Slight double vision** for some players. No clear repro.
- **A "giraffe arm"** (stretched arm) in one scripted scene. No repro.
- **Doors can push Miles** when they close on him.
- **The "real camcorder" hold** (`CamcorderHold=5`, the aim pose turned 180 deg) is broken. It is
  out of the menus, the default is 4 (free hold), and dev command `camhold 5` still selects it.
- **The live flip screen** (`CamcorderLiveScreen`, a SceneCapture2D lens camera) is experimental
  and off. Showing the picture on the camcorder's own screen texture is not done.
- **Not verified on real ledges:** climbing pacing and auto ledge grab (`[CLIMB]`, `[PHYSCLIMB]`,
  `[AUTOLEDGE]`); only the scaffold ladder in the opening has been tested.

## Requested features

- **Running and jumping that players can find.** Sprint is a left stick click, or left grip while
  walking. Vault and jump is A while moving. Several players did not know this - the README's
  Controls section and the in-headset hints cover it, but discovery is still the complaint.
- **More headsets and controllers tested:** Pimax, Index, Vive, WMR and Pico. The bindings are all
  in `src/ol_xr.cpp`.

