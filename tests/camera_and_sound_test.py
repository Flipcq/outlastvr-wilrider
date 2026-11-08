"""The camera grab and doors going silent: the shipped behaviour.

1. A physical grab never plays the lower animation first ("you see the camera start to lower, then he
   holds it").
2. R3 on a camera held physically at the face PINS it with the game's own state, and a physical grab
   takes a FRESH squeeze (so the gesture that pinned it cannot grab it straight back off).
3. Doors use the game's own Wwise objects. A save load retires those objects, so the mod FORGETS the
   ids it cached and the next game post repopulates them. Registering an object of our own was tried
   and reverted: such an object has no listener relation, so its events played nowhere (silent doors).

Run: python3 tests/camera_and_sound_test.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTER = (ROOT / 'src/ol_interact.cpp').read_text(encoding='utf-8', errors='replace')
UE3 = (ROOT / 'src/ol_ue3.cpp').read_text(encoding='utf-8', errors='replace')
SND = (ROOT / 'src/ol_sound.cpp').read_text(encoding='utf-8', errors='replace')


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


# ---------------------------------------------------------------- 1. grab: no lower animation first
cam = block('static void CamRaise(ULONGLONG now, const OLXrPose& head, const OLXrFrameHands& fh)', INTER)
face = cam[cam.index('if (s_faceLock) {'):cam.index('if (s_facePending)')]
grab = face[face.index('if (!s_faceLowering && s_gripEdge[1]'):]
grab = grab[:grab.index('s_inEyeSince = 0;\n        return;')]
assert 's_faceLowering = true' not in grab, \
    'the grab still enters the lower-animation state, so the model appears at the eye and the arm ' \
    'plays the lower before the hand takes it'
assert 's_hState = H_IN_HAND' in grab and 's_camBlend = 1.0f' in grab, \
    'the camera is not put in the hand on the grab frame'
print('1. grab: immediate (no lower animation first)')

# ---------------------------------------------------------------- 2. a fresh squeeze, once
gesture = block('static void CamHoldGesture(ULONGLONG now, const OLXrPad& p)', INTER)
assert 's_faceLock = true; s_facePending = false; s_faceLowering = false;' in gesture, \
    'the R3 pin does not put the game\'s own face pin in place'
# the grab must require a NEW squeeze: the gesture that pinned it was already holding the grip
assert 's_gripEdge[1] &&' in face, 'the grab does not require a fresh squeeze'
assert 's_gripDown[1] || s_gripEdge[1]' not in face, \
    'the grab reads the grip LEVEL, which re-fires every frame while the grip is held'
assert 's_faceGrabbed' not in INTER and 's_faceLockedAt' not in INTER and 'kFaceGrabArmMs' not in INTER, \
    'the latch / arming window is back; a fresh squeeze is all the shipped grab needs'
print('2. R3: pins with the game\'s state, and only a fresh squeeze can grab it off the face')

# ---------------------------------------------------------------- 3. doors use the game's objects
assert 'OLSound_OnWorldChanged' in SND and 'OLSound_OnWorldChanged' in UE3, \
    'a level load never tells the sound layer the world changed'
assert 'if (s_hasHero == 0 && hh > 0)' in UE3 and 'OLSound_OnWorldChanged();' in UE3, \
    'the hero-return (new level / save load) does not reset the sound objects'
forget = block('static void OLSound_ForgetObjects()', SND)
assert 's_milesObj = 0; s_lastObj = 0;' in forget, \
    'the stale Wwise objects are kept: a door event posted on one plays nowhere'
assert 's_playN = 0;' in forget, 'players from the old world are still tracked'
# the fallback is the game's own objects only
assert 'SoundOurObj' not in SND and 'g_regObj' not in SND and 's_ourObj' not in SND, \
    'the self-registered Wwise object is back; it has no listener relation and plays nowhere'
portal = block('static AkGameObjectID SoundPortalObj(AkGameObjectID obj)', SND)
assert 'if (!o) o = s_milesObj;' in portal and 'if (!o) o = s_lastObj;' in portal, \
    'the door sound no longer falls back to the game\'s own objects'
# order matters: the cached game objects come before the (possibly empty) play list
assert portal.index('s_lastObj') < portal.index('for (int k = s_playN - 1'), \
    'the fallback order still reaches the empty play list first'
print('3. doors: the game\'s own Wwise objects, forgotten on a world change and repopulated by the game')

print('\nall camera/sound checks passed')

