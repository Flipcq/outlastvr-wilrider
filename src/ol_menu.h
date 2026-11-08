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
// In-headset settings menu for the Outlast VR probe (INSERT toggles it).
//
// Everything tunable lives here rather than in outlastvr.ini: editing an ini means taking the
// headset off, which makes tuning a thing you do blind and once instead of live and properly.
struct IDirect3DDevice9;

void OLMenu_Render(IDirect3DDevice9* dev, unsigned bbW, unsigned bbH);  // call before XR capture
void OLMenu_OnDeviceLost();                                            // BEFORE the game's Reset
void OLMenu_OnDeviceReset();                                           // AFTER a successful Reset
void OLMenu_StartInput(void* hinst);   // installs the low-level mouse hook (once, at startup)
void OLMenu_Toggle();
void OLMenu_Nav(int dy);        // -1 up, +1 down
void OLMenu_Adjust(int dir);    // -1 left, +1 right (or activate, for action rows)
int  OLMenu_Visible();
