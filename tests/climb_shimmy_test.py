"""Ledge walk: the GAME's own move, driven by the walk stick, in every climb mode.

Walking sideways while hanging from a ledge is a built-in Outlast move (LocomotionMode 4/5, its own shimmy
animation). The mod used to keep the walk stick off on a ledge - "the hands move him" - which turned a
built-in move into a fight: the ledge could not be walked at all. The stick now goes through untouched.

1. Hanging from a ledge (lm 4/5) hands the walk stick to the GAME, in PHYSICAL and HYBRID alike (A button
   never changed it).
2. A hand-carried climb (edgeCarry) still keeps the stick off - that is the hands' business, not a ledge.
3. The ladder rules are untouched.
4. None of the hand/stick shimmy experiment remains.

Run: python3 tests/climb_shimmy_test.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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


rule = block(INTER, 'static int ClimbStickRule(int mode, int lm, bool ladderHold, bool edgeCarry, float underTopUU)')

# ---------------------------------------------------------------- 1. a ledge is the game's
assert 'lm == 4 || lm == 5' not in rule, \
    'hanging from a ledge still locks the walk stick: the game cannot play its own ledge walk'
assert 'edgeCarry || lm == 4' not in rule, 'the ledge is still mixed into the hand-carry lock'
assert '[LEDGEWALK]' in rule, 'the ledge-walk rule is not documented at the place it acts'
print('1. a hanging ledge hands the walk stick to the game (its own shimmy animation)')

# ---------------------------------------------------------------- 2. a hand-carried climb keeps it off
assert 'if (edgeCarry) return CLIMB_STICK_LOCKED;' in rule, \
    'a hand-carried climb no longer keeps the stick off (the hands must move him)'
print('2. a hand-carried climb still keeps the walk stick off')

# ---------------------------------------------------------------- 3. the ladder rules are untouched
assert 'if (lm == 3) return underTopUU <= kPhysLadderTopFreeUU ? CLIMB_STICK_FREE : CLIMB_STICK_DOWN_ONLY;' in rule, \
    'the ladder stick rules changed'
assert 'if (ladderHold) return CLIMB_STICK_FREE;' in rule, 'a hand on a rung from the floor no longer walks'
print('3. the ladder rules are unchanged')

# ---------------------------------------------------------------- 4. the experiment is gone
for gone in ('kShimmyReGrabUU', 'kShimmyHandReachUU', 'ShimmyHandAlong', 'ShimmyHandover',
             's_shimmyMoved', 'CLIMBSHIMMY'):
    assert gone not in INTER, f'the removed shimmy experiment is back: {gone}'
print('4. none of the hand/stick shimmy experiment remains')

# ---------------------------------------------------------------- 5. every mode goes through the same rule
hyb = block(INTER, 'static int ClimbStickRuleHybrid(')
assert 'ClimbStickRule(mode, lm, ladderHold, edgeCarry, underTopUU)' in hyb, \
    'HYBRID does not fall back to the shared rule'
print('5. PHYSICAL and HYBRID share the rule; the A button was never affected')

# ---------------------------------------------------------------- 6. the ledge walk needs BOTH hands
filt = block(INTER, 'extern "C" void OLInteract_FilterMoveStick(float* x, float* y)')
assert 's_lm == 4 || s_lm == 5' in filt, \
    'the ledge walk is not gated on hanging (the stick reaches the game with one hand off)'
assert '!(s_hold[0] && s_hold[1])' in filt, \
    'the ledge walk does not require BOTH hands holding'
gate = filt[filt.index('s_lm == 4 || s_lm == 5'):]
gate = gate[:gate.index('if (ClimbIsPhysicalLike(g_climbMode)) {')]
assert '*x = 0.0f; *y = 0.0f;' in gate and 'return;' in gate, \
    'with one hand off the stick is not stopped'
assert 'BOTH hands holding' in filt, 'the refusal is not logged'
print('6. the ledge walk only runs with both hands on the ledge')

# ---------------------------------------------------------------- 7. the left hand keeps the ledge
hang = block(INTER, 'static void PhysHang(')
assert 's_lOwned && !leftGrip && !s_hold[1]' in hang, \
    'opening the left grip without the right hand holding still drops him'
keep = hang[hang.index('s_lOwned && !leftGrip && !s_hold[1]'):]
assert 's_hold[0] = true;' in keep[:keep.index('}') + 1], \
    'Miles does not keep his left hand on the ledge'
assert 's_hold[0] = s_lOwned ? leftGrip : true;' in hang, \
    'with the right hand holding, the owned left hand must still be releasable'
print('7. the left hand keeps the ledge when the right is not holding (and is still releasable otherwise)')
print('\nall climbing checks passed')
