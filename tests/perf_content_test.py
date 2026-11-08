"""Phase 6 of the optimization pass: CONTENT - D.5 DetailMode, D.4 particles, B7 the launcher profile.

Three things are proved here:

1. The command lists. The real parser and the real apply/restore logic from ol_ue3.cpp are compiled
   against a stub console, then driven: a ';'-separated profile becomes one command per entry, an
   empty token is ignored, a long list is truncated instead of overflowing, and turning the profile
   off replays the RESTORE list (not the performance list) so the engine gets its own values back.

2. The wiring. The profile is read from [Content] in the shipped ini, ships OFF, is re-applied after
   a level load, and never runs while the game is loading.

3. The launcher row. "Performance profile" exists, offers exactly FULL DETAIL / PERFORMANCE /
   PERFORMANCE+, and writes the engine's 0/1/2 numbering into [Content] Profile.

Run: python3 tests/perf_content_test.py
"""
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
UE3 = (ROOT / 'src/ol_ue3.cpp').read_text(encoding='utf-8')
INI = (ROOT / 'runtime/outlastvr.ini').read_text(encoding='utf-8')
PAGES = (ROOT / 'launcher/Outlast1VR_Pages.cs').read_text(encoding='utf-8')


def block(signature, src=None):
    text = src if src is not None else UE3
    start = text.index(signature)
    i = text.index('{', start)
    depth = 0
    while i < len(text):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1
    raise AssertionError('unbalanced function: ' + signature)


# ---------------------------------------------------------------- 1. the shipped ini
assert '[Content]' in INI, 'the phase-6 section header is missing from the shipped ini'
section = INI[INI.index('[Content]'):]
assert re.search(r'^Profile=0$', section, re.M), 'the content profile must ship OFF'
m1 = re.search(r'^Commands1=(.+)$', section, re.M)
m2 = re.search(r'^Commands2=(.+)$', section, re.M)
m3 = re.search(r'^Restore=(.+)$', section, re.M)
assert m1 and m2 and m3, 'Commands1 / Commands2 / Restore are missing from the ini'
cmds1 = [c.strip() for c in m1.group(1).split(';') if c.strip()]
cmds2 = [c.strip() for c in m2.group(1).split(';') if c.strip()]
restore = [c.strip() for c in m3.group(1).split(';') if c.strip()]
# D.5 is the lever that actually cuts processed primitives: it must be in BOTH lists.
for name, lst in (('Commands1', cmds1), ('Commands2', cmds2)):
    assert any('DetailMode' in c for c in lst), f'{name} lost D.5 (DetailMode)'
    assert any('ParticleLODBias' in c for c in lst), f'{name} lost D.4 (ParticleLODBias)'
    for c in lst:
        assert c.startswith('scale set '), f'{name}: "{c}" is not a `scale set` console line'
# PERFORMANCE+ is a superset of PERFORMANCE by SYSTEM: it may tighten a value (0.6 -> 0.5) but must
# not quietly drop a lever.
system_of = lambda c: c.split()[2]
missing = [s for s in {system_of(c) for c in cmds1} if s not in {system_of(c) for c in cmds2}]
assert not missing, f'Commands2 is missing systems from Commands1: {missing}'
assert any('DynamicShadows' in c for c in cmds2), 'performance+ lost DynamicShadows'
assert any('Decals' in c for c in cmds2), 'performance+ lost Decals'
# The restore list has to name every system the two profiles touch, with a different value.
for lst in (cmds1, cmds2):
    for c in lst:
        parts = c.split()
        system = parts[2]
        assert any(x.split()[2] == system for x in restore), f'Restore does not cover {system}'
assert not any(c in restore for c in cmds1 + cmds2), 'Restore repeats a performance command'
print(f'ini: profile OFF, {len(cmds1)} + {len(cmds2)} commands, {len(restore)} restore lines, '
      'DetailMode+ParticleLODBias in both')

# ---------------------------------------------------------------- 2. the real parser and apply logic
stub = r'''
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <cassert>
#include <cwchar>
using LONG = long;
using ULONGLONG = unsigned long long;
#define InterlockedExchange(p, v) (*(p) = (v))
#define InterlockedIncrement(p)   (++*(p))
static void OLProxyLog(const char*) {}

// The console the profile runs through. Records every line so the test can compare the lists.
static char g_sent[64][128];
static int  g_nsent = 0;
static void Con_RunText(const char* cmd, int) {
    if (g_nsent < 64) { strncpy_s(g_sent[g_nsent], cmd, _TRUNCATE); ++g_nsent; }
}
static volatile LONG g_active = 1;
static int OLUE3_GameplayActive() { return g_active; }
static unsigned long long GetTickCount64() { return 0; }
#define __try
#define __except(x) if (0)
'''

CONTENT = UE3[UE3.index('// ---- [CONTENT] '):
             UE3.index('static void LS_Tick() {')]

checks = r'''
int main() {
    setvbuf(stdout, nullptr, _IONBF, 0);

    // ---- the parser -----------------------------------------------------------------------
    // A whole profile in one ini line becomes one command per entry, trimmed.
    int n = ContentParseList(L"scale set DetailMode 1;  scale set ParticleLODBias 2 ; scale set Decals False", 0);
    assert(n == 3);
    assert(strcmp(g_contentCmd[0][0], "scale set DetailMode 1") == 0);
    assert(strcmp(g_contentCmd[0][2], "scale set Decals False") == 0);

    // Empty tokens (a trailing ';', a doubled one) are not commands.
    assert(ContentParseList(L"a; ;b;;", 1) == 2);
    assert(strcmp(g_contentCmd[1][1], "b") == 0);

    // A list longer than the table is TRUNCATED, never written past it.
    char big[4096]; big[0] = 0;
    for (int i = 0; i < 40; ++i) strcat_s(big, "c;");
    wchar_t wbig[4096]; size_t wn = 0; mbstowcs_s(&wn, wbig, big, _TRUNCATE);
    assert(ContentParseList(wbig, 0) == kContentMaxCmds);
    assert(ContentParseList(wbig, 3) == 0);      // an out-of-range list is a no-op
    assert(ContentParseList(nullptr, 0) == 0);
    assert(ContentParseList(L"", 0) == 0);

    // ---- apply, then turn off: the RESTORE list, never the performance list ----------------
    assert(ContentParseList(L"scale set DetailMode 1; scale set Decals False", 0) == 2);
    assert(ContentParseList(L"scale set DetailMode 1; scale set DynamicShadows False", 1) == 2);
    assert(ContentParseList(L"scale set DetailMode 0; scale set Decals True; scale set DynamicShadows True", 2) == 3);

    g_contentProfile = 0; g_contentApplied = -1; g_nsent = 0;
    ContentApply();
    assert(g_nsent == 2 && strstr(g_sent[0], "DetailMode"));
    assert(g_contentApplied == 0);

    g_nsent = 0;
    g_contentProfile = -1;                       // profile OFF
    ContentApply();
    assert(g_nsent == 3);                        // exactly the restore list
    assert(strstr(g_sent[0], "DetailMode 0"));
    assert(strstr(g_sent[1], "Decals True"));
    assert(strstr(g_sent[2], "DynamicShadows True"));
    assert(g_contentApplied == -1);

    // Off with nothing applied is silent: no console traffic at all.
    g_nsent = 0;
    ContentApply();
    assert(g_nsent == 0);

    // Switching between the two profiles applies the new list - and restores first, because list 1
    // does not mention every system list 2 turns off (shadows, decals), so without the restore those
    // would stay off for ever after stepping down from PERFORMANCE+.
    g_contentProfile = 0; g_nsent = 0;            // start from PERFORMANCE
    ContentApply();
    assert(g_contentApplied == 0);                // (no restore: nothing was in force)
    g_contentProfile = 1; g_nsent = 0;           // step up to PERFORMANCE+
    ContentApply();
    assert(g_nsent == 3 + 2);                    // restore (3) then list 2 (2)
    assert(strstr(g_sent[0], "DetailMode 0"));   // the clean slate comes first
    assert(strstr(g_sent[4], "DynamicShadows")); // ... and the new list comes after it
    assert(g_contentApplied == 1);

    // Re-applying the SAME profile (a level load) does not restore first: it is idempotent.
    g_nsent = 0;
    ContentApply();
    assert(g_nsent == 2 && g_contentApplied == 1);

    // ---- the tick: gameplay only, once per level, then again after a level load -----------
    g_contentProfile = 0; g_contentApplied = -1; g_contentWant = 0;
    g_contentLevel = 0; g_contentPendingLevel = -1; g_contentNextTry = 0;
    g_active = 0;
    ContentTick();                               // not in gameplay: nothing happens
    assert(g_contentApplied == -1);

    g_active = 1; g_contentNextTry = 0;
    ContentTick();
    assert(g_contentApplied == 0);               // applied once gameplay is live
    const ULONGLONG t1 = g_contentNextTry;
    assert(t1 > 0);                              // and it paces the next attempt

    // A level load re-applies, but only after the settle delay.
    OLUE3_ContentLevelLoaded();
    g_nsent = 0;
    ContentTick();                               // still inside the settle window
    assert(g_nsent == 0 && g_contentApplied == 0);
    g_contentNextTry = 0;
    ContentTick();
    assert(g_nsent == 2);                        // the list ran again

    std::puts("ok");
    return 0;
}
'''

# ---------------------------------------------------------------- 6. the ini is actually read
# The launcher writes [Content] Profile; the mod must read it. Without the loader call the row
# changes the ini and nothing happens - the exact bug this section exists to prevent.
UE3 = (ROOT / 'src/ol_ue3.cpp').read_text(encoding='utf-8')
assert 'GetPrivateProfileIntW(L"Content", L"Profile"' in UE3, \
    'the mod never reads [Content] Profile - the launcher row would do nothing'
for key, idx in (('Commands1', 0), ('Commands2', 1), ('Restore', 2)):
    assert f'GetPrivateProfileStringW(L"Content", L"{key}"' in UE3, \
        f'[Content] {key} is never read from the ini'
    assert f'ContentParseList(list, {idx});' in UE3, \
        f'[Content] {key} is read but never parsed into list {idx}'
assert 'InterlockedExchange(&g_contentProfile, want);' in UE3, \
    'the loaded profile is not published to the thread that applies it'
assert 'prof <= 0 ? -1 : (prof > 2 ? 1 : prof - 1)' in UE3, \
    'the ini profile numbering is not mapped onto the internal off/0/1'
print('6. [Content] Profile, Commands1, Commands2 and Restore are read from the ini and parsed')

with tempfile.TemporaryDirectory() as td:
    src = Path(td) / 't.cpp'
    exe = Path(td) / 't.exe'
    src.write_text(stub + '\n' + CONTENT + '\n' + checks)
    subprocess.run(['g++', '-std=c++17', '-O1', '-Wall', '-Wno-unused-function',
                    '-o', str(exe), str(src)], check=True)
    out = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout
    assert out.strip() == 'ok', out
print('CONTENT: the real parser and apply/restore, driven - restore never replays the profile')

# ---------------------------------------------------------------- 3. the wiring, in source
read = block('static int ContentParseList(const wchar_t* src, int which)')
assert "strtok_s(all, \";\", &ctx)" in read, 'the parser no longer splits the profile on ";"'
assert 'kContentMaxCmds' in read, 'the parser no longer bounds the table'
body = block('static void ContentApply()')
assert 'ContentRunList(2)' in body, 'turning the profile off no longer replays the Restore list'
assert 'ContentRunList((int)prof)' in body, 'the selected profile is no longer what runs'
tick = block('static void ContentTick()')
assert 'OLUE3_GameplayActive()' in tick, 'the profile can be applied while the game is loading'
assert 'g_contentLevel == g_contentPendingLevel' in tick, 'a level load no longer triggers a re-apply'
assert 'InterlockedExchange(&g_contentWant, 0)' in tick, 'the apply request is never consumed'
# The ini is read from [Content], and the profile number is the launcher's 0/1/2.
assert 'GetPrivateProfileStringW(L"Content", L"Commands1"' in UE3
assert 'GetPrivateProfileStringW(L"Content", L"Commands2"' in UE3
assert 'GetPrivateProfileStringW(L"Content", L"Restore"' in UE3
assert 'GetPrivateProfileIntW(L"Content", L"Profile", 0, ini)' in UE3
# Every line goes through the engine's own console - no offset is written by phase 6.
assert 'Con_RunText(g_contentCmd' in UE3
assert 'OLUE3_ContentLevelLoaded()' in UE3
print('CONTENT: [Content] ini-driven, gameplay-gated, re-applied on level load, console only')

# ---------------------------------------------------------------- 4. the launcher row (B7)
assert '"Content", "Profile", "Performance profile"' in PAGES, \
    'the launcher has no Performance profile row'
row_start = PAGES.index('"Performance profile"')
row_end = PAGES.index('A_("TOOLS", "Open the log folder"')
row = PAGES[row_start:row_end]
for label in ('FULL DETAIL', 'PERFORMANCE', 'PERFORMANCE+'):
    assert label in row, f'the launcher profile lost "{label}"'
assert 'new double[] { 0, 1, 2 }' in row, 'the launcher no longer writes the 0/1/2 numbering'
assert 'DetailMode' in row or 'detail props' in row.lower(), \
    'the launcher help does not say what disappears'
print('B7: launcher row FULL DETAIL / PERFORMANCE / PERFORMANCE+, writes [Content] Profile 0/1/2')

# ---------------------------------------------------------------- 6. the ini is actually read
# The launcher writes [Content] Profile; the mod must read it. Without the loader call the row
# changes the ini and nothing happens - the exact bug this section exists to prevent.
UE3 = (ROOT / 'src/ol_ue3.cpp').read_text(encoding='utf-8')
assert 'GetPrivateProfileIntW(L"Content", L"Profile"' in UE3, \
    'the mod never reads [Content] Profile - the launcher row would do nothing'
for key, idx in (('Commands1', 0), ('Commands2', 1), ('Restore', 2)):
    assert f'GetPrivateProfileStringW(L"Content", L"{key}"' in UE3, \
        f'[Content] {key} is never read from the ini'
    assert f'ContentParseList(list, {idx});' in UE3, \
        f'[Content] {key} is read but never parsed into list {idx}'
assert 'InterlockedExchange(&g_contentProfile, want);' in UE3, \
    'the loaded profile is not published to the thread that applies it'
assert 'prof <= 0 ? -1 : (prof > 2 ? 1 : prof - 1)' in UE3, \
    'the ini profile numbering is not mapped onto the internal off/0/1'
print('6. [Content] Profile, Commands1, Commands2 and Restore are read from the ini and parsed')


print('\nall phase-6 checks passed')

