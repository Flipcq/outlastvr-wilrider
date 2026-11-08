"""Two locks against the "stuck in the locker" report, read from the real sources.

1. The Use click is NOT gated by OLUE3_GameplayActive(). Inside a locker Miles is in a special move
   (moveMode 8), and that gate was false there: the log shows B pressed inside a locker for 50 s with
   no `left mouse down` ever sent, so the player could not get out.
2. The hands-on door layer stands down while Miles is in any special move. A locker IS an OLDoor, so the
   proximity scan picked it up and the open-hand collision wrote its TargetOpenRatio: "the locker opened
   by itself" / "the locker door went invisible for a moment".
3. The use watchdog never cancels (spends) the press; a gap only retries the release.

Run: python3 tests/locker_test.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROXY = (ROOT / 'src/d3d9_proxy.cpp').read_text(encoding='utf-8', errors='replace')
INTER = (ROOT / 'src/ol_interact.cpp').read_text(encoding='utf-8', errors='replace')


def block(src, sig):
    i = src.index(sig)
    j = src.index('{', i)
    depth = 0
    while j < len(src):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
        j += 1
    raise AssertionError('unbalanced: ' + sig)


# ---------------------------------------------------------------- 1. Use is not gated by gameplay
sample = block(PROXY, 'extern "C" void OLProxy_MouseUseSample(')
assert 'OLUE3_GameplayActive()' not in sample, \
    'the Use click is gated by OLUE3_GameplayActive() again - inside a locker (a special move) that is ' \
    'false, so the click is never sent and the player is stuck'
assert 'canStart' in sample and 'VK_LBUTTON' in sample, \
    'a real mouse click must still win over the synthetic one'
print('1. the Use click no longer depends on "gameplay is running" (lockers are special moves)')

# ---------------------------------------------------------------- 2. the watchdog never spends a press
wd = block(PROXY, 'static void MouseUseWatchdog()')
assert '.Cancel(' not in wd, \
    'the use watchdog can Cancel again: that spends the press without clicking it (B "did nothing")'
assert '.Release(' in wd, 'the watchdog does not retry a pending release'
print('2. the use watchdog only retries the release; it cannot spend a press')

# ---------------------------------------------------------------- 3. doors stand down in a special move
doors = block(INTER, 'static void Doors(ULONGLONG now, float dt')
assert 'heroSpecialMove' in doors, \
    'the hands-on door layer runs while Miles is in a special move (locker / bed / squeeze)'
assert 'const bool heroSpecialMove = dlm != 0 && dlm != 7;' in doors, \
    'the special-move guard is not the locomotion-mode test (0 walk, 7 door)'
guard = doors[doors.index('if (heroSpecialMove) {'):]
guard = guard[:guard.index('if (heroDoorMove)')]
assert 'hs->live = false' in guard and 'continue;' in guard, \
    'a special move does not stop the door sims, so the geometry the player is inside keeps moving'
print('3. doors (incl. the locker you are standing in) are left to the game during a special move')

# ---------------------------------------------------------------- 4. B also reaches the game as its OWN Use
# In the mouse layout B is a synthetic left click, and a door's Use listens to that. A LOCKER does not:
# entering / leaving it is SpecialMove 38/39 run by the pad's own OLA_Use. The log shows the click being
# sent while the player sat in a locker for 50 s with no effect.
mapb = block(PROXY, 'static WORD MapPadButtons(const OLXrPad& p, bool inMenu = false)')
mouselayout = mapb[mapb.index('if (mouseLayout) {'):]
mouselayout = mouselayout[:mouselayout.index('} else {')]
assert 'HeroInScriptedMove()' in mouselayout and 'b |= 0x4000' in mouselayout, \
    'B is not sent as the game\'s own OLA_Use during a locker / scripted move: the click alone does not ' \
    'get the player out'
helper = block(PROXY, 'static bool HeroInScriptedMove()')
assert 's_lm > 0 && s_lm != 7' in helper, \
    'the scripted-move test must exclude walking (0) and doors (7) so a door never gets two Use presses'
assert 'OLUE3_HeroMoveState' in helper, 'the scripted-move test does not read the pawn locomotion mode'
print('4. inside a locker / scripted move B is also the pad\'s own Use (a door still gets one Use)')
print('\nall locker checks passed')
