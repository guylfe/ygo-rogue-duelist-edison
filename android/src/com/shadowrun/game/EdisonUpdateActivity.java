package com.shadowrun.game;

import android.app.Activity;
import android.app.ActivityOptions;
import android.app.PendingIntent;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageInstaller;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.view.Gravity;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import javax.net.ssl.HttpsURLConnection;

/** Checks the fork's stable channel. A download and the Android install both require player action. */
public final class EdisonUpdateActivity extends Activity {
    private static final String INSTALL_RESULT = EdisonRelease.PACKAGE + ".UPDATE_RESULT";
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private volatile boolean closed;
    private volatile boolean committing;
    private volatile HttpsURLConnection connection;
    private volatile File candidate;
    private TextView status;
    private ProgressBar progress;
    private Button primary;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout panel = new LinearLayout(this);
        panel.setOrientation(LinearLayout.VERTICAL);
        panel.setGravity(Gravity.CENTER);
        int padding = (int) (24 * getResources().getDisplayMetrics().density);
        panel.setPadding(padding, padding, padding, padding);
        TextView title = new TextView(this);
        title.setText("Rogue Duelist: Edison updates");
        title.setTextSize(24);
        panel.addView(title);
        status = new TextView(this);
        status.setPadding(0, padding, 0, padding);
        status.setGravity(Gravity.CENTER);
        panel.addView(status);
        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setMax(100);
        panel.addView(progress, new LinearLayout.LayoutParams(-1, padding));
        primary = new Button(this);
        panel.addView(primary);
        Button close = new Button(this);
        close.setText("Close");
        close.setOnClickListener(v -> finish());
        panel.addView(close);
        setContentView(panel);
        if (INSTALL_RESULT.equals(getIntent().getAction())) handleInstallResult(getIntent());
        else checkRelease();
    }

    private void show(String message, String action, Runnable click) {
        runOnUiThread(() -> {
            if (closed || isFinishing()) return;
            status.setText(message);
            progress.setIndeterminate(action == null);
            primary.setEnabled(click != null);
            if (action != null) primary.setText(action);
            primary.setOnClickListener(click == null ? null : v -> click.run());
        });
    }

    private void checkRelease() {
        show("Checking for Edison updates…", null, null);
        worker.execute(() -> {
            try {
                PackageInfo installed = installed();
                JSONObject release = json(EdisonRelease.LATEST, false, 524288);
                if (release.optBoolean("draft") || release.optBoolean("prerelease"))
                    throw new IOException("No stable Edison release is available.");
                String tag = release.getString("tag_name");
                JSONArray assets = release.getJSONArray("assets");
                JSONObject manifestAsset = findAsset(assets, tag, EdisonRelease.METADATA);
                JSONObject meta = json(manifestAsset.getString("browser_download_url"), true, 4096);
                String version = meta.getString("version");
                long versionCode = meta.getLong("versionCode");
                long bytes = meta.getLong("bytes");
                String digest = meta.getString("sha256");
                if (!EdisonRelease.version(version) || !tag.equals("edison-v" + version) ||
                        !installed.packageName.equals(EdisonRelease.PACKAGE) ||
                        !installed.packageName.equals(meta.getString("package")) ||
                        !signerHash(installed).equals(meta.getString("signerSha256")) ||
                        versionCode <= 0 || versionCode > 2100000000L ||
                        bytes <= 0 || bytes > EdisonRelease.MAX_APK_BYTES || !EdisonRelease.sha256(digest))
                    throw new IOException("Edison's release details could not be verified.");
                JSONObject apk = findAsset(assets, tag, EdisonRelease.apkName(version));
                if (bytes != apk.getLong("size") || !("sha256:" + digest).equals(apk.getString("digest")))
                    throw new IOException("The APK and release details disagree.");
                if (!EdisonRelease.newer(versionCode, installed.getLongVersionCode())) {
                    show("You’re up to date. Installed version: " + installed.versionName, "Check again", this::checkRelease);
                    return;
                }
                String url = apk.getString("browser_download_url");
                show(String.format(Locale.ROOT, "Edison %s is available (%.0f MB).", version, bytes / 1000000.0),
                        "Download update", () -> download(url, version, versionCode, bytes, digest));
            } catch (Exception e) {
                show("Could not check for Edison updates. Check your connection and try again.", "Retry", this::checkRelease);
            }
        });
    }

    private static JSONObject findAsset(JSONArray assets, String tag, String name) throws Exception {
        for (int i = 0; i < assets.length(); i++) {
            JSONObject asset = assets.getJSONObject(i);
            if (name.equals(asset.optString("name")) && "uploaded".equals(asset.optString("state")) &&
                    EdisonRelease.validAsset(asset.optString("browser_download_url"), tag, name)) return asset;
        }
        throw new IOException("The Edison update asset is missing.");
    }

    private HttpsURLConnection open(String address, boolean allowRedirect) throws IOException {
        URL url = new URL(address);
        for (int redirects = 0; redirects <= 4; redirects++) {
            ensureOpen();
            if (redirects > 0 && !EdisonRelease.downloadRedirect(url)) throw new IOException("Unexpected download address.");
            HttpsURLConnection c = (HttpsURLConnection) url.openConnection();
            connection = c;
            c.setConnectTimeout(20000);
            c.setReadTimeout(30000);
            c.setInstanceFollowRedirects(false);
            c.setRequestProperty("User-Agent", "RogueDuelistEdison-Android");
            c.setRequestProperty("Accept-Encoding", "identity");
            int code = c.getResponseCode();
            if (code == 200) return c;
            String location = c.getHeaderField("Location");
            c.disconnect();
            if (!allowRedirect || code < 300 || code >= 400 || location == null) throw new IOException("HTTP " + code);
            url = new URL(url, location);
        }
        throw new IOException("Too many download redirects.");
    }

    private JSONObject json(String address, boolean redirects, int limit) throws Exception {
        HttpsURLConnection c = open(address, redirects);
        try (InputStream in = c.getInputStream(); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[4096];
            for (int n; (n = in.read(buffer)) != -1;) {
                ensureOpen();
                if (out.size() + n > limit) throw new IOException("Invalid release response size.");
                out.write(buffer, 0, n);
            }
            return new JSONObject(new String(out.toByteArray(), StandardCharsets.UTF_8));
        } finally { c.disconnect(); connection = null; }
    }

    private void download(String url, String version, long code, long bytes, String hash) {
        show("Downloading Edison " + version + "…", null, null);
        worker.execute(() -> {
            HttpsURLConnection source = null;
            try {
                if (getCacheDir().getUsableSpace() < bytes * 2 + 32L * 1024 * 1024)
                    throw new IOException("Free some space before downloading the update.");
                candidate = File.createTempFile("edison-update-", ".apk", getCacheDir());
                source = open(url, true);
                MessageDigest sha = MessageDigest.getInstance("SHA-256");
                try (InputStream in = source.getInputStream(); OutputStream out = new FileOutputStream(candidate)) {
                    byte[] buffer = new byte[65536];
                    long total = 0;
                    int previous = -1;
                    for (int n; (n = in.read(buffer)) != -1;) {
                        ensureOpen();
                        total += n;
                        if (total > bytes) throw new IOException("The update is larger than expected.");
                        sha.update(buffer, 0, n);
                        out.write(buffer, 0, n);
                        int percent = (int) (total * 100 / bytes);
                        if (percent != previous) {
                            previous = percent;
                            runOnUiThread(() -> { progress.setIndeterminate(false); progress.setProgress(percent); });
                        }
                    }
                    if (total != bytes || !hash.equals(hex(sha.digest()))) throw new IOException("The download failed its integrity check.");
                }
                PackageInfo current = installed();
                PackageInfo next = getPackageManager().getPackageArchiveInfo(candidate.getPath(), PackageManager.GET_SIGNING_CERTIFICATES);
                if (next == null || !current.packageName.equals(next.packageName) || !version.equals(next.versionName) ||
                        next.getLongVersionCode() != code || !EdisonRelease.newer(code, current.getLongVersionCode()) ||
                        !signerHash(current).equals(signerHash(next))) throw new IOException("The APK does not match this Edison installation.");
                ensureOpen();
                show("Edison " + version + " is verified and ready to install.", "Install update", () -> install(bytes));
            } catch (Exception e) {
                discard();
                show("Download failed. " + (e.getMessage() == null ? "Try again." : e.getMessage()), "Check again", this::checkRelease);
            } finally {
                if (source != null) source.disconnect();
                connection = null;
            }
        });
    }

    private void install(long size) {
        if (!getPackageManager().canRequestPackageInstalls()) {
            Intent permission = new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + getPackageName()));
            try { startActivity(permission); }
            catch (RuntimeException e) { show("Allow this app to install updates in Android Settings.", "Retry install", () -> install(size)); return; }
            show("Turn on Allow from this source, then return and tap Install update.", "Install update", () -> install(size));
            return;
        }
        show("Preparing the Android installation…", null, null);
        worker.execute(() -> {
            PackageInstaller installer = getPackageManager().getPackageInstaller();
            int sessionId = -1;
            try {
                ensureOpen();
                PackageInstaller.SessionParams params = new PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL);
                params.setAppPackageName(getPackageName());
                params.setSize(size);
                if (Build.VERSION.SDK_INT >= 31) params.setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_REQUIRED);
                sessionId = installer.createSession(params);
                try (PackageInstaller.Session session = installer.openSession(sessionId)) {
                    try (InputStream in = new FileInputStream(candidate); OutputStream out = session.openWrite("base.apk", 0, size)) {
                        byte[] buffer = new byte[65536];
                        for (int n; (n = in.read(buffer)) != -1;) { ensureOpen(); out.write(buffer, 0, n); }
                        session.fsync(out);
                    }
                    ensureOpen();
                    Intent result = new Intent(this, EdisonUpdateActivity.class).setAction(INSTALL_RESULT)
                            .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
                    ActivityOptions options = ActivityOptions.makeBasic();
                    if (Build.VERSION.SDK_INT >= 35)
                        options.setPendingIntentCreatorBackgroundActivityStartMode(ActivityOptions.MODE_BACKGROUND_ACTIVITY_START_ALLOWED);
                    PendingIntent pending = PendingIntent.getActivity(this, sessionId, result,
                            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_MUTABLE, options.toBundle());
                    committing = true;
                    session.commit(pending.getIntentSender());
                }
            } catch (Exception e) {
                committing = false;
                if (sessionId != -1) try { installer.abandonSession(sessionId); } catch (RuntimeException ignored) {}
                show("Android could not prepare the installation.", "Check again", this::checkRelease);
            } finally { discard(); }
        });
    }

    @Override protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        if (INSTALL_RESULT.equals(intent.getAction())) handleInstallResult(intent);
    }

    private void handleInstallResult(Intent result) {
        int code = result.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE);
        if (code == PackageInstaller.STATUS_PENDING_USER_ACTION) {
            Intent confirmation = result.getParcelableExtra(Intent.EXTRA_INTENT);
            if (confirmation != null) {
                try { startActivity(confirmation); return; } catch (RuntimeException ignored) {}
            }
        }
        committing = false;
        show(code == PackageInstaller.STATUS_SUCCESS ? "Edison is updated." : "Android did not install the update.",
                "Check again", this::checkRelease);
    }

    private PackageInfo installed() throws PackageManager.NameNotFoundException {
        return getPackageManager().getPackageInfo(getPackageName(), PackageManager.GET_SIGNING_CERTIFICATES);
    }

    private static String signerHash(PackageInfo info) throws Exception {
        Signature[] signers = info.signingInfo == null ? null : info.signingInfo.getApkContentsSigners();
        if (signers == null || signers.length != 1) throw new IOException("Could not verify the Edison signer.");
        return hex(MessageDigest.getInstance("SHA-256").digest(signers[0].toByteArray()));
    }

    private static String hex(byte[] bytes) {
        StringBuilder hex = new StringBuilder(bytes.length * 2);
        for (byte b : bytes) hex.append(String.format(Locale.ROOT, "%02x", b & 0xff));
        return hex.toString();
    }

    private void ensureOpen() throws IOException {
        if (closed || Thread.currentThread().isInterrupted()) throw new IOException("Update cancelled.");
    }

    private void discard() {
        File file = candidate;
        candidate = null;
        if (file != null) file.delete();
    }

    @Override public void onBackPressed() {
        if (!committing) super.onBackPressed();
    }

    @Override protected void onDestroy() {
        closed = true;
        if (connection != null) connection.disconnect();
        worker.shutdownNow();
        discard();
        super.onDestroy();
    }
}
