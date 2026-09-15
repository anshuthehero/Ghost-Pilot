"""
Packaging and Cross-Platform Distribution Readiness Tests.
Verifies bundle layout, dynamic binary discovery, and absence of hardcoded developer paths.
"""

import os
import sys
import pytest
from pathlib import Path
from client.core.ffmpeg import find_ffmpeg, get_ffmpeg_bin
from client.core.config import get_resource_path


def test_ffmpeg_discovery_contract():
    """Validates find_ffmpeg returns compliant schema and resolves valid binary."""
    res = find_ffmpeg()
    assert "status" in res
    assert res["status"] in ("READY", "MISSING")
    assert "path" in res
    assert "is_bundled" in res
    
    bin_path = get_ffmpeg_bin()
    assert isinstance(bin_path, str)
    assert len(bin_path) > 0


def test_no_hardcoded_homebrew_in_app_source():
    """Guarantees app.py does not hardcode /opt/homebrew/bin/ffmpeg."""
    repo_root = Path(__file__).resolve().parent.parent
    app_py = repo_root / "app.py"
    content = app_py.read_text()
    assert "/opt/homebrew/bin/ffmpeg" not in content, "Found hardcoded Homebrew FFmpeg path in app.py"


def test_resource_path_resolution():
    """Tests cross-platform asset path resolution across run modes."""
    # Should resolve valid path without throwing
    res_path = get_resource_path("client/core/config.py")
    assert os.path.exists(res_path)


def test_packaging_blueprints_exist():
    """Ensures macOS and Windows packaging blueprints remain intact."""
    repo_root = Path(__file__).resolve().parent.parent
    assert (repo_root / "packaging" / "macos" / "build_app.sh").exists()
    assert (repo_root / "packaging" / "macos" / "bundle_dependencies.py").exists()
    assert (repo_root / "packaging" / "windows" / "ghost_copilot.spec").exists()
    assert (repo_root / "packaging" / "windows" / "installer.iss").exists()
