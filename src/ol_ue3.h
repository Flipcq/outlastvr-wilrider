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
// Outlast Stage 3: UE3 engine-side hook (CalcSceneView) + live offset discovery.
// Safe to call unconditionally: no-ops unless outlastvr.ini sets a CalcSceneViewRva.
void OLUE3_Init();
void OLUE3_ToggleSplit();
void OLUE3_ToggleAer();        // NUM2 - one-view-per-frame mode (A/B against the split)      // NUM4 - runtime on/off for the same-frame split
void OLUE3_AdjustEye(float d); // NUM1 / NUM3 - live IPD tuning (world units)
void OLUE3_ToggleBuildOrder(); // NUM6 - which eye is the PRIMARY view (diagnostic)
void OLUE3_SwapEyes();         // NUM5 - flip which side gets which eye
void OLUE3_ToggleOcclForce();  // NUM0 - bypass Outlast's per-object occlusion tracker (flicker A/B)
void OLUE3_ToggleHeadTrack();  // NUM. - head tracking on/off (A/B against gamepad-only)
void OLUE3_ToggleHeadPos();    // NUM/ - positional (lean/duck) on/off; OFF = camera stays put
void OLUE3_AdjustWorldScale(float mul);  // NUM+ / NUM- - uu per metre; scales head motion
