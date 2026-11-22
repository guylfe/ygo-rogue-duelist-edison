package com.shadowrun.game;

import java.net.URL;

public final class EdisonReleaseTest {
    private static void check(boolean condition, String description) {
        if (!condition) throw new AssertionError(description);
    }

    public static void main(String[] args) throws Exception {
        String tag = "edison-v0.2.42";
        String name = "Rogue-Duelist-Edison-v0.2.42.apk";
        String url = EdisonRelease.SOURCE + tag + "/" + name;
        check(EdisonRelease.validAsset(url, tag, name), "exact Edison release");
        check(EdisonRelease.validAsset(EdisonRelease.SOURCE + tag + "/edison-android-update.json",
                tag, EdisonRelease.METADATA), "exact metadata asset");
        check(!EdisonRelease.validAsset(url, "v0.2.42", name), "upstream tag");
        check(!EdisonRelease.validAsset(url.replace("guylfe", "Thronior"), tag, name), "upstream repository");
        check(!EdisonRelease.validAsset(url + "?file=replacement.apk", tag, name), "asset URL mismatch");
        check(!EdisonRelease.validAsset(url, tag, "another.apk"), "asset name mismatch");
        check(!EdisonRelease.version("0.2.42-rc1"), "prerelease version");
        check(EdisonRelease.newer(3, 2), "new release");
        check(!EdisonRelease.newer(3, 3) && !EdisonRelease.newer(2, 3), "current or older");
        check(!EdisonRelease.newer(2100000001L, 3), "invalid Android version code");
        check(EdisonRelease.sha256("f".repeat(64)) && !EdisonRelease.sha256("f".repeat(63)), "digest width");
        check(EdisonRelease.downloadRedirect(new URL("https://release-assets.githubusercontent.com/file")), "GitHub CDN");
        check(!EdisonRelease.downloadRedirect(new URL("http://release-assets.githubusercontent.com/file")), "unencrypted CDN");
        check(!EdisonRelease.downloadRedirect(new URL("https://release-assets.githubusercontent.com.evil.test/file")), "untrusted CDN");
        check(!EdisonRelease.downloadRedirect(new URL("https://user@release-assets.githubusercontent.com/file")), "redirect user info");
        System.out.println("PASS Edison asset identity, HTTPS redirects, version ordering and SHA-256 validation");
    }
}
