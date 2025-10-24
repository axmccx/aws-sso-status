#!/usr/bin/env python3
import os, json, subprocess, datetime, shutil
import rumps
from AppKit import NSApplication, NSApplicationActivationPolicyProhibited
from pathlib import Path
import zoneinfo

# Hide Dock icon:
NSApplication.sharedApplication().setActivationPolicy_(
    NSApplicationActivationPolicyProhibited
)


CACHE_DIR = Path("~/.aws/sso/cache").expanduser()
EXPIRY_WARNING_MINUTES = 10
CHECK_INTERVAL_SECONDS = 60
LOCAL_TZ = zoneinfo.ZoneInfo("America/Toronto")

# Try to locate AWS CLI binary
AWS_CLI = shutil.which("aws") or "/usr/local/bin/aws"  # fallback
if not os.path.exists(AWS_CLI):
    # Handle when AWS CLI not found at all
    rumps.alert(
        "AWS SSO Status",
        "Could not find AWS CLI on your system.\n\n"
        "Please install it via Homebrew or pipx and restart the app.",
    )
    AWS_CLI = None


def find_latest_sso_cache():
    files = list(CACHE_DIR.glob("*.json"))
    if not files:
        return None
    return max(files, key=lambda f: f.stat().st_mtime)


def read_expiry_from_cache():
    """Read expiry timestamp from ~/.aws/cli/cache."""
    cli_cache = Path("~/.aws/cli/cache").expanduser()
    files = list(cli_cache.glob("*.json"))
    if not files:
        return None
    latest = max(files, key=lambda f: f.stat().st_mtime)
    try:
        with open(latest) as f:
            data = json.load(f)
        exp = data.get("Credentials", {}).get("Expiration")
        if not exp:
            return None
        utc_dt = datetime.datetime.strptime(exp, "%Y-%m-%dT%H:%M:%SZ")
        utc_dt = utc_dt.replace(tzinfo=datetime.timezone.utc)
        return utc_dt.astimezone(LOCAL_TZ)
    except Exception:
        return None


def is_logged_in():
    if not AWS_CLI:
        return False
    try:
        subprocess.run(
            [AWS_CLI, "sts", "get-caller-identity"],
            capture_output=True,
            check=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


class AWSSSOStatusApp(rumps.App):
    def __init__(self):
        super().__init__("✕", icon=None, quit_button=None)

        # Static header label
        self.header_item = rumps.MenuItem("AWS SSO Login", callback=lambda _: None)

        # Menu items
        self.expires_item = rumps.MenuItem("Expires at: —", callback=lambda _: None)
        self.timeleft_item = rumps.MenuItem("Time left: —", callback=lambda _: None)
        self.refresh_item = rumps.MenuItem("Refresh now")
        self.quit_item = rumps.MenuItem("Quit")

        # Bind callbacks
        self.refresh_item.set_callback(self.refresh_now)
        self.quit_item.set_callback(self.quit_app)

        # Build menu
        self.menu = [
            self.header_item,
            self.expires_item,
            self.timeleft_item,
            None,
            self.refresh_item,
            self.quit_item,
        ]
        # Timer setup
        self.normal_interval = CHECK_INTERVAL_SECONDS
        self.fast_interval = 1
        self.fast_mode = False

        self.timer = rumps.Timer(self.update_status, self.normal_interval)
        self.timer.start()

        # Initial update
        self.update_status(None)

    def refresh_now(self, _):
        """Trigger aws sso login and temporarily increase update frequency."""
        if not AWS_CLI:
            rumps.alert("AWS SSO Status", "AWS CLI not found. Cannot refresh login.")
            return

        self.fast_mode = True
        self.timer.stop()
        self.timer.interval = self.fast_interval
        self.timer.start()

        subprocess.Popen([AWS_CLI, "sso", "login"])
        rumps.notification("AWS SSO", "Logging in…", "Waiting for new credentials...")

    def quit_app(self, _):
        rumps.quit_application()

    def update_status(self, _):
        now = datetime.datetime.now(LOCAL_TZ)
        expiry = read_expiry_from_cache()
        logged_in = is_logged_in()

        if not expiry:
            self.title = "✕"
            self.expires_item.title = "Expires at: —"
            self.timeleft_item.title = "Time left: —"
            return

        delta = expiry - now
        total_minutes = int(delta.total_seconds() / 60)
        hours = total_minutes // 60
        minutes = total_minutes % 60
        warning = total_minutes < 60

        # Choose icon
        if total_minutes <= 0 or not logged_in:
            icon = "✕"
        elif warning:
            icon = "⚠"
        else:
            icon = "✓"

        self.title = icon

        # Format display
        expiry_date = expiry.date()
        now_date = now.date()

        if expiry_date == now_date:
            expiry_str = expiry.strftime("today at %-I:%M%p")
        elif expiry_date == now_date + datetime.timedelta(days=1):
            expiry_str = expiry.strftime("tomorrow at %-I:%M%p")
        else:
            expiry_str = expiry.strftime("%b %-d at %-I:%M%p")

        if hours > 0:
            timeleft_str = f"{hours}h {minutes:02d}m"
        else:
            timeleft_str = f"{minutes}m"

        self.expires_item.title = f"Expires {expiry_str}"
        self.timeleft_item.title = f"Time left: {timeleft_str}"

        # If in fast mode, and we’ve confirmed a valid login → go back to slow cadence
        if self.fast_mode and logged_in:
            self.fast_mode = False
            self.timer.stop()
            self.timer.interval = self.normal_interval
            self.timer.start()
            rumps.notification(
                "AWS SSO", "Login confirmed", "Session refreshed successfully."
            )


if __name__ == "__main__":
    AWSSSOStatusApp().run()
