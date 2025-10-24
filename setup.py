from setuptools import setup

APP = ["aws_sso_status.py"]
OPTIONS = {
    "argv_emulation": False,
    "includes": ["imp", "jaraco.text"],
    "packages": ["rumps", "zoneinfo"],
    "plist": {
        "LSUIElement": True,
        "CFBundleName": "AWS SSO Status",
        "CFBundleIdentifier": "io.github.axmccx.aws-sso-status",
        "CFBundleShortVersionString": "1.0.0",
    },
}

setup(
    app=APP,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
