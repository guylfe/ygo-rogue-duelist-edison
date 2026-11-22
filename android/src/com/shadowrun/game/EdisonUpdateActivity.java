package com.shadowrun.game;

import android.app.Activity;
import android.app.ActivityOptions;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageInstaller;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.view.Gravity;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.security.MessageDigest;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import javax.net.ssl.HttpsURLConnection;

/** Checks the fork's stable channel. A download and the Android install both require player action. */
public final class EdisonUpdateActivity extends Activity {
    private static final String INSTALL_RESULT = EdisonRelease.PACKAGE + ".UPDATE_RESULT";
    private static final String STARTUP_DOWNLOAD = EdisonRelease.PACKAGE + ".STARTUP_DOWNLOAD";
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private final EdisonUpdateClient updates = new EdisonUpdateClient();
    private volatile boolean closed;
    private volatile boolean committing;
    private volatile File candidate;
    private TextView status;
    private ProgressBar progress;
    private Button primary;

    static Intent downloadIntent(Context context, EdisonRelease.Update update) {
        return new Intent(context, EdisonUpdateActivity.class).setAction(STARTUP_DOWNLOAD)
                .putExtra("version", update.version).putExtra("versionCode", update.versionCode)
                .putExtra("bytes", update.bytes).putExtra("sha256", update.sha256).putExtra("url", update.url);
    }

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
        Intent intent = getIntent();
        if (INSTALL_RESULT.equals(intent.getAction())) handleInstallResult(intent);
        else if (state == null && STARTUP_DOWNLOAD.equals(intent.getAction())) {
            download(new EdisonRelease.Update(intent.getStringExtra("version"), intent.getLongExtra("versionCode", 0),
                    intent.getLongExtra("bytes", 0), intent.getStringExtra("sha256"), intent.getStringExtra("url")));
        } else checkRelease();
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
                EdisonRelease.Update update = updates.check(installed, false);
                if (update == null) {
                    show("You’re up to date. Installed version: " + installed.versionName, "Check again", this::checkRelease);
                    return;
                }
                show(String.format(Locale.ROOT, "Edison %s is available (%.0f MB).", update.version, update.bytes / 1000000.0),
                        "Download update", () -> download(update));
            } catch (Exception e) {
                show("Could not check for Edison updates. Check your connection and try again.", "Retry", this::checkRelease);
            }
        });
    }

    private void download(EdisonRelease.Update update) {
        String version = update.version;
        long bytes = update.bytes;
        show("Downloading Edison " + version + "…", null, null);
        worker.execute(() -> {
            try {
                if (getCacheDir().getUsableSpace() < bytes * 2 + 32L * 1024 * 1024)
                    throw new IOException("Free some space before downloading the update.");
                candidate = File.createTempFile("edison-update-", ".apk", getCacheDir());
                HttpsURLConnection source = updates.openDownload(update.url);
                MessageDigest sha = MessageDigest.getInstance("SHA-256");
                try (InputStream in = source.getInputStream(); OutputStream out = new FileOutputStream(candidate)) {
                    byte[] buffer = new byte[65536];
                    long total = 0;
                    int previous = -1;
                    for (int n; (n = in.read(buffer)) != -1;) {
                        updates.ensureOpen();
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
                    if (total != bytes || !update.sha256.equals(EdisonUpdateClient.hex(sha.digest())))
                        throw new IOException("The download failed its integrity check.");
                }
                PackageInfo current = installed();
                PackageInfo next = getPackageManager().getPackageArchiveInfo(candidate.getPath(), PackageManager.GET_SIGNING_CERTIFICATES);
                if (next == null || !current.packageName.equals(next.packageName) || !version.equals(next.versionName) ||
                        next.getLongVersionCode() != update.versionCode ||
                        !EdisonRelease.newer(update.versionCode, current.getLongVersionCode()) ||
                        next.applicationInfo.minSdkVersion > Build.VERSION.SDK_INT ||
                        !EdisonUpdateClient.signerHash(current).equals(EdisonUpdateClient.signerHash(next)))
                    throw new IOException("The APK does not match this Edison installation.");
                updates.ensureOpen();
                show("Edison " + version + " is verified and ready to install.", "Install update", () -> install(bytes));
            } catch (Exception e) {
                discard();
                show("Download failed. " + (e.getMessage() == null ? "Try again." : e.getMessage()), "Check again", this::checkRelease);
            } finally {
                updates.disconnect();
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
                updates.ensureOpen();
                PackageInstaller.SessionParams params = new PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL);
                params.setAppPackageName(getPackageName());
                params.setSize(size);
                if (Build.VERSION.SDK_INT >= 31) params.setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_REQUIRED);
                sessionId = installer.createSession(params);
                try (PackageInstaller.Session session = installer.openSession(sessionId)) {
                    try (InputStream in = new FileInputStream(candidate); OutputStream out = session.openWrite("base.apk", 0, size)) {
                        byte[] buffer = new byte[65536];
                        for (int n; (n = in.read(buffer)) != -1;) { updates.ensureOpen(); out.write(buffer, 0, n); }
                        session.fsync(out);
                    }
                    updates.ensureOpen();
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
        updates.cancel();
        updates.disconnect();
        worker.shutdownNow();
        discard();
        super.onDestroy();
    }
}
