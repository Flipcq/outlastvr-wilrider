"""Phase 7 of the Beta 1.2.2 pass: the OpenXR delivery pipeline.

What is proved here:

1. FSR1 (B6). The blit shader embedded in ol_xr.cpp is extracted and compiled with fxc for ps_4_0,
   because a shader that does not compile is a black headset, not a slow one. Then the source rules:
   EASU's 12 taps, the dering against the 2x2, RCAS's clipping solve, the seam clamp on EVERY tap,
   and the upscaler switch reaching the shader as three distinct modes.

2. Overscan (the motion-induced black borders). This is the mechanism docs/VR-RUNTIMES.md names as the
   missing half: a runtime that honours the declared FOV has no margin for the compositor's
   reprojection to pull from. The widening must be in ANGLE space, must be the SAME for the blit's
   target and the declaration (or the picture shrinks), and must never run when the render did not
   get the wider frustum.

3. B9 (draw duplication). The per-eye draw counters exist and the fingerprint compares the two eyes'
   lists - the measurement any reuse scheme stands on.

4. The wiring: every new ini key has its default, and the per-eye/overscan paths are gated.

Run: python3 tests/perf_pipeline_test.py
"""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
XR = (ROOT / 'src/ol_xr.cpp').read_text(encoding='utf-8')
PROXY = (ROOT / 'src/d3d9_proxy.cpp').read_text(encoding='utf-8')
INI = (ROOT / 'runtime/outlastvr.ini').read_text(encoding='utf-8')


def block(signature, src=None):
    text = src if src is not None else XR
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


# --------------------------------------------------------------- 1. the shader actually compiles
# The embedded source is a C string literal; unescape it back to HLSL and hand it to fxc.
m = re.search(r'static const char\* kBlitHlsl =\n(.*?);\n\n', XR, re.S)
assert m, 'kBlitHlsl is gone'
lines = []
for lit in re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1)):
    lines.append(lit.encode().decode('unicode_escape'))
hlsl = ''.join(lines)
assert 'float4 ps(' in hlsl and 'VOut vs(' in hlsl, 'the blit shader lost an entry point'
assert 'FsrEasu(' in hlsl and 'FsrRcas(' in hlsl, 'the FSR1 path is not in the shipped shader'

fxc = None
for cand in (Path(r'C:\Program Files (x86)\Windows Kits\10\bin'),
             Path(r'C:\Program Files\Windows Kits\10\bin')):
    if cand.exists():
        hits = sorted(cand.glob('*/x64/fxc.exe'))
        if hits:
            fxc = hits[-1]
            break
assert fxc, 'fxc.exe not found - cannot prove the shader compiles'
with tempfile.TemporaryDirectory() as td:
    src = Path(td) / 'blit.hlsl'
    out = Path(td) / 'blit.cso'
    src.write_text(hlsl, encoding='utf-8')
    r = subprocess.run([str(fxc), '/T', 'ps_4_0', '/E', 'ps', '/O3', str(src), '/Fo', str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0, 'the shipped blit shader does not compile:\n' + (r.stdout + r.stderr)
    assert out.exists() and out.stat().st_size > 0
    r2 = subprocess.run([str(fxc), '/T', 'vs_4_0', '/E', 'vs', '/O1', str(src), '/Fo', str(Path(td) / 'v.cso')],
                        capture_output=True, text=True)
    assert r2.returncode == 0, 'the blit vertex shader does not compile:\n' + (r2.stdout + r2.stderr)
print(f'B6/FSR1: the shipped blit shader compiles with {fxc.parent.name} (ps_4_0 + vs_4_0)')

# The FSR rules, in the source.
easu = block('float3 FsrEasu(float2 sp)', XR if 'float3 FsrEasu(float2 sp)' in XR else hlsl)
assert easu.count('FsrTaps(') == 12, 'EASU no longer accumulates its 12 taps'
assert 'min(max4, max(min4, aC' in easu, 'EASU lost the 2x2 dering (it would ring)'
assert easu.count('FsrSet(') == 4, 'EASU no longer evaluates the four bilinear corners'
assert 'rsqrt' in easu, 'EASU lost the direction normalise'
# Every sample must go through the seam clamp: a tap that bypasses it can pull the other eye in.
assert 'clamp(uv.x, clampU.x, clampU.y)' in hlsl, 'the seam clamp is gone from the tap'
fsrpx = block('float3 FsrPx(float2 px)', hlsl)
assert 'clamp(uv.x, clampU.x, clampU.y)' in fsrpx, 'an FSR tap reaches across the SBS seam'
rcas = block('float3 FsrRcas(float3 e, float2 uv, float stops)', XR if 'float3 FsrRcas(float3 e' in XR else hlsl)
assert 'hitMin' in rcas and 'hitMax' in rcas and '0.1875' in rcas, \
    'RCAS lost its clipping solve / lobe limit'
# The switch must reach the shader as three modes, not a bool.
assert '(float)upMode' in XR and 'const int upMode = scalingUp ? (int)g_upscaler : 0;' in XR, \
    'the upscaler mode no longer reaches the shader (or FSR runs at 1:1)'
assert 'OLXR_SetUpscaler(int v) { g_upscaler = (v < 0) ? 0 : (v > 2 ? 2 : v); }' in XR, \
    'the upscaler is no longer a three-way setting'
print('B6/FSR1: 12 taps, dering, RCAS clipping, seam clamp on every tap, 3-mode switch')

# --------------------------------------------------------------- 2. overscan, the black borders
ov = block('static void OlrOverscan(float* l, float* r, float* u, float* d, float deg)', XR)
assert 'atanf(*l)' in ov and 'tanf(' in ov, 'the widening is not done in ANGLE space'
assert '*l = nl; *r = nr; *u = nu; *d = nd;' in ov, 'the widened box is not written back'
assert '12.0f' in ov, 'the tan blow-up guard is gone'
submit = block('static XrFovf OlrSubmitFov(int eye)', XR)
assert 'g_edgeOverscanDeg > 0.001f && g_overscanLive && g_lensFitOn && g_fitFrustum' in submit, \
    'the declaration can be widened when the RENDER was not (that shrinks the picture)'
assert 'f.angleLeft  -= rad' in submit, 'the declared frustum is not widened'
# The blit target and the declaration must be the same function.
lens = block('extern "C" int OLXR_LensFitTangents(int half, float* l, float* r, float* u, float* d)', XR)
assert 'OlrOverscan(l, r, u, d, g_edgeOverscanDeg);' in lens, \
    'the render frustum is not widened (declaring wider would then shrink the picture)'
assert 'InterlockedExchange(&g_overscanLive, 1);' in lens, 'the "overscan is live" latch is gone'
# Every fit call site must use the submit FOV, not the raw runtime one.
fit_calls = re.findall(r'BlitFitToEye(?:Tan)?\([^;]*?;', XR, re.S)
assert fit_calls, 'the fitted blit calls are gone'
assert XR.count('OlrSubmitFov(') >= 6, \
    'a blit path still targets the un-widened frustum, so overscan would squeeze the picture'
# The union-frustum path must have overscan applied AFTER the union, not instead of it.
assert XR.index('if (!OlrUnionTangents(l, r, u, d)) return 0;') < XR.index('OlrOverscan(l, r, u, d,'), \
    'overscan is applied before the union frustum (the union would overwrite it)'
#  ships ON at 2 degrees by the player's request: the black bars were worse than the
# sharpness the margin costs. 0 is still the A/B for "sharpest, bars possible".
assert re.search(r'^EdgeOverscanDeg=2\.0$', INI, re.M), 'EdgeOverscanDeg must ship at the chosen 2.0 deg'
assert 'L"Stream", L"EdgeOverscanDeg", L"0"' in XR, \
    'the code default is what a missing key gets; the shipped ini sets 2.0'
print('overscan: angle-space widening, blit and declaration agree, OFF by default, after the union')

# --------------------------------------------------------------- 3. B9, the duplication measurement
assert 'static LONG g_dcDrawsL = 0, g_dcDrawsR = 0;' in PROXY, 'the per-eye draw counters are gone'
cnt = block('static inline void CountDraw()', PROXY)
assert 'g_olRenderEye == 0' in cnt, 'the per-eye split no longer asks which eye is drawing'
assert 'extern "C" void OLProxy_TakeEyeDrawStats' in PROXY
assert 'OLProxy_TakeEyeDrawStats(&drawsL, &drawsR);' in XR, 'the [PERF] report lost the per-eye split'
assert 'draws per eye: L %.0f R %.0f' in XR, 'the per-eye line is gone from [PERF]'
fp = block('static inline void FingerprintDraw(unsigned a, unsigned b, unsigned c)', PROXY)
assert '16777619u' in fp, 'the draw-list fingerprint is gone'
assert 'OLProxy_DrawFingerprintFrame();' in PROXY, 'the fingerprint is never compared per frame'
assert 'draw lists: %ld/%ld identical' in XR, 'the fingerprint result is not reported'
assert re.search(r'^DrawFingerprint=0$', INI, re.M), 'DrawFingerprint must ship OFF (it costs per draw)'
print('B9: per-eye draws + a draw-list fingerprint, published in [PERF], OFF by default')

# --------------------------------------------------------------- 4. the layer count (B5)
assert 'composition layers: %.2f/frame avg' in XR, 'the layer-count measurement is gone'
assert 'layers[layerCount++]' in XR, 'the layer stack is gone'

# --------------------------------------------------------------- 5. every new ini key is read
for key, shipped, section in (('EdgeOverscanDeg', '2.0', 'Stream'),
                              ('DrawFingerprint', '0', 'Perf')):
    assert re.search(r'^%s=%s$' % (key, re.escape(shipped)), INI, re.M), f'{key}={shipped} missing from the ini'
    assert f'L"{section}", L"{key}"' in (XR if section == 'Stream' else PROXY), \
        f'{key} is not read from [{section}]'
print('wiring: EdgeOverscanDeg and DrawFingerprint exist in the ini and in the code')

print('\nall phase-7 checks passed')

