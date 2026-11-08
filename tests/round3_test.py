"""The third round: snap blink, hand collision, the handle grab, Use gating, and the new defaults.

1. A snap turn blinks for the turn (the game's own black dip). This is the shipped behaviour and it
   was deliberately restored: a single blink per turn showed the turn instead.
2. The open-hand collision is the shipped ANCHOR response: while `contact` is true the hand's arm
   anchor is written a palm's depth out from the panel on the hand's side. The phase-10/11 geometric
   "push plane" variants were removed - the first had no effect at all, the second reacted a frame
   late (the hand was through before it was recognised).
3. No handle magnet / guide point: it moved the hand off real handles and was removed. The handle the
   hand takes is still landed instantly - the anchor is applied in full on the grab frame, in the door
   tick and in the arm blend ramp .
4. A plain sprint (left grip) does not swallow the door button.
5. A physical face grab is the shipped immediate one - no "snap the arm" request.
6. The shipped defaults are the ones the player chose.

Run: python3 tests/round3_test.py
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
INTER = (ROOT / 'src/ol_interact.cpp').read_text(encoding='utf-8', errors='replace')
UE3 = (ROOT / 'src/ol_ue3.cpp').read_text(encoding='utf-8', errors='replace')
HDR = (ROOT / 'src/ol_interact.h').read_text(encoding='utf-8', errors='replace')
MOTION = (ROOT / 'src/ol_motion.cpp').read_text(encoding='utf-8', errors='replace')
PROXY = (ROOT / 'src/d3d9_proxy.cpp').read_text(encoding='utf-8', errors='replace')
XR = (ROOT / 'src/ol_xr.cpp').read_text(encoding='utf-8', errors='replace')
INI = (ROOT / 'runtime/outlastvr.ini').read_text(encoding='utf-8')
PAGES = (ROOT / 'launcher/Outlast1VR_Pages.cs').read_text(encoding='utf-8', errors='replace')


def block(signature, src):
    start = src.index(signature)
    i = src.index('{', start)
    depth = 0
    while i < len(src):
        if src[i] == '{':
            depth += 1
        elif src[i] == '}':
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
        i += 1
    raise AssertionError('unbalanced: ' + signature)


# ---------------------------------------------------------------- 1. the snap turn's black dip
snap = block('static void SnapTurn(float* lx, ULONGLONG now)', MOTION)
assert 'if (g_snapBlink && now - s_snapStart < 350u) OLXR_Blink(70);' in snap, \
    'the snap turn no longer blinks for the turn (the game\'s own black dip)'
assert 's_blinkDone' not in MOTION, \
    'the one-blink-per-turn latch is back: it turned the black dip into a single flash and showed the turn'
print('1. snap blink: the game\'s own 70 ms dip, re-armed for as long as the turn lasts')

# ---------------------------------------------------------------- 2. the shipped anchor collision
col = INTER[INTER.index('// [DOOR] open-hand collision: keep an open hand pushing the panel'):]
col = col[:col.index('if (!ng && !contact[0] && !contact[1]')]
assert 'if (!contact[h] || s_grab[h].d) continue;' in col, \
    'the open-hand collision is not the shipped contact-gated anchor'
assert 's_doorAnchor[h] = {' in col and 's_doorAnchorOn[h] = true;' in col, \
    'the collision does not write the hand anchor, so the arm solver has nothing to follow'
assert 'g_pushDepthUU' in col, 'the anchor is not held off the panel by the tunable wrist depth'
# there must be exactly one response: the anchor. A separate push plane fought it and reacted late.
assert 's_pushPlane' not in INTER and 's_pushNormal' not in INTER, \
    'the phase-10/11 push plane is back: it is a second response that reacts a frame late'
assert 'OLInteract_HandPushOut' not in INTER and 'OLInteract_HandPushOut' not in UE3, \
    'the solver still applies a separate push-out instead of the anchor'
# the solver must follow the anchor on BOTH hands, with no per-hand exception
solve = UE3[UE3.index('const bool doorLock = OLInteract_HandAnchorLock(hand) != 0;'):]
solve = solve[:solve.index('s_doorLockPrev[hand] = doorLock;')]
assert 's_doorWrist[hand] = wristTarget;' in solve, 'the held handle no longer locks the wrist pose'
assert 'OLInteract_HandAnchorYaw(hand)' in solve, 'the wrist no longer turns with the door\'s swing'
assert 'hand == 1' not in solve, 'the door pose only reaches one hand'
# and the contact radius must be the tunable that fixed the late ring
assert 'static float g_contactUU = 14.0f;' in INTER, \
    'the contact radius is back to the shipped 7 uu, which is thinner than a palm'
print('2. hand collision: the shipped contact-gated anchor, tunable radius, no second response')

# ---------------------------------------------------------------- 3. no magnet / guide point
assert 'OLInteract_HandGrabGuide' not in INTER and 'OLInteract_HandGrabGuide' not in UE3, \
    'the handle magnet/guide is back - it pulls the hand off real handles'
assert 's_grabGuide' not in INTER, 'the guide state was left behind'
assert 'g_grabReachUU' not in INTER and 'bestD[h] < kGrabUU' in INTER, \
    'the grab reach is not the shipped fixed kGrabUU'
#  door magnet snaps instantly onto the handle - anchor weight set to 1 at grab.
assert 's_anchorWt[h] = 1.0f' in INTER, 'the door anchor weight is not snapped to 1 at grab'
#  ...and it STAYS at 1 for as long as the grip is closed on the knob: "the magnet works,
# but it delays too much, it should be almost instant". The weight is applied in full on the grab frame
# instead of being ramped in at 18/s, and re-asserted every frame so a missed door tick cannot decay it.
assert 'if (heldKnob) {' in INTER and 's_anchorWt[h] = 1.0f;' in INTER, \
    'the anchor weight is still ramped in (the hand eases onto the knob instead of snapping to it)'
assert 'const bool heldKnob = s_doorAnchorOn[h] && s_grab[h].d && s_gripDown[h];' in INTER, \
    'the instant anchor is not tied to a grip actually holding the knob'
# the magnet must FOLLOW the knob every frame, not go stale after the grab
assert 's_anchorW[h] = s_doorAnchor[h]; on = true;' in INTER, \
    'the magnet no longer pulls the hand to the knob the door tick published'
assert 'anchorFresh' not in INTER, 'the 300 ms align-then-release window is back (the magnet goes stale)'
assert 'released the door anchor' not in INTER, \
    'the anchor is dropped while the grip is still closed (the hand comes off the knob)'
# [DOOR] the solver keeps the shipped weight mix - what changed is the weight (instant on, instant off)
assert 's_doorLetGoKnob' in INTER, 'letting go of the handle does not drop the anchor at once'
# the arm solver snaps its own blend ramp for that hand, so the pose does not ease in either
assert 'OLInteract_HandAnchorKnob' in HDR and 'OLInteract_HandAnchorKnob(hand)' in UE3, \
    'the arm solver still eases the hand onto the handle (the grab feels delayed)'
assert 'if (knobHeld) g_poseRamp[hand] = 1.0f;' in UE3, \
    'the arm ramp is not taken straight to 1 for a hand holding a knob'
assert 'g_grabReachUU' not in INTER and 'bestD[h] < kGrabUU' in INTER, \
    'the grab reach is not the shipped fixed kGrabUU'
print('3. handle: no magnet or guide point; the grab uses the shipped fixed reach and lands instantly')

# ---------------------------------------------------------------- 4. sprint does not eat Use
grip = block('static bool LeftGripBlocksUse(float gripL)', PROXY)
assert 'return gripL > 0.6f;' not in grip, \
    'a plain sprint still swallows the Use button (the "door button sometimes does nothing")'
assert 'return false;' in grip and 'g_leftGripOwned' in grip, \
    'when nothing owns the grip the Use must be allowed'
print('4. Use: only a grip the mod is actually using blocks the door button, never a sprint')

# ---------------------------------------------------------------- 5. the grab is the shipped one
assert 'OLInteract_CamGrabSnap' not in INTER and 'OLInteract_CamGrabSnap' not in UE3, \
    'the arm still requests a one-frame snap on a physical grab'
assert 'g_camGrabSnap' not in INTER, 'the grab-snap latch was left behind'
face = INTER[INTER.index('if (s_faceLock) {'):INTER.index('if (s_facePending)')]
assert 'if (!s_faceLowering && s_gripEdge[1] && s_dEye < EyeLeave() && now > s_camCooldown) {' in face, \
    'the grab is not the shipped fresh-squeeze test'
assert 's_hState = H_IN_HAND; s_camBlend = 1.0f;' in face, \
    'the grabbed camera is not put in the hand on the grab frame'
assert 's_faceLowering = true' not in face, 'the grab still enters the lower-animation state'
print('5. camera grab: the shipped immediate grab, no snap request, no lower state')

# ---------------------------------------------------------------- 6. the chosen defaults
WANT = [('TurnMode', '0'), ('SmoothTurnDegPerSec', '180'), ('FreezeCameraRotation', '0'),
        ('RaiseToEyeReachM', '0.140'), ('RenderScale', '1.00'), ('Upscaler', '2'),
        ('RoomscaleWalk', '0'), ('EdgeOverscanDeg', '2.0')]
for key, want in WANT:
    assert re.search(r'^%s=%s$' % (key, re.escape(want)), INI, re.M), f'{key} must ship as {want}'
# the launcher defaults must agree, or a fresh install and a reset disagree
assert '"Smooth turn speed", 180,' in PAGES, 'launcher smooth turn default is not 180'
assert '"Camcorder to eye distance", 0.14,' in PAGES, 'launcher camcorder reach default is not 0.14'
assert '"Render resolution", 1.00,' in PAGES, 'launcher render scale default is not 100%'
assert '"Upscaler", "Upscaling", 2,' in PAGES, 'launcher upscaler default is not FSR1'
assert '"Walk around for real", 0,' in PAGES, 'launcher roomscale default is not off'
assert '"Edge margin", 2.0,' in PAGES, 'launcher edge margin default is not 2.0'
assert '"FreezeCameraRotation", "Freeze camera rotation", 0,' in PAGES, 'launcher freeze-camera default is not off'
# and the code must not collapse the upscaler's 3 values back to a bool
assert '? 1 : 0; }' not in XR[XR.index('L"XR", L"Upscaler"'):XR.index('L"XR", L"Upscaler"') + 200], \
    'the upscaler is read as a boolean, so FSR1 (2) can never take effect'
# the code's own fallbacks must agree with the ini, or a missing key changes the defaults silently
assert 'L"RaiseToEyeReachM", L"0.14"' in INTER, 'the camcorder-reach code fallback is not 0.14'
assert 'static float g_eyeReach = 0.14f;' in INTER, 'the g_eyeReach initialiser is not 0.14'
assert 'g_eyeReach = 0.14f;' in INTER, 'the g_eyeReach clamp fallback is not 0.14'
assert 'L"RenderScale", L"1.0"' in UE3, 'the render-scale code fallback is not 1.0'
assert '{ 1, 1, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 1 }' in INTER, \
    'the ON_ROOMWALK code default is not off'
print('6b. the code fallbacks agree with the ini (camcorder 14 cm, render 100%, roomscale off)')
print('6. defaults: SMOOTH 180, freeze off, 14 cm, 100%, FSR1, 2.0 deg, roomscale off - ini, launcher and code agree')

print('\nall round-3 checks passed')

