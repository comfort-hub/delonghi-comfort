"""Tests for device / status / capabilities parsing."""

from __future__ import annotations

from delonghi_comfort.models import Device, MachineCapabilities, MachineStatus

_DEVICE = {
    "machineName": "EUPDL01COM000000004875",
    "serialNumber": "90:70:69:90:93:74",
    "sku": "0110070300",
    "machineModel": "TRD5WIFI",
    "status": "ONLINE",
}

_REPORTED = {
    "DeviceStatus": 1,
    "TempSetPoint": 27,
    "RoomTemp": 200,
    "PowerLimit": True,
    "KeyLock": False,
    "NightModeEnable": False,
    "SilentEnable": True,
    "BrightnessLevel": 2,
    "TempUnit": True,
    "LanIpAddress": "192.168.1.250",
    "alarms": {"TOS_alarm": False, "HTMAX_alarmPowerBoard": False},
}


def test_device_from_dict() -> None:
    """Device fields map from the ownedByMe entry."""
    device = Device.from_dict(_DEVICE)
    assert device.thing_name == "EUPDL01COM000000004875"
    assert device.serial_number == "90:70:69:90:93:74"
    assert device.model == "TRD5WIFI"
    assert device.online is True


def test_status_scaling_and_flags() -> None:
    """RoomTemp is scaled by 10, setpoint is whole degrees, flags are bools."""
    status = MachineStatus.from_reported(_REPORTED)
    assert status.is_on is True
    assert status.target_temperature == 27
    assert status.current_temperature == 20.0
    assert status.eco is True
    assert status.child_lock is False
    assert status.silent is True
    assert status.brightness == 2
    assert status.celsius is True
    assert status.lan_ip == "192.168.1.250"
    assert status.any_alarm is False


def test_status_off_and_missing_fields() -> None:
    """Missing fields yield None / False rather than raising."""
    status = MachineStatus.from_reported({"DeviceStatus": 0})
    assert status.is_on is False
    assert status.target_temperature is None
    assert status.current_temperature is None
    assert status.brightness is None
    assert status.alarms == {}


def test_capabilities() -> None:
    """Capabilities map from the MachineCapabilities shadow."""
    caps = MachineCapabilities.from_reported(
        {
            "MAC": "90:70:69:90:93:74",
            "SN": "90:70:69:90:93:74",
            "MachineModel": "TRD5WIFI",
            "SKU": "0110070300",
            "FWWiFiVersion": "2.1.4",
            "DLAWS_Version": "1.0.9",
        }
    )
    assert caps.mac == "90:70:69:90:93:74"
    assert caps.wifi_firmware == "2.1.4"
    assert caps.aws_version == "1.0.9"
