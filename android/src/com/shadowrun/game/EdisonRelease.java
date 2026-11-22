package com.shadowrun.game;

import java.io.IOException;
import java.net.URL;
import org.json.JSONArray;
import org.json.JSONObject;

final class EdisonRelease {
    static final String SOURCE = "https://github.com/guylfe/ygo-rogue-duelist-edison/releases/download/";
    static final String LATEST = "https://api.github.com/repos/guylfe/ygo-rogue-duelist-edison/releases/latest";
    static final String METADATA = "edison-android-update.json";
    static final String PACKAGE = "io.github.guylfe.rogueduelist.edison";
    static final long MAX_APK_BYTES = 1024L * 1024 * 1024;
    private static final int LEGACY_MIN_SDK = 29;

    static final class Update {
        final String version, url, sha256;
        final long versionCode, bytes;

        Update(String version, long versionCode, long bytes, String sha256, String url) {
            this.version = version;
            this.versionCode = versionCode;
            this.bytes = bytes;
            this.sha256 = sha256;
            this.url = url;
        }
    }

    interface JsonReader {
        JSONObject read(String address, boolean redirects, int limit) throws Exception;
    }

    static Update check(String packageName, String signer, long installedCode, int sdk, JsonReader read) throws Exception {
        JSONObject release = read.read(LATEST, false, 524288);
        if (release.optBoolean("draft") || release.optBoolean("prerelease"))
            throw new IOException("No stable Edison release is available.");
        String tag = release.getString("tag_name");
        JSONArray assets = release.getJSONArray("assets");
        JSONObject manifestAsset = findAsset(assets, tag, METADATA);
        JSONObject meta = read.read(manifestAsset.getString("browser_download_url"), true, 4096);
        String version = meta.getString("version");
        long versionCode = meta.getLong("versionCode");
        long bytes = meta.getLong("bytes");
        String digest = meta.getString("sha256");
        int minSdk = meta.has("minSdk") ? meta.getInt("minSdk") : LEGACY_MIN_SDK;
        if (!version(version) || !tag.equals("edison-v" + version) || !PACKAGE.equals(packageName) ||
                !packageName.equals(meta.getString("package")) || !signer.equals(meta.getString("signerSha256")) ||
                versionCode <= 0 || versionCode > 2100000000L || minSdk <= 0 ||
                bytes <= 0 || bytes > MAX_APK_BYTES || !sha256(digest))
            throw new IOException("Edison's release details could not be verified.");
        JSONObject apk = findAsset(assets, tag, apkName(version));
        if (bytes != apk.getLong("size") || !("sha256:" + digest).equals(apk.getString("digest")))
            throw new IOException("The APK and release details disagree.");
        if (!newer(versionCode, installedCode)) return null;
        if (minSdk > sdk) throw new IOException("This Edison update requires a newer Android version.");
        return new Update(version, versionCode, bytes, digest, apk.getString("browser_download_url"));
    }

    private static JSONObject findAsset(JSONArray assets, String tag, String name) throws Exception {
        for (int i = 0; i < assets.length(); i++) {
            JSONObject asset = assets.getJSONObject(i);
            if (name.equals(asset.optString("name")) && "uploaded".equals(asset.optString("state")) &&
                    validAsset(asset.optString("browser_download_url"), tag, name)) return asset;
        }
        throw new IOException("The Edison update asset is missing.");
    }

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
