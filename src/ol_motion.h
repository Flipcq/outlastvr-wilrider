#pragma once
// OutlastVR Walrider - a free PC VR mod for Outlast (2013).
// Copyright (C) 2026 the Outlast VR authors.
//
// A fork of OutlastVR by StrikeZoneVR (https://github.com/StrikeZoneVR-hub/OutlastVR),
// distributed under the same terms. Not affiliated with or endorsed by StrikeZoneVR.
// Outlast is a game by Red Barrels; this mod contains no game files.
//
// This program is free software: you can redistribute it and/or modify it under
// the terms of the GNU General Public License as published by the Free Software
// Foundation, either version 3 of the License, or (at your option) any later
// version. It is distributed WITHOUT ANY WARRANTY; without even the implied
// warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
// GNU General Public License in LICENSE for details.
//
// [PHASE1] Locomotion on the virtual pad: snap/smooth turn, walk direction, stick pitch and
// physical crouch. Called from the XInput hook in d3d9_proxy.cpp.
#include <Windows.h>
struct OLXrPad;

void OLMotion_Init();                 // reads [Input] from outlastvr.ini; call once at startup
void OLMotion_Save(const wchar_t* ini);
// Rewrites the sticks in place (all -1..1) and returns extra XInput buttons to OR in.
// camcorderUp: the right stick's vertical axis belongs to camcorder zoom.
WORD OLMotion_Process(const OLXrPad& p, bool camcorderUp, float* moveX, float* moveY,
                      float* lookX, float* lookY);

// Menu bindings.
extern "C" int   OLMotion_GetTurnMode();      extern "C" void OLMotion_SetTurnMode(int v);    // 0 smooth, 1 snap
extern "C" int   OLMotion_GetSnapDeg();       extern "C" void OLMotion_SetSnapDeg(int v);
extern "C" int   OLMotion_GetSnapBlink();     extern "C" void OLMotion_SetSnapBlink(int v);
extern "C" float OLMotion_GetTurnSpeed();     extern "C" void OLMotion_SetTurnSpeed(float v);
extern "C" int   OLMotion_GetTurnDegPerSec(); extern "C" void OLMotion_SetTurnDegPerSec(int v);   // (Test46) 30..360
extern "C" int   OLMotion_GetWalkDir();       extern "C" void OLMotion_SetWalkDir(int v);     // 0 body, 1 head, 2 left hand
extern "C" int   OLMotion_GetStickPitch();    extern "C" void OLMotion_SetStickPitch(int v);
extern "C" int   OLMotion_GetPhysCrouch();    extern "C" void OLMotion_SetPhysCrouch(int v);
extern "C" float OLMotion_GetCrouchDepth();   extern "C" void OLMotion_SetCrouchDepth(float v);
extern "C" int   OLMotion_CrouchStatus();     // -1 unavailable, 0 standing, 1 crouched (game)
