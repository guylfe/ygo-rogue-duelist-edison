package com.shadowrun.game;

import java.net.URL;

final class EdisonRelease {
    static final String SOURCE = "https://github.com/guylfe/ygo-rogue-duelist-edison/releases/download/";
    static final String LATEST = "https://api.github.com/repos/guylfe/ygo-rogue-duelist-edison/releases/latest";
    static final String METADATA = "edison-android-update.json";
    static final String PACKAGE = "io.github.guylfe.rogueduelist.edison";
    static final long MAX_APK_BYTES = 1024L * 1024 * 1024;

    static boolean version(String version) {
        return version != null && version.matches("(0|[1-9][0-9]{0,4})(\\.(0|[1-9][0-9]{0,4})){2}");
    }

    static boolean newer(long remote, long installed) {
        return remote > installed && remote <= 2100000000L;
    }

    static boolean sha256(String hash) {
        return hash != null && hash.matches("[0-9a-f]{64}");
    }

    static String apkName(String version) {
        return "Rogue-Duelist-Edison-v" + version + ".apk";
    }

    static boolean validAsset(String url, String tag, String name) {
        return tag.startsWith("edison-v") && version(tag.substring(8)) &&
                (METADATA.equals(name) || apkName(tag.substring(8)).equals(name)) &&
                (SOURCE + tag + "/" + name).equals(url);
    }

    static boolean downloadRedirect(URL url) {
        String host = url.getHost();
        return "https".equals(url.getProtocol()) && url.getUserInfo() == null &&
                (url.getPort() == -1 || url.getPort() == 443) &&
                (host.equals("release-assets.githubusercontent.com") ||
                    host.equals("objects.githubusercontent.com"));
    }

    private EdisonRelease() {}
}
