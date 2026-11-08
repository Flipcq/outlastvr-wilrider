"""The six fixes of phase 8, each checked where it actually acts.

1. Logging can be turned off completely (no file, no writer, no formatting).
2. Interaction aim has a bounded cone (a correction, never a replacement).
3. A door swinging through Miles can no longer pull a hand with it.
4. The face-pinned camcorder can be grabbed again.
5. HYBRID behaves as PHYSICAL except for the walk stick's forward.
6. The camcorder HUD hides on the frame the menu opens.

Run: python3 tests/fixes_test.py
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
PROXY = (ROOT / 'src/d3d9_proxy.cpp').read_text(encoding='utf-8', errors='replace')
UE3 = (ROOT / 'src/ol_ue3.cpp').read_text(encoding='utf-8', errors='replace')
INTER = (ROOT / 'src/ol_interact.cpp').read_text(encoding='utf-8', errors='replace')
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


# ---------------------------------------------------------------- 1. logging off
assert re.search(r'^\[General\]$', INI, re.M), 'the [General] section is missing'
#  Log ships OFF by request: nothing is written to disk unless the player turns it on.
assert re.search(r'^Log=0$', INI, re.M), 'Log must ship off (no files written by default)'
assert 'L"General", L"Log", 0' in PROXY, 'the log switch is not read from [General], defaulting to off'
worker = block('static DWORD WINAPI Worker(LPVOID)', PROXY)
assert worker.index('g_logEnabled') < worker.index('OpenLog()'), \
    'the switch must be read BEFORE the file is opened'
openlog = block('static void OpenLog()', PROXY)
assert 'if (!g_logEnabled) return;' in openlog, 'OpenLog can still create a file with logging off'
logfn = block('static void Log(const char* fmt, ...)', PROXY)
assert 'if (!g_log) return;' in logfn and 'if (!g_logEnabled) return;' in logfn, \
    'Log() does not bail out when logging is off'
# The probe CSV is a logging artefact too.
assert 'if (!OLProxy_GetLogEnabled()) { g_probeRows = 30000; return; }' in UE3, \
    'the camera probe still writes CamProbe.csv with logging off'
assert '"General", "Log", "Write log files"' in PAGES, 'the launcher has no Log row'
print('1. logging: [General] Log, read before OpenLog, Log() bails, CSV gated, launcher row')

# ---------------------------------------------------------------- 2. interaction cone
aim = block('static float AimBend(float dir[3], const float to[3], float maxRad)', UE3)
assert 'acosf(d)' in aim, 'AimBend does not measure the angle it is correcting'
assert 'maxRad / ang' in aim, 'AimBend does not cap the correction'
assert 'dir[i] * ca + (perp[i] / pl) * sa' in aim, 'AimBend is not a slerp toward the target'
hook = block('static void __fastcall Hook_NativePlayerMove(void* ctrl, float dt)', UE3)
assert 'OLInteract_AimAssistTarget(headW, wrote, 260.0f,' in hook, \
    'the interaction aim is not offered a target'
assert 'AimBend(wrote, to, g_aimAssistMaxDeg * 0.0174532925f)' in hook, \
    'the correction is not applied to the aim the engine will see'
# Only an aim that is ALREADY close may be corrected, and only within the cone.
tgt = block('extern "C" int OLInteract_AimAssistTarget(const float headWorld[3], const float fwd[3],\n'
            '                                          float maxDistUU, float coneDeg, float out[3])', INTER)
assert 'cosf(coneDeg' in tgt, 'the cone is not converted to a cosine'
assert '< cosCone' in tgt, 'a knob outside the cone can still be chosen'
assert 'if (d > maxDistUU) continue;' in tgt, 'the assist has no distance limit'
assert 's_near[i].busy || s_near[i].cant' in tgt, 'a busy/impossible door can still be aimed at'
assert re.search(r'^AimAssistConeDeg=6', INI, re.M) and re.search(r'^AimAssistMaxDeg=4', INI, re.M), \
    'the two numbers must be in the ini'
assert 'L"Input", L"AimAssistConeDeg"' in UE3, 'the cone is not read from [Input]'
assert 'OLUE3_SetAimAssist((float)_wtof(ab), (float)_wtof(am));' in UE3, 'the cone is not applied'
print('2. aim: bounded slerp onto a knob already inside the cone, distance-limited, ini-backed')

# ---------------------------------------------------------------- 3. the door collision anchor
#  The open hand is handled by ONE response: while `contact` is true the collision writes
# the hand's arm anchor a palm's depth out from the panel. The phase-8 "separate push plane" was
# removed - it was written and never read (no collision at all), and the geometric follow-up reacted a
# frame late (the hand was through the door before it was recognised).
assert 's_pushPlane' not in INTER and 's_pushPlaneOn' not in INTER, \
    'the separate push plane is back: it either goes unread or reacts a frame late'
assert 'OLInteract_HandPushOut' not in INTER, 'the push-out accessor is back'
push = INTER[INTER.index('// [DOOR] open-hand collision: keep an open hand pushing the panel'):]
push = push[:push.index('if (!ng && !contact[0]')]
assert 'if (!contact[h] || s_grab[h].d) continue;' in push, \
    'the open-hand response is not the shipped contact-gated collision'
assert 's_doorAnchor[h] = {' in push, 'the collision writes no anchor, so the arm never follows it'
assert 's_anchorYaw[h] = 0.0f;' not in push, \
    'the push still resets the wrist yaw, which belongs to a held handle only'
#  the door anchor holds the hand on the knob for as long as the grip is CLOSED, so the
# player cannot drag the hand off the handle while still squeezing it. It is still written at grab time
# (s_doorAnchorMs / s_doorAnchorFixed) and still released when the grab ends.
assert 'kAnchorMaxUU' not in INTER, 'the knob-to-eyes reach cap is back'
assert 's_doorAnchorMs' in INTER and 's_doorAnchorFixed' in INTER, \
    'the grab-time anchor state is missing'
assert 's_doorAnchorFixed[h] = false' in INTER, 'the anchor is not reset on release'
assert 'if (s_gripDown[h] || (now - s_doorAnchorMs[h]) < 300)' in INTER, \
    'the anchor is not held for as long as the grip is closed (the hand can be pulled off the knob)'
assert 's_anchorW[h] = s_doorAnchor[h]; on = true;' in INTER, \
    'the held knob no longer aligns the hand during the grab'
print('3. doors: the anchor holds the hand on the knob while the grip is closed, released when it opens')

# ---------------------------------------------------------------- 4. face grab
face = INTER[INTER.index('if (s_faceLock) {'):]
face = face[:face.index('if (s_facePending)')]
# the shipped grab needs a FRESH squeeze, so a held grip cannot re-fire it frame after frame
assert 'if (!s_faceLowering && s_gripEdge[1] && s_dEye < EyeLeave() && now > s_camCooldown) {' in face, \
    'the face grab is not the shipped fresh-squeeze test'
assert 's_gripDown[1] || s_gripEdge[1]' not in face, \
    'the face grab reads the grip LEVEL, so it re-fires every frame while held'
assert 's_faceGrabbed' not in INTER, 'the grab latch is back (the shipped grab needs none)'
#  the grab is the old/ (V1) one: it takes the hand state directly, and the holster keeps the camera
# while the grip is closed.
assert 's_hState = H_IN_HAND; s_camBlend = 1.0f;' in face, 'the grabbed camera is not put in the hand'
# The holster must not immediately undo it on the same frame: it only releases on an OPEN grip, so the
# squeeze that grabbed the camera keeps it (old/ relies on exactly this).
hol = block('static void Holster(ULONGLONG now, const OLXrFrameHands& fh)', INTER)
assert '} else if ((!s_gripDown[1] || !rOk) && !BatReloading() && !GameReloading()) {' in hol, \
    'the holster releases the camera regardless of the grip (it snaps the grabbed camera back to the hip)'
# [FACECAM] HOLDING R3 TO LOWER A PINNED CAMCORDER DROPS THE HAND STATE WHEN THE LOWER STARTS.
# The tick returns for the whole lower dwell (~0.9 s) BEFORE the Holster runs, so a hold inherited from a
# physical face grab would still be "in the hand" when the animation ended and only then glide to the
# waist - the report "the camera goes to Miles's hand after the lower animation finishes".
gesture = block('static void CamHoldGesture(ULONGLONG now, const OLXrPad& p)', INTER)
lowerStart = gesture[gesture.index('if (!s_faceLowering) {'):]
lowerStart = lowerStart[:lowerStart.index('RequestCamToggle(now, 300)')]
assert 's_hState = H_HOLSTERED' in lowerStart and 's_camBlend = 0.0f' in lowerStart, \
    'the lower starts with the camcorder still held, so it stops in the hand before the waist'
# and the end of the lower does not re-introduce a hold
lower = INTER[INTER.index('if (s_faceLowering && s_camUp == 0) {'):]
lower = lower[:lower.index('if (s_camUp == 0 && s_faceLock)')]
assert 'H_IN_HAND' not in lower, 'the end of the R3 lower puts the camcorder in the hand'
print('4. face cam: a fresh squeeze at the eye takes it, and the holster does not undo it')

# ---------------------------------------------------------------- 5. hybrid == physical
assert 'static bool ClimbIsPhysicalLike(int mode) { return mode == CLIMB_PHYSICAL || mode == CLIMB_HYBRID; }' in INTER, \
    'the physical-like predicate is missing'
assert 'g_climbMode == CLIMB_HYBRID && (lm == 0 || lm == 1 || s_pc || s_pcFinish) && PcReady()' not in INTER, \
    'HYBRID still runs its own guided carry'
# Every remaining mode check must go through the shared predicate, not compare to PHYSICAL directly.
stragglers = re.findall(r'g_climbMode\s*==\s*CLIMB_PHYSICAL', INTER)
assert not stragglers, f'{len(stragglers)} direct CLIMB_PHYSICAL comparisons remain'
hyb = block('static int ClimbStickRuleHybrid(int mode, int lm, bool ladderHold, bool edgeCarry, float underTopUU,\n'
            '                                bool forwardHeld)', INTER)
assert 'if (mode == CLIMB_HYBRID && forwardHeld) return CLIMB_STICK_FREE;' in hyb, \
    'HYBRID no longer re-allows the forward stick - or it re-allows more than that'
assert 'return ClimbStickRule(mode, lm, ladderHold, edgeCarry, underTopUU);' in hyb, \
    'HYBRID does not fall back to the shared rule'
filter_call = INTER[INTER.index('extern "C" void OLInteract_FilterMoveStick'):]
filter_call = filter_call[:filter_call.index('if (!s_blockOn)')]
assert 'ClimbStickRuleHybrid((int)g_climbMode, s_lm, ladderHold, edgeCarry,' in filter_call, \
    'the walk stick does not use the HYBRID-aware rule'
assert '*y > 0.05f' in filter_call, 'the HYBRID exception is not driven by forward on the stick'
print('5. hybrid: shares every rule with PHYSICAL through one predicate; only forward differs')

# ---------------------------------------------------------------- 6. HUD hides now
hud = block('extern "C" int OLInteract_CamcorderHud(OLCamcorderHudState* state)', INTER)
assert 'g_hudHiddenNow' in hud and 'if (g_hudHiddenNow) return 0;' in hud, \
    'the HUD still waits for the game thread when the menu opens'
assert '< 250' in hud, 'the snapshot freshness window is still a full second'
assert 'OLInteract_RefreshCamHudMenu();' in XR, 'the worker never asks about the menu'
frame = XR[XR.index('XrCompositionLayerQuad camcorderQuad = {};'):]
frame = frame[:frame.index('CamcorderHudLayer(')]
assert 'OLInteract_RefreshCamHudMenu();' in frame, 'the menu check is not before the layer is built'
assert 'InterlockedExchange(&g_hudHiddenNow, 0)' in INTER, 'the hidden latch is never released'
assert 'if (!OLUE3_InGameMenu() && !OLMenu_Visible()) InterlockedExchange(&g_hudHiddenNow, 0);' in INTER, \
    'the latch release is tied to the HUD being wanted (it must not be: a lowered camcorder would strand it)'
print('6. HUD: hidden on the worker frame the menu is seen, latch released by the game tick')

print('\nall phase-8 fix checks passed')

