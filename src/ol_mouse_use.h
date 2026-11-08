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
#include "ol_xr.h"

// One owner calls this under the proxy's input lock. A failed release retains
// ownership so the watchdog can retry; blocked/held buttons never become clicks
// merely because a menu, grip chord or focus state changes.
struct OLMouseUse {
    static constexpr unsigned long InputTag = 0x4F4C5652; // OLVR synthetic mouse events
    bool previousDown = false;
    bool held = false;
    bool releasePending = false;

    template<class Send> void Sample(bool down, bool allowed, bool canStart, Send send) {
        const bool rising = down && !previousDown;
        previousDown = down;
        if (held && (releasePending || !down || !allowed)) {
            releasePending = true;
            if (send(false)) { held = false; releasePending = false; }
            return; // a release retry cannot turn into a delayed new click
        }
        if (!held && rising && allowed && canStart) { held = send(true); return; }
        // [MOUSEUSE] A PRESS THE GAME COULD NOT TAKE YET IS NOT SPENT.
        // canStart is "gameplay is running". Gameplay reports "not running" for a frame or two around
        // transitions - the locker enter / exit move is a special move, and a scripted move or a menu
        // flag does the same - so a press landing there was latched and dropped, and the player pressed
        // B again and again ("I have to press B several times"). The press now stays pending and clicks
        // on the first frame the game will take it. A press refused on purpose (!allowed: a menu, lost
        // focus) is still spent - it must not fire when the menu closes.
        if (down && !canStart) previousDown = false;
    }
    template<class Send> void Cancel(Send send) {
        Sample(true, false, false, send); // rearm only after a sampled release
    }
    // [MOUSEUSE] A MISSED SAMPLE IS NOT A CANCELLATION.
    // Cancel() above is for a state that really ended (a menu opened, focus was lost): it re-arms the
    // sampler so the held button cannot become a fresh click later. A sample that simply did not arrive
    // says nothing about the button, so it must only retry a pending release - it must not touch the
    // press state at all, or the player's press is eaten and B needs several tries.
    template<class Send> void Release(Send send) {
        if (!held) return;
        releasePending = true;
        if (send(false)) { held = false; releasePending = false; }
    }
};

// The same physical button must not become a different action when crossing a
// menu boundary (e.g. X accepting a menu must not crouch on Resume).
struct OLFaceButtonGate {
    bool inMenu = false;
    unsigned previous = 0, blocked = 0;
    unsigned Apply(unsigned buttons, bool menu) {
        if (menu != inMenu) blocked |= previous & buttons & (OLXR_BTN_X | OLXR_BTN_B);
        blocked &= buttons;
        previous = buttons;
        inMenu = menu;
        return buttons & ~blocked;
    }
};
