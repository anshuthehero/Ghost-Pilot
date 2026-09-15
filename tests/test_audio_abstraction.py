"""
Tests for Cross-Platform Audio Provider Abstraction.
Validates macOS and Windows audio providers, device discovery, and fallback behaviors.
"""

import pytest
from client.audio.base import BaseAudioProvider, AudioState
from client.audio.manager import get_audio_provider
from client.platform.macos.audio import MacAudioProvider
from client.platform.windows.audio import WindowsAudioProvider


def test_audio_manager_returns_base_audio_provider():
    provider = get_audio_provider()
    assert isinstance(provider, BaseAudioProvider)


def test_macos_audio_provider_interface():
    provider = MacAudioProvider()
    assert isinstance(provider, BaseAudioProvider)

    caps = provider.check_capabilities()
    assert caps["platform"] == "macos"
    assert "microphone" in caps
    assert "system_audio" in caps
    assert "state" in caps["microphone"]
    assert "state" in caps["system_audio"]
    # Check that state is a valid AudioState enum value
    assert caps["microphone"]["state"] in [s.value for s in AudioState]
    assert caps["system_audio"]["state"] in [s.value for s in AudioState]


def test_windows_audio_provider_interface():
    provider = WindowsAudioProvider()
    assert isinstance(provider, BaseAudioProvider)

    caps = provider.check_capabilities()
    assert caps["platform"] == "windows"
    assert caps["audio_backend"] == "WASAPI"
    assert "microphone" in caps
    assert "system_audio" in caps
    assert "no virtual cable required" in caps["system_audio"]["backend"].lower()


def test_macos_graceful_degradation_on_missing_blackhole():
    from unittest.mock import patch
    provider = MacAudioProvider()
    mock_devs = {
        "mic_detected": True,
        "mic_index": "1",
        "blackhole_detected": False,
        "blackhole_index": None,
        "all_devices": [{"index": "1", "name": "Built-in Microphone"}]
    }
    with patch.object(provider, "detect_devices", return_value=mock_devs):
        caps = provider.check_capabilities()
        assert caps["system_audio"]["state"] == AudioState.MISSING.value
        # Microphone remains operational even when BlackHole is absent
        assert caps["microphone"]["state"] == AudioState.READY.value
        assert caps["system_audio"]["graceful_fallback"] == "Microphone-Only mode active"
