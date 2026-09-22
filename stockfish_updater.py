"""
Stockfish auto-updater - ensures latest version is installed
Uses the same method as Dockerfile for consistency
"""

import os
import sys
import platform
import subprocess
import tempfile
import shutil
import logging
import json
from urllib.request import urlopen, Request
from urllib.parse import urlparse
from typing import Optional

logger = logging.getLogger(__name__)

INSTALL_PATH = "/usr/local/bin/stockfish"
GITHUB_API = "https://api.github.com/repos/official-stockfish/Stockfish/releases/latest"

# Releases are only ever fetched from the project's own GitHub download hosts.
# The URL comes out of an API response, so it is checked before anything is
# downloaded and made executable.
ALLOWED_DOWNLOAD_HOSTS = ("github.com", "objects.githubusercontent.com")

# Archive extension used by the release assets.
ARCHIVE_SUFFIX = ".tar.gz"


def get_binary_name() -> str:
    """Determine the correct Stockfish binary name for this platform.

    Stockfish 19 dropped the per-microarchitecture assets and publishes one
    universal build per platform. A universal binary selects its code path
    (AVX2, AVX-512, ...) from the CPU at runtime, so it is both the only
    option and the fast one — the old ``stockfish-ubuntu-x86-64`` asset was
    the generic SSE2 build.
    """
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "linux":
        if machine in ("x86_64", "amd64"):
            return "stockfish-linux-x86-64-universal"
        elif machine in ("aarch64", "arm64"):
            return "stockfish-linux-arm64-universal"
        elif machine in ("riscv64",):
            return "stockfish-linux-riscv64-universal"
        else:
            raise RuntimeError(f"Unsupported Linux architecture: {machine}")
    elif system == "darwin":
        # One universal build covers both Intel and Apple Silicon.
        return "stockfish-macos-universal"
    else:
        raise RuntimeError(f"Unsupported OS: {system}")


def log_build_info(path: str = INSTALL_PATH) -> Optional[str]:
    """Log which code path the installed binary compiled for.

    A universal binary only uses what the CPU exposes, and a VM with a generic
    CPU model hides AVX2. Recording the line makes a slow build obvious in the
    logs instead of silently costing search speed.
    """
    try:
        result = subprocess.run(
            [path, "compiler"], capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.splitlines():
            if line.startswith("Compilation settings"):
                settings = line.split(":", 1)[1].strip()
                logger.info(f"Stockfish build: {settings}")
                return settings
    except Exception as e:
        logger.debug(f"Could not read Stockfish build info: {e}")
    return None


def get_installed_version() -> Optional[str]:
    """Get currently installed Stockfish version."""
    if not os.path.isfile(INSTALL_PATH):
        return None
    
    try:
        # Try different methods to get version
        result = subprocess.run(
            [INSTALL_PATH, "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0 and result.stdout:
            # Extract version from output like "Stockfish 18"
            first_line = result.stdout.strip().split('\n')[0]
            if "Stockfish" in first_line:
                parts = first_line.split()
                for i, part in enumerate(parts):
                    if part == "Stockfish" and i + 1 < len(parts):
                        return parts[i + 1]
        
        # Fallback: try compiler info
        result = subprocess.run(
            [INSTALL_PATH, "compiler"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            return "unknown"
            
    except Exception as e:
        logger.debug(f"Could not get Stockfish version: {e}")
    
    return None


def get_latest_release_info() -> dict:
    """Fetch latest release info from GitHub API."""
    try:
        req = Request(GITHUB_API)
        req.add_header("Accept", "application/vnd.github.v3+json")
        
        with urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            return data
    except Exception as e:
        logger.error(f"Failed to fetch latest release info: {e}")
        raise


def _check_download_url(url: str) -> str:
    """Reject a download URL that does not point at a GitHub release host."""
    host = urlparse(url).hostname or ""
    if host not in ALLOWED_DOWNLOAD_HOSTS:
        raise RuntimeError(f"Refusing to download Stockfish from unexpected host: {host}")
    return url


def get_download_url(binary_name: str) -> str:
    """Get download URL for the specified binary from latest release."""
    release_info = get_latest_release_info()
    archive_name = f"{binary_name}{ARCHIVE_SUFFIX}"

    for asset in release_info.get("assets", []):
        if asset["name"] == archive_name:
            return _check_download_url(asset["browser_download_url"])

    raise RuntimeError(
        f"Binary {archive_name} not found in latest release. "
        f"Available: {[a['name'] for a in release_info.get('assets', [])]}"
    )


def download_and_install(url: str, binary_name: str) -> None:
    """Download and install Stockfish."""
    logger.info(f"Downloading Stockfish from {url}")
    
    _check_download_url(url)

    with tempfile.TemporaryDirectory() as tmpdir:
        tar_path = os.path.join(tmpdir, "stockfish" + ARCHIVE_SUFFIX)

        # Download
        with urlopen(url, timeout=300) as response:
            with open(tar_path, 'wb') as f:
                shutil.copyfileobj(response, f)

        logger.info("Extracting archive...")

        # Release assets are gzip-compressed since Stockfish 19.
        subprocess.run(
            ["tar", "-xzf", tar_path, "-C", tmpdir],
            check=True,
            capture_output=True
        )

        # Locate the binary by search. The archive nests it under a directory
        # whose layout has changed between releases, so nothing here assumes a
        # fixed path — only the file name, which is the asset name.
        extracted_binary = None
        for root, dirs, files in os.walk(tmpdir):
            if binary_name in files:
                extracted_binary = os.path.join(root, binary_name)
                break

        if not extracted_binary:
            raise RuntimeError(
                f"Could not find {binary_name} in the extracted archive. "
                f"The release layout may have changed."
            )
        
        logger.info(f"Installing to {INSTALL_PATH}")
        
        # Install
        try:
            # Try to move with sudo if we don't have permissions
            shutil.copy(extracted_binary, INSTALL_PATH)
            os.chmod(INSTALL_PATH, 0o755)
        except PermissionError:
            # Need sudo
            logger.info("Requesting sudo privileges for installation...")
            subprocess.run(
                ["sudo", "cp", extracted_binary, INSTALL_PATH],
                check=True
            )
            subprocess.run(
                ["sudo", "chmod", "755", INSTALL_PATH],
                check=True
            )
        
        logger.info("Stockfish installed successfully!")


def ensure_stockfish_installed(auto_update: bool = True) -> str:
    """
    Ensure Stockfish is installed and optionally update to latest version.
    Returns the path to Stockfish binary.
    """
    binary_name = get_binary_name()
    
    # Check if already installed
    current_version = get_installed_version()
    
    if current_version:
        logger.info(f"Stockfish {current_version} found at {INSTALL_PATH}")
        
        if not auto_update:
            return INSTALL_PATH
        
        # Check for updates
        try:
            logger.info("Checking for Stockfish updates...")
            release_info = get_latest_release_info()
            latest_tag = release_info.get("tag_name", "").replace("sf_", "")
            
            if current_version == "unknown" or current_version != latest_tag:
                logger.info(f"New version available: {latest_tag}")
                download_url = get_download_url(binary_name)
                download_and_install(download_url, binary_name)
                logger.info(f"Updated to Stockfish {latest_tag}")
            else:
                logger.info("Stockfish is up to date")
        except Exception as e:
            logger.warning(f"Update check failed, using existing version: {e}")
    else:
        # Not installed, install it
        logger.info("Stockfish not found, installing...")
        download_url = get_download_url(binary_name)
        download_and_install(download_url, binary_name)
    
    # Verify installation
    if not os.path.isfile(INSTALL_PATH):
        raise RuntimeError("Stockfish installation failed")

    log_build_info(INSTALL_PATH)

    return INSTALL_PATH


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        path = ensure_stockfish_installed(auto_update=True)
        print(f"Stockfish ready at: {path}")
        
        # Quick test
        subprocess.run(
            [path, "bench", "1"],
            capture_output=True,
            text=True,
            timeout=30
        )
        print("Stockfish test successful!")
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
