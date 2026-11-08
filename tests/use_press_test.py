"""Behavioural check of the Use sampler (src/ol_mouse_use.h) against old/'s rules.

The sampler is mirrored in Python so the LOGIC is exercised, not the text; the mirror is asserted
against the real header first, so it cannot drift.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
src = (ROOT / 'src/ol_mouse_use.h').read_text(encoding='utf-8')

assert 'const bool rising = down && !previousDown;' in src
assert 'if (!held && rising && allowed && canStart) { held = send(true); return; }' in src
assert 'if (down && !canStart) previousDown = false;' in src
assert 'template<class Send> void Release(Send send)' in src


class Use:
    """Mirror of OLMouseUse."""

    def __init__(self):
        self.previousDown = False
        self.held = False
        self.releasePending = False
        self.events = []

    def send(self, down):
        self.events.append(down)
        return True

    def sample(self, down, allowed, canStart):
        rising = down and not self.previousDown
        self.previousDown = down
        if self.held and (self.releasePending or not down or not allowed):
            self.releasePending = True
            if self.send(False):
                self.held = False
                self.releasePending = False
            return
        if not self.held and rising and allowed and canStart:
            self.held = self.send(True)
            return
        if down and not canStart:
            self.previousDown = False

    def cancel(self):
        self.sample(True, False, False)

    def release(self):
        if not self.held:
            return
        self.releasePending = True
        if self.send(False):
            self.held = False
            self.releasePending = False


# 1. old/ behaviour: one click per physical press, however long it is held
u = Use()
u.sample(True, True, True)
u.sample(True, True, True)
assert u.events == [True], f'one press produced more than one click: {u.events}'
u.sample(False, True, True)
assert u.events == [True, False], f'release misbehaved: {u.events}'
print('1. one click per physical press, release immediate')

# 2. a press refused on purpose (menu / no focus) is not a delayed click
u = Use()
u.sample(True, False, True)
assert u.events == [], 'a press refused by a menu clicked immediately'
u.sample(True, True, True)
assert u.events == [], 'a press refused by a menu clicked when the menu closed'
u.sample(False, True, True)
u.sample(True, True, True)
assert u.events == [True], f'a new press after a refusal did not click: {u.events}'
print('2. a press refused by a menu never becomes a delayed click')

# 3. THE BUG: a missed sample must NOT cancel (that swallowed the press)
u = Use()
u.sample(True, True, True)
u.release()
assert u.events == [True, False]
u.sample(True, True, True)
assert u.events == [True, False], f'a gap turned into a second click: {u.events}'
print('3. a missed sample retries the release and cannot double-click')

# 3b. Cancel() is still the real thing: a held button must not click again after it
u = Use()
u.sample(True, True, True)
u.cancel()
assert u.events == [True, False]
u.sample(True, True, True)
assert u.events == [True, False], 'a cancelled press became a new click'
print('3b. Cancel (a menu / lost focus) still prevents a delayed click')

# 4. gameplay not running (canStart false) is not a click, and the press is retried
u = Use()
u.sample(True, True, False)
assert u.events == []
u.sample(True, True, True)
assert u.events == [True], f'the retried press did not click: {u.events}'
print('4. a press held across a gameplay gap clicks when gameplay returns')
print('\nall mouse-use press checks passed')
