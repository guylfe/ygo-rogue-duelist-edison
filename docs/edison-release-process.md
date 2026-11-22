# Edison releases

The fork's `main` branch checks for stable Thronior releases daily at 05:23 UTC. Maintainers can also run the **Edison upstream releases** workflow manually. Each new tag gets one `edison/upstream/<tag>` candidate branch and draft PR. Read-only regressions check that candidate. The daily check compares the upstream tag with `docs/edison-upstream-state.json` on `edison/android-three-acts`. That baseline advances when the selected changes are merged.

Review the draft and its regression run. The review file lists the paths that applied, conflicts and deferred changes. Keep Edison’s own format rules, boosts, pack choices, roster, app ID and save scheme. Evaluate deferred changes in their own review. Mark the candidate ready and merge approved changes to `edison/android-three-acts`. The workflow creates draft PRs and runs tests. The signing key stays on the maintainer’s computer.

## Build and publish on the signing computer

1. Check the previous Edison Android release. Read its `edison-android-update.json` or its APK version code for older builds. Set `EDISON_ANDROID_PREVIOUS_CODE` to the previous code, choose a larger `EDISON_ANDROID_VERSION_CODE`, and advance `VERSION`. Use the existing Edison signing key described in the [Android readme](../android/README.md).
2. Run `python -B tools/build_android.py` and `python -B tools/build_pwa.py --output releases/web-VERSION`. Confirm both menus show the intended version, then run `python -B tools/finalize_releases.py`. The finalizer checks the installed package ID and signer embedded in the APK and writes `edison-android-update.json`. If you choose a custom APK output folder, keep the file name `Rogue-Duelist-Edison-vVERSION.apk`.
3. Push the tested fork source. Create a GitHub draft release tagged `edison-vVERSION` at that exact commit. Upload the APK, web ZIP and `edison-android-update.json`. Compare GitHub's recorded APK size and SHA-256 with the metadata. Publish as the latest stable release after the artifacts match.
4. Read the fork’s latest release back. Confirm the release tag, source commit, canonical APK name, version code, package ID, minimum Android API level, signer, size and digest. The Android startup prompt and the manual check use this channel. Older release assets remain available for troubleshooting.
