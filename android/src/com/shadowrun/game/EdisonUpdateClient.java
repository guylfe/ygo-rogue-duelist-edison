package com.shadowrun.game;

import android.content.pm.PackageInfo;
import android.content.pm.Signature;
import android.os.Build;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Locale;
import javax.net.ssl.HttpsURLConnection;
import org.json.JSONObject;

final class EdisonUpdateClient {
    private volatile boolean cancelled;
    private volatile HttpsURLConnection connection;

    EdisonRelease.Update check(PackageInfo installed, boolean startup) throws Exception {
        return EdisonRelease.check(installed.packageName, signerHash(installed), installed.getLongVersionCode(),
                Build.VERSION.SDK_INT, (address, redirects, limit) -> json(address, redirects, limit, startup));
    }

    private JSONObject json(String address, boolean redirects, int limit, boolean startup) throws Exception {
        HttpsURLConnection c = open(address, redirects, startup ? 5000 : 20000, startup ? 5000 : 30000);
        try (InputStream in = c.getInputStream(); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[4096];
            for (int n; (n = in.read(buffer)) != -1;) {
                ensureOpen();
                if (out.size() + n > limit) throw new IOException("Invalid release response size.");
                out.write(buffer, 0, n);
            }
            return new JSONObject(new String(out.toByteArray(), StandardCharsets.UTF_8));
        } finally { disconnect(); }
    }

    HttpsURLConnection openDownload(String address) throws IOException {
        return open(address, true, 20000, 30000);
    }

    private HttpsURLConnection open(String address, boolean allowRedirect, int connectTimeout, int readTimeout) throws IOException {
        URL url = new URL(address);
        for (int redirects = 0; redirects <= 4; redirects++) {
            ensureOpen();
            if (redirects > 0 && !EdisonRelease.downloadRedirect(url)) throw new IOException("Unexpected download address.");
            HttpsURLConnection c = (HttpsURLConnection) url.openConnection();
            connection = c;
            c.setConnectTimeout(connectTimeout);
            c.setReadTimeout(readTimeout);
            c.setInstanceFollowRedirects(false);
            c.setRequestProperty("User-Agent", "RogueDuelistEdison-Android");
            c.setRequestProperty("Accept-Encoding", "identity");
            try {
                int code = c.getResponseCode();
                if (code == 200) return c;
                String location = c.getHeaderField("Location");
                if (!allowRedirect || code < 300 || code >= 400 || location == null) throw new IOException("HTTP " + code);
                url = new URL(url, location);
            } catch (IOException | RuntimeException e) {
                disconnect();
                throw e;
            }
            disconnect();
        }
        throw new IOException("Too many download redirects.");
    }

    void cancel() { cancelled = true; }

    void disconnect() {
        HttpsURLConnection c = connection;
        connection = null;
        if (c != null) c.disconnect();
    }

    void ensureOpen() throws IOException {
        if (cancelled || Thread.currentThread().isInterrupted()) throw new IOException("Update cancelled.");
    }

    static String signerHash(PackageInfo info) throws Exception {
        Signature[] signers = info.signingInfo == null ? null : info.signingInfo.getApkContentsSigners();
        if (signers == null || signers.length != 1) throw new IOException("Could not verify the Edison signer.");
        return hex(MessageDigest.getInstance("SHA-256").digest(signers[0].toByteArray()));
    }

    static String hex(byte[] bytes) {
        StringBuilder hex = new StringBuilder(bytes.length * 2);
        for (byte b : bytes) hex.append(String.format(Locale.ROOT, "%02x", b & 0xff));
        return hex.toString();
    }
}
