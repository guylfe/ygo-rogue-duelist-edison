# Android app

> **Platform status:** The native Windows desktop edition is deprecated and is no longer maintained or distributed. The supported versions are this Android app and the webapp; the webapp also works in desktop browsers. Existing saves from the deprecated native app can be imported through the webapp Settings.

Install the signed APK from the [latest Edison release](https://github.com/guylfe/ygo-rogue-duelist-edison/releases/latest) on Android 10 or newer. Use a current Android System WebView. The APK bundles the card images, tokens, boosters, characters, music, campaign rules and duel scripts for offline solo play.

This build uses the Project Ignis duel core through `ocgcore-wasm`, with a touch-friendly field layout. It does not embed the native EDOPro GUI.

The Python campaign modules are copied into the APK and run offline with Pyodide. Characters, draft packs, deck lists, shops, relic effects, achievements and progression use the shared campaign data. Relic effects run as Lua effects inside the duel core. The mobile opponent decision layer is in `web/duel.js`.

## Updating

Rogue Duelist: Edison uses application ID `io.github.guylfe.rogueduelist.edison` and a separate Android save directory. Version 0.2.43 and later check for updates in the background at launch. When a compatible update is available, the main menu offers **Update now** to download it or **Later** to dismiss the prompt for this launch. You can also use **Settings → Devices &amp; App → Check for Edison updates** and choose **Download update**. After the download is verified, select **Install update** and confirm the normal Android prompt. The first in-game install may ask you to allow updates from this app. Installing over an existing Edison build keeps your saves.

On Windows, set `JAVA_HOME` to JDK 17 and `ANDROID_HOME` to an SDK with Android 35 and Build Tools 35.0.0. Install Node and Python 3 with Pillow. Set `EDISON_ANDROID_KEYSTORE` to the existing private PKCS#12 key outside the checkout and provide its password through `EDISON_ANDROID_KEYSTORE_PASSWORD`. The build checks the signing certificate. Preserve the key and its password for future updates.

Run `python -B tools/build_android.py` from the repository root. Use `--sync-only` to refresh web assets without signing. `web/build.json` records the shared-campaign checksum. See the [Edison release process](../docs/edison-release-process.md) for signing, updater metadata and publication.

Saves are app-private and use Android AtomicFile. Duel responses are journaled and replayed on Continue. Android and browser progress are separate; there is no automatic cloud synchronization. Uninstalling the Android app deletes its private save.

## Controls

- Tap your card, then its floating action button. Tap a glowing zone to place it.
- Phase buttons sit between the monster rows. Effect and target choices appear over the field.
- Tap a card to update the left preview; Inspect opens its complete text.
- Both players have five monster zones, five Spell/Trap zones, Field Spell, Main Deck, Extra Deck, Graveyard and Banished piles. Opponent hand/set cards remain hidden.
- Tap a visible pile to browse it. The opponent's deck and Extra Deck are private.
- Save / Menu pauses the duel. Continue resumes it, including after closing the app.
- Testing code: Settings → Testing → `heartofthecards`.

## Sources and licenses

- [Project Ignis EDOPro](https://github.com/edo9300/edopro) and [Android GUI source](https://github.com/edo9300/edopro-android).
- [ocgcore-wasm](https://github.com/n1xx1/ocgcore-wasm), version 0.1.2; MIT wrapper with Project Ignis core licensing.
- [Pyodide](https://pyodide.org/), version 0.27.7; Mozilla Public License 2.0 runtime.
- Card/character/game images and music remain copyrighted by their original owners. See `../assets/CREDITS.md` and the runtime texture/sound credits. Private, unofficial fan experiment.
