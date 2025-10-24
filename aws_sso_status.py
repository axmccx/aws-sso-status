#!/usr/bin/env python3
import os, json, subprocess, datetime, shutil, configparser
import rumps
from AppKit import NSApplication, NSApplicationActivationPolicyProhibited
from pathlib import Path
import zoneinfo

# Hide Dock icon:
NSApplication.sharedApplication().setActivationPolicy_(
    NSApplicationActivationPolicyProhibited
)


CACHE_DIR = Path("~/.aws/sso/cache").expanduser()
ACTIVE_PROFILE_FILE = Path("~/.aws/sso/active_profile").expanduser()
EXPIRY_WARNING_MINUTES = 10
CHECK_INTERVAL_SECONDS = 60
# Automatically detect local timezone from system
LOCAL_TZ = datetime.datetime.now().astimezone().tzinfo

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


def discover_sso_profiles():
    """Parse ~/.aws/config and return list of SSO-enabled profile names."""
    config_path = Path("~/.aws/config").expanduser()
    if not config_path.exists():
        return ["default"]

    try:
        config = configparser.ConfigParser()
        config.read(config_path)

        profiles = []
        for section in config.sections():
            # Section names are like "profile myprofile" or "default"
            if section == "default":
                profile_name = "default"
            elif section.startswith("profile "):
                profile_name = section[8:]  # Remove "profile " prefix
            else:
                continue

            # Check if profile has SSO configuration
            if config.has_option(section, "sso_start_url") or config.has_option(
                section, "sso_session"
            ):
                profiles.append(profile_name)

        return profiles if profiles else ["default"]
    except Exception:
        return ["default"]


def load_active_profile():
    """Load the active profile from persistent storage."""
    if ACTIVE_PROFILE_FILE.exists():
        try:
            return ACTIVE_PROFILE_FILE.read_text().strip()
        except Exception:
            pass
    return "default"


def save_active_profile(profile_name):
    """Save the active profile to persistent storage."""
    try:
        ACTIVE_PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)
        ACTIVE_PROFILE_FILE.write_text(profile_name)
    except Exception:
        pass


def find_latest_sso_cache():
    files = list(CACHE_DIR.glob("*.json"))
    if not files:
        return None
    return max(files, key=lambda f: f.stat().st_mtime)


def read_expiry_from_cache(profile=None):
    """Read expiry timestamp from ~/.aws/cli/cache for given profile."""
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


def is_logged_in(profile=None):
    """Check if the given profile has valid AWS credentials."""
    if not AWS_CLI:
        return False
    try:
        cmd = [AWS_CLI, "sts", "get-caller-identity"]
        if profile and profile != "default":
            cmd.extend(["--profile", profile])
        subprocess.run(cmd, capture_output=True, check=True)
        return True
    except subprocess.CalledProcessError:
        return False


class AWSSSOStatusApp(rumps.App):
    def __init__(self):
        super().__init__("✕", icon=None, quit_button=None)

        # Profile management
        self.profiles = discover_sso_profiles()
        self.active_profile = load_active_profile()

        # Dynamic header label
        self.header_item = rumps.MenuItem(
            "AWS SSO not logged in", callback=lambda _: None
        )

        # Menu items
        self.expires_item = rumps.MenuItem("Expires at: —", callback=lambda _: None)
        self.timeleft_item = rumps.MenuItem("Time left: —", callback=lambda _: None)

        # Create refresh submenu with profile options
        self.refresh_item = rumps.MenuItem("Refresh profile...")
        for profile in self.profiles:
            profile_item = rumps.MenuItem(
                profile, callback=lambda sender: self.refresh_profile(sender.title)
            )
            self.refresh_item.add(profile_item)

        self.quit_item = rumps.MenuItem("Quit")

        # Bind callbacks
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

    def refresh_profile(self, profile):
        """Trigger aws sso login for profile and temporarily increase update frequency."""
        if not AWS_CLI:
            rumps.alert("AWS SSO Status", "AWS CLI not found. Cannot refresh login.")
            return

        # Set this profile as the active one
        self.active_profile = profile
        save_active_profile(profile)

        self.fast_mode = True
        self.timer.stop()
        self.timer.interval = self.fast_interval
        self.timer.start()

        # Build command with profile argument
        cmd = [AWS_CLI, "sso", "login"]
        if profile and profile != "default":
            cmd.extend(["--profile", profile])

        subprocess.Popen(cmd)
        rumps.notification(
            "AWS SSO", f"Logging in to {profile}…", "Waiting for new credentials..."
        )

    def quit_app(self, _):
        rumps.quit_application()

    def update_status(self, _):
        now = datetime.datetime.now(LOCAL_TZ)
        expiry = read_expiry_from_cache(self.active_profile)
        logged_in = is_logged_in(self.active_profile)

        # Update header based on login status
        if logged_in and expiry:
            self.header_item.title = f"AWS SSO profile: {self.active_profile}"
        else:
            self.header_item.title = "AWS SSO not logged in"

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

        # If in fast mode, and we've confirmed a valid login → go back to slow cadence
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
