from importlib.metadata import PackageNotFoundError, version

APP_VERSION = "0.1.1"
PACKAGE_VERSION_NAMES = ("agentlens", "AgentLens-backend", "agentlens-backend")


def get_app_version() -> str:
    for package_name in PACKAGE_VERSION_NAMES:
        try:
            return version(package_name)
        except PackageNotFoundError:
            continue
    return APP_VERSION
