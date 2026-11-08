"""The legacy fixes, each checked where it actually acts.

1. The face-pinned camcorder can be grabbed with a fresh squeeze, once (the shipped behaviour).
2. The reload sound starts with the animation (blend-in 0 so the t=0 notify fires at once).
3. The hand is anchored to the handle while a door is held, at the shipped anchor: the knob point on
   the grabbed face at the height the hand had when it grabbed, and the wrist turns with the swing.
4. The game's lower animation plays out before the controller arm takes the hand back.
5. A palm-down hand does not push its fingers through the panel: the shipped contact box measures the
   hand across the panel, and contact is what writes the collision anchor.
6. A push is the shipped position solve: the door follows the hand out of the panel.

Run: python3 tests/legacy_fixes_test.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTER = (ROOT / 'src/ol_interact.cpp').read_text(encoding='utf-8', errors='replace')
UE3 = (ROOT / 'src/ol_ue3.cpp').read_text(encoding='utf-8', errors='replace')
HDR = (ROOT / 'src/ol_interact.h').read_text(encoding='utf-8', errors='replace')


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


# ---------------------------------------------------------------- 1. the face grab
cam = block('static void CamRaise(ULONGLONG now, const OLXrPose& head, const OLXrFrameHands& fh)', INTER)
face = cam[cam.index('if (s_faceLock) {'):cam.index('if (s_facePending)')]
# the shipped grab needs a FRESH squeeze, so a held grip cannot re-fire it frame after frame
assert 's_gripEdge[1] &&' in face, 'the grab no longer accepts a fresh squeeze'
assert 'if (!s_faceLowering && s_gripEdge[1] && s_dEye < EyeLeave() && now > s_camCooldown) {' in face, \
    'the grab is not the shipped fresh-squeeze test'
assert 's_gripDown[1] || s_gripEdge[1]' not in face, \
    'the grab is back to a LEVEL grip check, which re-fires every frame while held (the constant buzz)'
assert 's_faceGrabbed' not in INTER and 's_faceGrabUntil' not in INTER and 's_faceLockedAt' not in INTER, \
    'the grab latch / arming window is back; the shipped grab needs neither'
assert 'kFaceGrabArmMs' not in INTER, 'the 400 ms blind window is back (it swallowed real squeezes)'
assert 's_hState = H_IN_HAND; s_camBlend = 1.0f;' in face, \
    'the grabbed camera is not put in the hand on the grab frame'
print('1. face grab: the shipped fresh-squeeze grab, no latch, no blind window')

# ---------------------------------------------------------------- 2. reload sound start
reload = block('extern "C" float OLUE3_BeginBatteryReload(int inactive)', UE3)
assert '*(float*)(p + s_blendInOff) = 0.0f;' in reload, \
    'the reload montage still blends in, which delays its t=0 notify (the sound start)'
assert '0.55f' not in reload, 'the old 0.55 s blend-in is still there'
assert 'BlendOutTime' in reload, 'the blend-out must stay (the arm still eases back)'
print('2. reload: montage starts at time 0, so the opening sound notify is not swallowed')

# ---------------------------------------------------------------- 3. the handle anchor
assert 'OLInteract_HandAnchorLock' in HDR and 'OLInteract_HandAnchorYaw' in HDR, \
    'the handle anchor is not published'
anchor = INTER[INTER.index('s_doorAnchor[h] = { ipx + px * s_grabSide[h] * off'):]
anchor = anchor[:anchor.index('// [DOOR] open-hand collision')]
assert 's_grabKnobCenter[h].z' in anchor, \
    'the anchor lost the shipped height: the wrist at grab time, on the knob'
assert 'nd.knob.z' not in anchor and 'g_handleOffF' not in anchor, \
    'the knob-height / live-trim anchor is back - it moved the hand off the handle'
assert 's_anchorYaw[h] = sign * (An - s_grabA0[h]);' in anchor, \
    'the wrist no longer turns with the door swing'
# no lever-axis / panel-face publishing: the shipped solver yaws the wrist and nothing more
assert 's_doorHandleDir' not in INTER and 's_doorHandleFace' not in INTER, \
    'the lever-axis / panel-face orientation is back'
assert 'OLInteract_HandAnchorOrientation' not in INTER and \
       'OLInteract_HandAnchorOrientation' not in UE3 and \
       'OLInteract_HandAnchorOrientation' not in HDR, \
    'the arm solver still rolls the wrist onto a handle orientation'
assert 'WorldDirToComp' not in UE3, 'the direction transform for that roll was left behind'
solve = block('static void PoseApplyVisible(void* space)', UE3) if \
    'static void PoseApplyVisible(void* space)' in UE3 else UE3
lock = UE3[UE3.index('const bool doorLock = OLInteract_HandAnchorLock(hand) != 0;'):]
lock = lock[:lock.index('s_doorLockPrev[hand] = doorLock;')]
assert 's_doorWrist[hand] = wristTarget;' in lock, 'the held handle no longer locks the wrist pose'
assert 'OLInteract_HandAnchorYaw(hand)' in lock, 'the wrist no longer turns with the door'
assert 'IQBlend(wristTarget' not in lock, 'a roll is still blended onto the wrist'
# the anchor height is the knob point, taken at grab time
assert 's_grabKnobCenter[h] = nd.knob;' in INTER, 'the knob center is not recorded at grab time'
print('3. handle: the shipped anchor (knob point at wrist height) and a wrist that yaws with the door')

# ---------------------------------------------------------------- 4. the lower animation plays
lower = INTER[INTER.index('if (s_faceLowering && s_camUp == 0) {'):]
lower = lower[:lower.index('if (s_camUp == 0 && s_faceLock)')]
assert 'kFaceLowerAnimMs' in lower, 'the lower animation is not given its own duration'
assert 'return;      // hold the arm with the game' in lower, \
    'the arm is handed back to IK the instant the state flips, so the animation is never seen'
assert 'static const ULONGLONG kFaceLowerAnimMs = 900;' in INTER, 'the animation dwell constant is missing'
print('4. lower animation: the arm stays with the game for its full dwell before IK resumes')

# ---------------------------------------------------------------- 5. palm-down fingers + collision
box = INTER[INTER.index('// [DOOR] open-hand collision box: check if the whole hand'):]
box = box[:box.index('contact[h] = true;', box.index('edgeRadius'))]
assert 'acrossNormal' in box, 'the collision box still ignores the hand lying across the panel'
assert 'kFingerLenUU * 0.5f) * acrossNormal' in box, \
    'a pronated hand still collapses to the half-width and the fingers pass through'
assert 'boxRadius > edgeRadius ? boxRadius : edgeRadius' in box, \
    'only one of the two radii is used'
# the contact radius is the tunable that fixed "it only registers once the hand is through"
assert 'static float g_contactUU = 14.0f;' in INTER, \
    'the contact radius is back to the shipped 7 uu (thinner than a palm, so it rings late)'
assert 'g_contactUU / r' in INTER and 'g_contactUU + 0.5f' in INTER, \
    'the contact radius is not what the push corridor uses'
# the collision response is the shipped anchor, written from `contact`
col = INTER[INTER.index('// [DOOR] open-hand collision: keep an open hand pushing the panel'):]
col = col[:col.index('if (!ng && !contact[0] && !contact[1]')]
assert 'if (!contact[h] || s_grab[h].d) continue;' in col, \
    'the collision is not gated on contact (the shipped shape)'
assert 's_doorAnchor[h] = {' in col and 's_doorAnchorOn[h] = true;' in col, \
    'the collision does not write the arm anchor, so an open hand goes through the door'
assert 'g_pushDepthUU' in col, 'the hand is not held off the panel by the wrist depth'
assert 's_pushPlane' not in INTER and 'OLInteract_HandPushOut' not in INTER, \
    'a separate push-out is back; it reacted a frame late (the hand was through before it fired)'
print('5. hand collision: pronated span + the shipped contact-gated anchor, tuned radius')

# ---------------------------------------------------------------- 6. the shipped push
push = INTER[INTER.index('bool anyPush = false;'):]
push = push[:push.index('if (anyPush) { s->pushed = true;')]
assert 'const float need = (aC[h] - A) / dt, maxDv = kPushAccel * dt;' in push, \
    'the push is not the shipped position solve (the door follows the hand out of the panel)'
assert 'if (dirA[h] * dv < 0.0f) Om += dv;' in push, 'the push does not drive the door away from the hand'
assert 'An = A + Om * dt;' in push, 'the solved angle is not applied'
# the reverted speed rule must be gone: it disturbed anyPush/contact and broke auto open/close
assert 'handDegPerSec' not in INTER, 'the speed-based push is back (it broke the auto open/close)'
assert 's_pushPerpPrev' not in INTER, 'the previous-depth state for the speed push was left behind'
assert 'kPushGain' not in INTER, 'the speed gain was left behind'
print('6. push: the shipped position solve, capped by the door\'s acceleration budget')

print('\nall legacy fix checks passed')
