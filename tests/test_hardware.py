import csv
import json
import os
import socket
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from expecto_process_manager.core import hardware
from expecto_process_manager.core.cancellation import Cancellation, Cancelled


@pytest.fixture
def portable(monkeypatch):
    """No real CIM, disk, network or sensor work during unit tests."""
    monkeypatch.setattr(hardware, "_cache", None)
    monkeypatch.setattr(hardware.platform, "system", lambda: "Windows")
    monkeypatch.setattr(hardware, "_query_windows_cim", lambda: ({}, []))
    monkeypatch.setattr(hardware, "_registry_cpu", lambda: "CPU do registo")
    monkeypatch.setattr(hardware, "_registry_windows_components", lambda: {})
    monkeypatch.setattr(hardware.psutil, "boot_time", lambda: 1_700_000_000)
    monkeypatch.setattr(hardware.psutil, "cpu_count", lambda logical=True: 16 if logical else 8)
    monkeypatch.setattr(hardware.psutil, "cpu_freq", lambda: SimpleNamespace(current=3200, max=5000))
    monkeypatch.setattr(hardware.psutil, "virtual_memory", lambda: SimpleNamespace(total=32 * 1024**3))
    monkeypatch.setattr(hardware.psutil, "swap_memory", lambda: SimpleNamespace(total=0))
    monkeypatch.setattr(hardware.psutil, "disk_partitions", lambda all=False: [])
    monkeypatch.setattr(hardware.psutil, "net_if_stats", lambda: {})
    monkeypatch.setattr(hardware.psutil, "net_if_addrs", lambda: {})
    monkeypatch.setattr(hardware.psutil, "sensors_battery", lambda: None)
    monkeypatch.setattr(hardware.psutil, "sensors_temperatures", lambda **kwargs: {}, raising=False)


def values(inventory, category):
    return {item.name: item.value for item in inventory.items if item.category == category}


def test_partial_windows_hardware_keeps_sources_and_unknowns(portable, monkeypatch):
    query = Mock(return_value=({"cpu": {"Name": "Example CPU"},
                              "memory": [{"Capacity": 16 * 1024**3, "Manufacturer": "Maker", "ConfiguredClockSpeed": 3200}],
                              "board": [{"Manufacturer": "BoardMaker", "Product": "BoardModel"}],
                              "bios": [{"SMBIOSBIOSVersion": "1.20"}],
                              "storage": [{"FriendlyName": "Drive", "Size": 10**12, "MediaType": 4, "BusType": 17}]},
                             ["Consulta não disponível: Win32_VideoController: CimException"]))
    monkeypatch.setattr(hardware, "_query_windows_cim", query)
    result = hardware.detect_hardware()
    query.assert_called_once()
    assert values(result, "CPU")["Modelo 1"] == "Example CPU"
    assert "16.00 GiB" in values(result, "Memória")["Módulo 1 · Indisponível"]
    assert "3200 MHz (CIM)" in values(result, "Memória")["Módulo 1 · Indisponível"]
    assert "SSD · NVMe" in values(result, "Armazenamento")["Tipo · Drive"]
    assert values(result, "GPU")["Adaptadores"] == "Indisponível"
    assert all(item.source for item in result.items)
    assert any("CimException" in note for note in result.notes)
    assert result.as_dict()["items"][0]["category"] == "Sistema"
    assert result.as_dict()["cache_seconds"] == 600


@pytest.mark.parametrize("truncated_vram", [0, 2**32 - 1, 4 * 1024**3, 12 * 1024**3])
def test_adapterram_is_never_presented_as_reliable_vram(portable, monkeypatch, truncated_vram):
    monkeypatch.setattr(hardware, "_query_windows_cim", lambda: ({"gpu": [{"Name": "Large GPU", "DriverVersion": "600.1", "AdapterRAM": truncated_vram}]}, []))
    result = hardware.detect_hardware()
    gpu = values(result, "GPU")
    assert gpu["Adaptador 1"] == "Large GPU"
    assert gpu["Controlador 1"] == "600.1"
    assert "Indisponível" in gpu["Memória dedicada 1"]
    assert not any("GiB" in value for value in gpu.values())
    assert any("uint32" in note for note in result.notes)


def test_cache_does_not_requery_or_leak_mutations(portable, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(hardware.time, "monotonic", lambda: clock[0])
    query = Mock(return_value=({}, ["CIM indisponível"]))
    monkeypatch.setattr(hardware, "_query_windows_cim", query)
    first = hardware.detect_hardware()
    original_count = len(first.items)
    first.items.clear()
    first.notes.clear()
    second = hardware.detect_hardware()
    assert len(second.items) == original_count
    assert "CIM indisponível" in second.notes
    assert second.collected_at == first.collected_at
    assert query.call_count == 1
    hardware.detect_hardware(refresh=True)
    assert query.call_count == 2
    clock[0] += 601
    hardware.detect_hardware()
    assert query.call_count == 3


def test_cancellation_never_replaces_cache(portable, monkeypatch):
    token = Cancellation()
    token.cancel()
    query = Mock(return_value=({}, []))
    monkeypatch.setattr(hardware, "_query_windows_cim", query)
    with pytest.raises(Cancelled):
        hardware.detect_hardware(token)
    query.assert_not_called()
    assert hardware._cache is None
    token = Cancellation()
    monkeypatch.setattr(hardware, "_query_windows_cim", lambda: (token.cancel() or {}, []))
    with pytest.raises(Cancelled):
        hardware.detect_hardware(token)
    assert hardware._cache is None


def test_cached_accessor_never_waits_or_starts_detection(portable, monkeypatch):
    query = Mock(return_value=({}, []))
    monkeypatch.setattr(hardware, "_query_windows_cim", query)
    assert hardware.get_cached_hardware() is None
    query.assert_not_called()
    original = hardware.detect_hardware()
    query.reset_mock()
    cached = hardware.get_cached_hardware()
    assert cached.collected_at == original.collected_at
    cached.items.clear()
    assert hardware.get_cached_hardware().items
    with hardware._cache_lock:
        assert hardware.get_cached_hardware() is None
    query.assert_not_called()


def test_windows_query_is_single_batched_hidden_subprocess(monkeypatch):
    monkeypatch.setattr(hardware.shutil, "which", lambda _: "powershell.exe")
    runner = Mock(return_value=SimpleNamespace(returncode=0, stdout='\ufeff{"data":{"cpu":[{"Name":"CPU"}]},"errors":[]}'))
    monkeypatch.setattr(hardware.subprocess, "run", runner)
    data, errors = hardware._query_windows_cim()
    assert data["cpu"][0]["Name"] == "CPU" and errors == []
    args, kwargs = runner.call_args
    assert runner.call_count == 1
    assert args[0][0] == "powershell.exe"
    assert "Win32_PhysicalMemory" in args[0][-1] and "MSFT_PhysicalDisk" in args[0][-1]
    assert "SerialNumber" not in args[0][-1]
    assert "shell" not in kwargs and kwargs["timeout"] == 8
    assert kwargs["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0)


@pytest.mark.parametrize("mode", ["timeout", "invalid", "nonzero", "missing"])
def test_windows_query_fallback_does_not_fail_inventory(monkeypatch, mode):
    monkeypatch.setattr(hardware.shutil, "which", lambda _: None if mode == "missing" else "powershell.exe")
    runner = Mock()
    if mode == "timeout":
        runner.side_effect = subprocess.TimeoutExpired("powershell.exe", 8)
    else:
        runner.return_value = SimpleNamespace(returncode=1 if mode == "nonzero" else 0, stdout="not JSON")
    monkeypatch.setattr(hardware.subprocess, "run", runner)
    data, notes = hardware._query_windows_cim()
    assert data == {} and notes
    assert "8 s" in notes[0] if mode == "timeout" else "CIM" in notes[0]


def test_network_uses_nominal_speed_without_exporting_addresses(portable, monkeypatch):
    monkeypatch.setattr(hardware.psutil, "net_if_stats", lambda: {"Ethernet": SimpleNamespace(isup=True, speed=1000)})
    monkeypatch.setattr(hardware.psutil, "net_if_addrs", lambda: {"Ethernet": [SimpleNamespace(family=socket.AF_INET, address="192.0.2.5"), SimpleNamespace(family=-1, address="ab:cd:ef:01:23:45")]})
    result = hardware.detect_hardware()
    assert "1000 Mbit/s" in values(result, "Rede")["Ethernet"]
    assert "IPv4 configurado" in values(result, "Rede")["Ethernet"]
    serialized = json.dumps(result.as_dict())
    assert "192.0.2.5" not in serialized and "ab:cd:ef" not in serialized


def test_registry_fallback_labels_gpu_configuration_without_inventing_presence(portable, monkeypatch):
    monkeypatch.setattr(hardware, "_registry_windows_components", lambda: {
        "gpu": [{"Name": "Example configured GPU", "DriverVersion": "1.2"}],
        "board": {"Manufacturer": "Example", "Product": "Board"},
        "bios": {"Manufacturer": "Example", "SMBIOSBIOSVersion": "2.0", "ReleaseDate": "2025-01-01"},
    })
    result = hardware.detect_hardware()
    assert values(result, "GPU")["Adaptador configurado 1"] == "Example configured GPU"
    assert values(result, "GPU")["Memória dedicada 1"] == "Indisponível"
    assert values(result, "Placa principal")["Fabricante / modelo"] == "Example · Board"
    assert any("não confirmam atividade ou presença" in note for note in result.notes)
    assert any("Registo Windows" in item.source for item in result.items if item.category == "Firmware")


def test_skip_network_and_removable_volume_capacity(portable, monkeypatch):
    monkeypatch.setattr(hardware.psutil, "disk_partitions", lambda all=False: [
        SimpleNamespace(device="\\\\server\\share", mountpoint="Z:\\", fstype="NTFS", opts="rw"),
        SimpleNamespace(device="D:\\", mountpoint="D:\\", fstype="", opts="cdrom"),
        SimpleNamespace(device="C:\\", mountpoint="C:\\", fstype="NTFS", opts="rw,fixed"),
    ])
    usage = Mock(return_value=SimpleNamespace(total=1024**4, free=0))
    monkeypatch.setattr(hardware.psutil, "disk_usage", usage)
    result = hardware.detect_hardware()
    usage.assert_called_once_with("C:\\")
    assert "livre 0 B" in values(result, "Volumes")["C:\\"]
    assert "não consultada" in values(result, "Volumes")["Z:\\"]


def test_sensor_and_permissions_failures_are_explicit(portable, monkeypatch):
    def denied(*args, **kwargs):
        raise hardware.psutil.AccessDenied()
    monkeypatch.setattr(hardware.psutil, "cpu_freq", denied)
    monkeypatch.setattr(hardware.psutil, "sensors_temperatures", denied)
    result = hardware.detect_hardware()
    assert values(result, "CPU")["Frequência reportada"] == "Indisponível"
    assert values(result, "Sensores")["Temperaturas expostas pelo SO"] == "Indisponível"
    assert any("AccessDenied" in note for note in result.notes)


def test_linux_sysfs_fallback_uses_kernel_sector_units(portable, monkeypatch):
    monkeypatch.setattr(hardware.platform, "system", lambda: "Linux")
    original_glob = hardware.Path.glob
    def fake_glob(path, pattern):
        if path.as_posix().endswith("/sys/block"):
            return iter([hardware.Path("/sys/block/nvme0n1")])
        if path.as_posix().endswith("/sys/class/drm"):
            return iter([hardware.Path("/sys/class/drm/card0"), hardware.Path("/sys/class/drm/card0-HDMI-A-1")])
        return original_glob(path, pattern)
    monkeypatch.setattr(hardware.Path, "glob", fake_glob)
    fields = {"/proc/cpuinfo": "model name : Example Linux CPU\n", "/sys/block/nvme0n1/size": "2097152",
              "/sys/block/nvme0n1/queue/rotational": "0", "/sys/block/nvme0n1/device/model": "Example Disk",
              "/sys/class/drm/card0/device/vendor": "0x1002", "/sys/class/drm/card0/device/device": "0x1234",
              "/sys/class/drm/card0/device/mem_info_vram_total": str(12 * 1024**3)}
    monkeypatch.setattr(hardware, "_read", lambda path: fields.get(path.as_posix(), ""))
    result = hardware.detect_hardware()
    assert values(result, "CPU")["Modelo"] == "Example Linux CPU"
    assert "1.00 GiB" in values(result, "Armazenamento")["nvme0n1"]
    assert values(result, "GPU")["VRAM · card0"] == "12.00 GiB"
    assert "card0-HDMI-A-1" not in values(result, "GPU")


def test_atomic_json_and_csv_exports(portable, tmp_path):
    from expecto_process_manager.interface.hardware_page import export_hardware
    result = hardware.detect_hardware()
    json_path = tmp_path / "hardware.json"
    export_hardware(json_path, result)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["collected_at"] == result.collected_at
    assert payload["items"] and payload["notes"]
    csv_path = tmp_path / "hardware.csv"
    export_hardware(csv_path, result)
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows[0]["source"] == result.items[0].source
    assert any(row["category"] == "Notas / limitações" for row in rows)
    json_path.write_text("old result", encoding="utf-8")
    token = Mock()
    token.check.side_effect = [None, Cancelled()]
    with pytest.raises(Cancelled):
        export_hardware(json_path, result, token)
    assert json_path.read_text(encoding="utf-8") == "old result"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["hardware.csv", "hardware.json"]


def test_hardware_page_is_lazy_and_limits_notes(portable, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from expecto_process_manager.interface import hardware_page
    app = QApplication.instance() or QApplication([])
    tasks = Mock()
    page = hardware_page.HardwarePage(tasks)
    assert not page.loaded
    tasks.start.assert_not_called()
    result = hardware.detect_hardware()
    detect = Mock(return_value=result)
    monkeypatch.setattr(hardware_page, "detect_hardware", detect)
    try:
        page.show()
        app.processEvents()
        assert page.loaded and page.busy
        function, done, _ = tasks.start.call_args.args
        done(function(None))
        detect.assert_called_once_with(None, refresh=False)
        assert not page.busy and page.model.rowCount() > 4
        assert page.tree.wordWrap() and page.tree.textElideMode() == Qt.TextElideMode.ElideNone
        assert page.notes_area.isHidden()
        # A narrow provenance column must increase row height rather than hide
        # its text behind an ellipsis (the complaint that motivated this UI).
        page.tree.setColumnWidth(2, 120)
        cpu_group = next(page.model.item(row) for row in range(page.model.rowCount()) if page.model.item(row).text() == "CPU")
        source_index = cpu_group.child(cpu_group.rowCount() - 1, 2).index()
        page.tree.scrollTo(source_index)
        app.processEvents()
        assert page.tree.visualRect(source_index).height() > page.tree.fontMetrics().height() * 2
        page.notes_toggle.click()
        assert not page.notes_area.isHidden() and page.notes_area.maximumHeight() == 140
        assert page.timer.isActive()
        page.timer.timeout.emit()
        function = tasks.start.call_args.args[0]
        function(None)
        assert detect.call_args.kwargs == {"refresh": False}
        page.hide()
        assert not page.timer.isActive()
    finally:
        page.close()
