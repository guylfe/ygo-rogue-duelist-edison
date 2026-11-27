# Edison releases

The fork's `main` branch checks for stable Thronior releases daily at 05:23 UTC. Maintainers can also run the **Edison upstream releases** workflow manually. Each new tag gets one `edison/upstream/<tag>` candidate branch and draft PR. Read-only regressions check that candidate. The daily check compares the upstream tag with `docs/edison-upstream-state.json` on `edison/android-three-acts`. That baseline advances when the selected changes are merged.

Review the draft and its regression run. The review file lists the paths that applied, conflicts and deferred changes. Keep Edison’s own format rules, boosts, pack choices, roster, app ID and save scheme. Evaluate deferred changes in their own review. Mark the candidate ready and merge approved changes to `edison/android-three-acts`. The workflow creates draft PRs and runs tests. The signing key stays on the maintainer’s computer.

## Build and publish on the signing computer

1. Check the previous Edison Android release. Read its `edison-android-update.json` or its APK version code for older builds. Set `EDISON_ANDROID_PREVIOUS_CODE` to the previous code, choose a larger `EDISON_ANDROID_VERSION_CODE`, and advance `VERSION`. Use the existing Edison signing key described in the [Android readme](../android/README.md).
2. Run `python -B tools/build_android.py` and `python -B tools/build_pwa.py --output releases/web-VERSION`. Confirm both menus show the intended version, then run `python -B tools/finalize_releases.py`. The finalizer checks the installed package ID and signer embedded in the APK and writes `edison-android-update.json`. If you choose a custom APK output folder, keep the file name `Rogue-Duelist-Edison-vVERSION.apk`.
3. Push the tested fork source. Create a GitHub draft release tagged `edison-vVERSION` at that exact commit. Upload the APK, web ZIP and `edison-android-update.json`. Compare GitHub's recorded APK size and SHA-256 with the metadata. Publish as the latest stable release after the artifacts match.
4. Read the fork’s latest release back. Confirm the release tag, source commit, canonical APK name, version code, package ID, minimum Android API level, signer, size and digest. The Android startup prompt and the manual check use this channel. Older release assets remain available for troubleshooting.

## Hosted web and playtest feedback

Publish the verified web build directory to the existing Edison Netlify site after validating the ZIP. The hosted site, builds distributed as ZIPs and the Android edition send playtest notes to the shared service. Keep the web site URL stable so the browser retains its IndexedDB saves. Use the existing export/import controls to move a save from a different origin. Verify live-version.json reports the new version and asset hash after each host deployment.

Players send suggestions from **Playtest note** during a solo run, or from **Options** in a duel. The client saves each queued note on the device and retries with its original report ID. An HTTP 200 receipt must match the game, report ID and `playtest-feedback/<report-id>.json` before the client marks it sent. Reports already marked sent in an older build stay in local history. Drafts opened in an old browser flow stay available for manual submission.

Each suggestion is a separate JSON file in the private feedback intake. Follow the [maintenance commands in the feedback service](https://github.com/guylfe/game-feedback-service#retrieve-and-remove-suggestions). After implementing and verifying a suggestion, run `node manage-feedback.mjs implemented edison REPORT_ID CHECKOUT` from the service checkout to remove the stored suggestion and the exported local copy. Keep pending and partially implemented suggestions in intake. Record the report ID with the verification evidence so the team can identify the exact file to remove.

## Independent game services

Edison uses a numeric display and update version from the generated `replay-version.js`. Its tag handshake, new replay journals and new playtest notes identify the build as `VERSION-edison`. Preserve the numeric Android version, app ID, signing key, hosted origin and web save database when publishing.

Tag Duels, Draft Duels, Ultimate Collector and its leaderboard, Cloud Save, Link Devices, replay uploads, behaviour flags and worldwide statistics are unavailable. Solo play, local replay playback, Device Stats and private playtest notes stay available. Players can move progress using a save file from Android's **Devices & App** settings or the web app's backup controls. Old cloud codes and queued reports stay on the device. The release packages only the reserved IDs for retired Collector opponents. Previously saved routes can still use their frozen decks.

Keep the upstream Workers, former room URL overrides and old Collector roster refresh out of Edison releases. The shared packaging step refuses an upstream Worker hostname. Any future Edison service deployment needs Edison-owned endpoints, an independent state store, and separate verification of that service before client release.
