"""Phase 12b: the hand on the handle, the arm the door must not pull, the face grab, and the defaults.

1. The wrist anchor is never closer to the panel than an open hand is (a flush knob used to put the
   palm inside the door).
2. The solver eases the door's pull off past the arm's reach: the handle gain legitimately moves the
   knob faster than the hand, but it may not drag the arm out of its reach.
3. A camera physically grabbed off the face is the CONTROLLER's: the right arm follows the hand and
   the model is drawn there, even while the game's CamcorderState lags at 1.
4. The startup camcorder guard does not make the arms wait when the camera was never raised.
5. The defaults the player asked for, in the ini and the launcher.

Run: python3 tests/phase12b_test.py
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
INTER = (ROOT / 'src/ol_interact.cpp').read_text(encoding='utf-8', errors='replace')
UE3 = (ROOT / 'src/ol_ue3.cpp').read_text(encoding='utf-8', errors='replace')
HDR = (ROOT / 'src/ol_interact.h').read_text(encoding='utf-8', errors='replace')
MOTION = (ROOT / 'src/ol_motion.cpp').read_text(encoding='utf-8', errors='replace')
PROXY = (ROOT / 'src/d3d9_proxy.cpp').read_text(encoding='utf-8', errors='replace')
INI = (ROOT / 'runtime/outlastvr.ini').read_text(encoding='utf-8')
PAGES = (ROOT / 'launcher/Outlast1VR_Pages.cs').read_text(encoding='utf-8', errors='replace')

# ---------------------------------------------------------------- 1. wrist not inside the panel
anchor = INTER[INTER.index('float off = fabsf(dNative);'):]
anchor = anchor[:anchor.index('s_doorAnchorOn[h] = true;')]
assert 'if (off < g_pushDepthUU) off = g_pushDepthUU;' in anchor, \
    'a nearly flush knob still anchors the wrist inside the panel (the palm sinks into the door)'
# and the same depth an open hand uses, so the two cannot drift apart
assert 'g_pushDepthUU' in INTER[INTER.index('OLInteract_GetHandPlacement'):], \
    'the wrist depth is not the tunable the collision uses'
print('1. handle: the wrist sits at least a hand-depth off the panel, never inside it')

# ---------------------------------------------------------------- 2. the hand stays on the handle it holds
#  The anchor is followed for as long as the grip is CLOSED on the knob. The old 300 ms
# align-then-release window is what let a squeezing player pull the hand off the handle and leave the
# door behind; a hand closed round a handle rides it instead. The solver still enforces the arm's real
# reach, and a genuine let-go (grip open, the game taking the door, the body turning away, the knob out
# of reach) still ends the grab.
assert 'OLInteract_HandAnchorHand' not in INTER and 'OLInteract_HandAnchorHand' not in HDR and \
       'OLInteract_HandAnchorHand' not in UE3, \
    'the pull-limit plumbing is back (the anchor must be followed unconditionally again)'
assert 's_doorHandW' not in INTER, 'the grabbed hand point is still published'
assert 'kDoorPullFullUU' not in UE3 and 'kDoorPullMaxUU' not in UE3, \
    'the eased pull weight is back'
solve = UE3[UE3.index('const float w = OLInteract_HandAnchorWorld(hand, aw);'):]
solve = solve[:solve.index('{   // [ARMRESET]')]
# [DOOR] the solver keeps the shipped formula: the knob is mixed in by the eased hold amount. The magnet
# felt broken because of that hold amount in ol_interact (it was released 300 ms after the grab and then
# decayed) and a target that could go stale - not because of this line.
assert 'IVScale(IVSub(ac, rawTarget), w > 1.0f ? 1.0f : w)' in solve, \
    'the anchor is not followed by the eased weight (the wrist lags behind the handle)'
assert 'weight' not in solve, 'the eased pull weight is back'
assert 'kAnchorMaxUU' not in INTER, 'the knob-to-eyes reach cap is back'
assert 's_doorAnchorMs' in INTER and 's_doorAnchorFixed' in INTER, \
    'the grab-time anchor state is missing'
assert 's_doorAnchorFixed[h] = false' in INTER, 'the anchor is not reset on release'
assert 's_doorAnchorMs[h] = now' in INTER, 'the anchor start time is not recorded'
anchorHold = INTER[INTER.index('else if (s_doorAnchorOn[h]) {'):]
anchorHold = anchorHold[:anchorHold.index('const bool heldKnob')]
assert 'if (s_gripDown[h] || (now - s_doorAnchorMs[h]) < 300)' in anchorHold, \
    'the handle anchor is still released 300 ms after the grab (the hand can be pulled off the knob)'
assert 'anchorFresh' not in INTER, 'the 300 ms align-then-release window is back'
assert 'released the door anchor' not in INTER, 'the anchor is dropped while the grip is still closed'
# a closed grip never drops the handle by pulling the hand away from it
assert 'kReleaseTravel' not in INTER, 'pulling the hand away still releases the knob (>kReleaseTravel)'
assert 'tooFar' not in INTER, 'the "pulled away from the handle" let-go is back'
# [DOOR] the magnet is instant ON and instant OFF: weight 1 while the grip holds the knob, and a release
# drops the anchor at once instead of the hand staying stuck to the handle for ~0.5 s.
assert 'if (heldKnob) {' in INTER and 's_anchorWt[h] = 1.0f;' in INTER, \
    'the anchor weight is not applied in full on the grab frame'
assert 's_doorLetGoKnob' in INTER and 's_anchorWt[h] = 0.0f; s_doorLetGoKnob[h] = false;' in INTER, \
    'letting go of the handle still decays the anchor (the hand stays on the knob)'
assert 's_doorLetGoKnob[h] = true;' in INTER, \
    'a release does not tell the anchor to drop at once'
print('2. doors: the hand rides the knob for as long as the grip is closed; the magnet is instant')

# ---------------------------------------------------------------- 3. the grabbed camera is the hand's
face = INTER[INTER.index('if (s_faceLock) {'):INTER.index('if (s_facePending)')]
grab = face[face.index('if (!s_faceLowering && s_gripEdge[1]'):]
#  the grab is the old/ (V1) one: a fresh squeeze at the eye takes it straight into the hand, with no
# toggle, no lower state and no latch.
assert 's_hState = H_IN_HAND' in grab and 's_camBlend = 1.0f' in grab, \
    'the camera is not put in the hand on the grab frame'
#  RESTORED: NO toggle on the grab - the camera stays visibly in the hand at the face.
assert 'RequestCamToggle' not in grab, \
    'the grab asks the game to lower its state, so the model vanishes instead of staying in the hand'
native = INTER[INTER.index('extern "C" int OLInteract_RightArmNative()'):]
native = native[:native.index('\n}')]
assert 'if (s_hState == H_IN_HAND) return 0;' in native, \
    'the right arm stays the game\'s while the camera is in the hand (the grab has no visible effect)'
auto = INTER[INTER.index('if (s_camStarted && s_camUp == 1'):]
auto = auto[:auto.index('}\n', auto.index('s_faceLock = true;'))]
assert 's_hState != H_IN_HAND' in auto, \
    'the auto-pin re-adopts a camera the player is holding (the grab is undone next frame)'
visual = INTER[INTER.index('extern "C" int OLInteract_CamVisual'):]
visual = visual[:visual.index('v->torsoFwd[0] = s_torsoF.x; v->torsoFwd[1] = s_torsoF.z;\n    return 1;\n}')]
#  camera up at the face and not held: model hidden, only screen shows.
assert 'if (s_camUp == 1) { v->mode = 2; return 1; }' in visual, \
    'the model is not hidden at the face when not holding it'
#  old/ (V1) model placement: at the eye it is hidden and only the screen shows, and everywhere else it is
# drawn by the blend - which is 1 while it is held, so it sits in the hand, and 0 once it has been let go.
assert 'if (s_camUp == 1) { v->mode = 2; return 1; }' in visual, \
    'the model is not hidden at the eye'
assert 'const float b = s_camBlend;' in visual and 'v->blend = b * b * (3.0f - 2.0f * b);' in visual, \
    'the held camera is not placed by the blend (it cannot sit in the hand)'
# and the hand is dropped in BOTH cases the camera can be at the face: the game's own state up and
# inside the eye zone, or a hand grab that has not yet carried it out of the zone (the game's state
# lags for frames after a grab, and in those frames the empty open hand was drawn beside the lens).
handAtFace = INTER[INTER.index('extern "C" int OLInteract_CamInHandAtFace()'):]
handAtFace = handAtFace[:handAtFace.index('\n}')]
assert 's_dEye < EyeLeave()' in handAtFace, \
    'the controller hand is dropped for as long as the game state lags, so his native arm pose stands'
assert 's_camGrabbedAtFace ? 1 : 0' in handAtFace, \
    'a camera physically grabbed at the face does not hide the hand (the empty open hand shows beside the lens)'
assert 'if (s_hState != H_IN_HAND) return 0;' in handAtFace, \
    'the hand is hidden even when the camera is not in the hand'
# ol_ue3 must actually consume the signal, or it is dead code
UE3F = (ROOT / 'src/ol_ue3.cpp').read_text(encoding='utf-8')
assert 'extern "C" int OLInteract_CamInHandAtFace();' in UE3F, \
    'ol_ue3 never declares the hand-at-face signal'
assert 'const bool handCamAtFace = OLInteract_CamInHandAtFace() != 0;' in UE3F, \
    'ol_ue3 never reads the hand-at-face signal'
assert 'if (facePin || faceBusy || handCamAtFace)' in UE3F, \
    'the right arm is not handed to the game while the camera is held at the face'
# and the latch must be released once it is carried away, or the hand would stay hidden for good
assert 'if (s_camGrabbedAtFace && s_dEye > EyeLeave()) s_camGrabbedAtFace = false;' in INTER, \
    'the grab-at-face latch never ends, so the hand stays hidden after the camera is carried away'
# the visual must treat it as hidden at the eye (mode 2), not as in the hand
assert 'if (s_hState == H_IN_HAND && s_camGrabbedAtFace) {' in visual, \
    'a camera held at the face is still drawn in the hand while the hand is hidden'
print('3. face grab: camera hidden at the face (screen only); the hand is hidden with it')

# ---------------------------------------------------------------- 4. the arms at level start
guard = INTER[INTER.index('if (!s_camStarted) {'):]
guard = guard[:guard.index('if (s_camByGesture || s_rsDown')]
assert 's_camSawUp = true;' in guard, 'the guard does not remember that the camera really was raised'
assert 'const ULONGLONG settle = s_camSawUp ? kCamGuardSettleMs : kCamGuardStartMs;' in guard, \
    'the long settle is used even when the camera was never raised (the arms appear late)'
assert 'static const ULONGLONG kCamGuardStartMs = 200;' in INTER, 'the fast startup settle is missing'
print('4. startup: the arms are released at once unless the game actually raised the camera')

# ---------------------------------------------------------------- 5. the requested defaults
WANT_INI = [('WorldSize', '1.00'), ('SnapTurnBlink', '0'), ('WalkDirection', '0'),
            ('FreezeCameraRotation', '0'), ('ClimbMode', '0'), ('Log', '0'),
            ('BodyAlignSeconds', '2.000')]
for key, want in WANT_INI:
    assert re.search(r'^%s=%s$' % (key, re.escape(want)), INI, re.M), f'{key} must ship as {want}'
assert 'N_("COMFORT", "Render", "WorldSize", "World size", 1.00,' in PAGES, 'launcher world size is not 100%'
assert 'T_("COMFORT", "Input", "SnapTurnBlink", "Blink while snapping", 0,' in PAGES, \
    'launcher blink-while-snapping default is not off'
assert 'C_("MOVEMENT", "Input", "WalkDirection", "Walk direction", 0,' in PAGES, \
    'launcher walk-direction default is not BODY'
assert 'T_("MOVEMENT", "Motion", "FreezeCameraRotation", "Freeze camera rotation", 0,' in PAGES, \
    'launcher freeze-camera default is not off'
assert 'C_("HANDS", "Motion", "ClimbMode", "Climbing", 0,' in PAGES, \
    'launcher climbing default is not A BUTTON'
assert 'T_("TOOLS", "General", "Log", "Write log files", 0,' in PAGES, \
    'launcher write-log default is not off'
assert 'N_("MOVEMENT", "Motion", "BodyAlignSeconds", "Body alignment speed", 2.0,' in PAGES, \
    'launcher body-alignment default is not 2.0 s'
# the code fallbacks must agree, or a missing key reads differently from a reset
assert 'L"SnapTurnBlink", 0, ini' in MOTION, 'the SnapTurnBlink fallback is not off'
assert 'L"BodyAlignSeconds", L"2"' in UE3, 'the BodyAlignSeconds fallback is not 2 s'
assert 'L"General", L"Log", 0' in PROXY, 'the Log fallback is not off'
print('5. defaults: 100% world, blink off, BODY walk, freeze off, A-button climb, no log, 2.0 s')

print('\nall phase-12b checks passed')

