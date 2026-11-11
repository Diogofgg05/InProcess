"""Read-only, cached hardware inventory, separate from periodic monitoring.

Values describe what the operating system exposes. In particular, discovering a
GPU does not provide its utilisation, and Windows' 32-bit AdapterRAM field is
deliberately not used as a reliable measurement of modern GPU memory.
"""
from __future__ import annotations

import copy
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import psutil

from .cancellation import Cancellation

CACHE_SECONDS = 600.0
UNAVAILABLE = "Indisponível"
_cache: tuple[str, float, "HardwareInventory"] | None = None
_cache_lock = threading.Lock()


@dataclass(frozen=True)
class HardwareItem:
    category: str
    name: str
    value: str
    source: str


@dataclass
class HardwareInventory:
    collected_at: float
    platform: str
    items: list[HardwareItem] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def age_s(self) -> float:
        return max(0.0, time.time() - self.collected_at)

    def as_dict(self) -> dict[str, Any]:
        """JSON-compatible snapshot; collection time remains the original time."""
        return {**asdict(self), "age_s": self.age_s, "cache_seconds": CACHE_SECONDS}


def detect_hardware(token: Cancellation | None = None, *, refresh: bool = False) -> HardwareInventory:
    """Collect once per ten minutes, unless explicitly refreshed.

    Call from a worker: the optional Windows CIM subprocess has an eight-second
    timeout. Cache hits preserve the timestamp and return an independent copy.
    Concurrent requests share one collection; cancellation never poisons cache.
    """
    global _cache
    if token:
        token.check()
    system = platform.system()
    with _cache_lock:
        if token:
            token.check()
        now = time.monotonic()
        if not refresh and _cache and _cache[0] == system and now - _cache[1] < CACHE_SECONDS:
            return copy.deepcopy(_cache[2])
        inventory = _collect(system, token)
        if token:
            token.check()
        _cache = (system, time.monotonic(), copy.deepcopy(inventory))
        return inventory


def get_cached_hardware() -> HardwareInventory | None:
    """Return the latest snapshot immediately, with no discovery or lock wait.

    A stale snapshot is still useful for report provenance: the unchanged
    collected_at / age_s identify it. None means no snapshot or collection busy.
    """
    if not _cache_lock.acquire(blocking=False):
        return None
    try:
        return copy.deepcopy(_cache[2]) if _cache else None
    finally:
        _cache_lock.release()


def _number(value: Any) -> float | None:
    try:
        number = float(value)
        return number if number > 0 and number < float("inf") else None
    except (TypeError, ValueError, OverflowError):
        return None


def _bytes(value: Any) -> str:
    if value == 0:
        return "0 B"
    size = _number(value)
    if size is None:
        return UNAVAILABLE
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if size < 1024 or unit == "PiB":
            return f"{size:.2f} {unit}"
        size /= 1024
    return UNAVAILABLE


def _text(value: Any) -> str:
    if value is None:
        return UNAVAILABLE
    value = str(value).strip()
    return value if value and value.lower() not in {"unknown", "none", "to be filled by o.e.m.", "default string"} else UNAVAILABLE


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _collect(system: str, token: Cancellation | None) -> HardwareInventory:
    result = HardwareInventory(time.time(), system)

    def add(category: str, name: str, value: Any, source: str) -> None:
        result.items.append(HardwareItem(category, name, _text(value), source))

    def probe(category: str, name: str, function, source: str) -> None:
        if token:
            token.check()
        try:
            add(category, name, function(), source)
        except (OSError, psutil.Error, AttributeError, NotImplementedError, ValueError) as error:
            add(category, name, UNAVAILABLE, source)
            result.notes.append(f"{category} · {name}: {type(error).__name__}; dados não acessíveis.")

    add("Sistema", "Sistema operativo", f"{system} {platform.release()}", "Python platform")
    add("Sistema", "Arquitetura", platform.machine(), "Python platform")
    probe("Sistema", "Arranque", lambda: time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime(psutil.boot_time())), "psutil boot_time")
    probe("CPU", "Núcleos físicos", lambda: psutil.cpu_count(logical=False), "psutil cpu_count")
    probe("CPU", "Processadores lógicos", lambda: psutil.cpu_count(logical=True), "psutil cpu_count")
    probe("Memória", "RAM utilizável pelo SO", lambda: _bytes(psutil.virtual_memory().total), "psutil virtual_memory")
    probe("Memória", "Swap / ficheiro de paginação", lambda: "0 B (não configurado)" if psutil.swap_memory().total == 0 else _bytes(psutil.swap_memory().total), "psutil swap_memory")
    probe("CPU", "Frequência reportada", lambda: _frequency(), "psutil cpu_freq · instantâneo")

    if system == "Windows":
        _windows(result, add, token)
    elif system == "Linux":
        _linux(result, add, token)
    else:
        add("CPU", "Modelo", platform.processor(), "Python platform")
        result.notes.append("Inventário específico não disponível neste SO; mantêm-se as consultas portáveis psutil.")

    _partitions(result, add, token)
    _network(result, add, token)
    probe("Energia", "Bateria", lambda: _battery(), "psutil sensors_battery")
    probe("Sensores", "Temperaturas expostas pelo SO", lambda: _temperatures(), "psutil sensors_temperatures")
    result.notes.append("Inventário de leitura pontual; frequências, rede, bateria e sensores podem mudar. Cache de 10 min; Atualizar força nova consulta.")
    result.notes.append("Detetar um adaptador gráfico não mede utilização, temperatura ou consumo da GPU. Campos indisponíveis não são estimados.")
    return result


def _frequency() -> str:
    frequency = psutil.cpu_freq()
    if frequency is None or not _number(frequency.current):
        return UNAVAILABLE
    maximum = f" · máximo reportado {frequency.max:.0f} MHz" if _number(frequency.max) else ""
    return f"{frequency.current:.0f} MHz{maximum}"


def _battery() -> str:
    battery = psutil.sensors_battery()
    if battery is None:
        return "Não detetada pelo SO"
    state = "ligada à corrente" if battery.power_plugged else "em descarga"
    return f"{battery.percent:.0f}% · {state}"


def _temperatures() -> str:
    reader = getattr(psutil, "sensors_temperatures", None)
    readings = reader(fahrenheit=False) if reader else {}
    values = [f"{group} / {sensor.label or 'sensor'}: {sensor.current:.1f} °C"
              for group, sensors in readings.items() for sensor in sensors
              if sensor.current is not None and float("-inf") < sensor.current < float("inf")]
    return "; ".join(values) if values else "Indisponível · nenhum sensor acessível neste fornecedor"


def _partitions(result: HardwareInventory, add, token: Cancellation | None) -> None:
    try:
        partitions = psutil.disk_partitions(all=False)
    except (OSError, psutil.Error):
        add("Volumes", "Volumes montados", UNAVAILABLE, "psutil disk_partitions")
        return
    if not partitions:
        add("Volumes", "Volumes montados", "Nenhum volume reportado", "psutil disk_partitions")
    seen: set[str] = set()
    for partition in partitions:
        if token:
            token.check()
        if partition.mountpoint in seen:
            continue
        seen.add(partition.mountpoint)
        # Do not wake removable media or network shares to discover their size.
        remote = partition.device.startswith("\\\\") or partition.fstype.lower() in {"nfs", "nfs4", "cifs", "smbfs"}
        skip = remote or "cdrom" in partition.opts or "removable" in partition.opts
        value = f"{partition.device} · {partition.fstype or 'sistema de ficheiros não indicado'}"
        if skip:
            value += " · capacidade não consultada (rede / removível)"
        else:
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                value += f" · total {_bytes(usage.total)} · livre {_bytes(usage.free) if usage.free else '0 B'}"
            except (OSError, psutil.Error):
                value += " · capacidade indisponível"
        add("Volumes", partition.mountpoint, value, "psutil disk_partitions / disk_usage")


def _network(result: HardwareInventory, add, token: Cancellation | None) -> None:
    try:
        states = psutil.net_if_stats()
        addresses = psutil.net_if_addrs()
    except (OSError, psutil.Error):
        add("Rede", "Interfaces", UNAVAILABLE, "psutil net_if_stats / net_if_addrs")
        return
    for name in sorted(set(states) | set(addresses)):
        if token:
            token.check()
        state = states.get(name)
        details = ["ativa" if state and state.isup else "inativa / estado indisponível"]
        if state and state.speed > 0:
            details.append(f"ligação nominal {state.speed} Mbit/s")
        else:
            details.append("velocidade nominal indisponível")
        families = {address.family for address in addresses.get(name, [])}
        details.extend(label for family, label in ((socket.AF_INET, "IPv4 configurado"), (socket.AF_INET6, "IPv6 configurado")) if family in families)
        add("Rede", name, " · ".join(details), "psutil net_if_stats / net_if_addrs")
    if not states and not addresses:
        add("Rede", "Interfaces", "Nenhuma interface reportada", "psutil net_if_stats")
    result.notes.append("Velocidade de ligação de rede é nominal; não representa tráfego instantâneo nem capacidade garantida. Endereços IP e MAC não são exportados.")


# One subprocess and one JSON response; individual unsupported CIM classes do not
# discard the remaining results. Serial numbers and network identifiers omitted.
_CIM_SCRIPT = r"""
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$ErrorActionPreference = 'Stop'
$result = @{data = @{}; errors = @()}
$queries = @(
  @{key='cpu'; class='Win32_Processor'; props=@('Name','Manufacturer','MaxClockSpeed')},
  @{key='memory'; class='Win32_PhysicalMemory'; props=@('BankLabel','Capacity','Speed','ConfiguredClockSpeed','Manufacturer')},
  @{key='gpu'; class='Win32_VideoController'; props=@('Name','DriverVersion','AdapterRAM')},
  @{key='board'; class='Win32_BaseBoard'; props=@('Manufacturer','Product')},
  @{key='bios'; class='Win32_BIOS'; props=@('Manufacturer','SMBIOSBIOSVersion','ReleaseDate')},
  @{key='disks'; class='Win32_DiskDrive'; props=@('Model','Size','MediaType','InterfaceType')},
  @{key='storage'; class='MSFT_PhysicalDisk'; namespace='root/Microsoft/Windows/Storage'; props=@('FriendlyName','Size','MediaType','BusType')},
  @{key='os'; class='Win32_OperatingSystem'; props=@('Caption','Version','BuildNumber')}
)
foreach ($query in $queries) {
  try {
    $parameters = @{ClassName=$query.class; ErrorAction='Stop'}
    if ($query.namespace) {$parameters.Namespace=$query.namespace}
    $result.data[$query.key] = @(Get-CimInstance @parameters | Select-Object -Property $query.props)
  } catch { $result.errors += $query.class + ': ' + $_.Exception.GetType().Name + ' (' + $_.CategoryInfo.Category + '; HRESULT ' + $_.Exception.HResult.ToString('X8') + ')' }
}
$result | ConvertTo-Json -Depth 6 -Compress
"""


def _query_windows_cim() -> tuple[dict[str, Any], list[str]]:
    executable = shutil.which("powershell.exe")
    if not executable:
        return {}, ["CIM: Windows PowerShell não encontrado; mantêm-se os dados psutil e do registo."]
    try:
        process = subprocess.run(
            [executable, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", _CIM_SCRIPT],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False,
        )
        if process.returncode:
            return {}, [f"CIM indisponível: PowerShell terminou com código {process.returncode}."]
        payload = json.loads(process.stdout.lstrip("\ufeff"))
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
            raise ValueError("Resposta CIM inválida")
        errors = payload.get("errors", [])
        if not isinstance(errors, list):
            errors = [errors]
        return payload["data"], [f"Consulta não disponível: {_text(error)}" for error in errors]
    except subprocess.TimeoutExpired:
        return {}, ["CIM excedeu o limite de 8 s; a consulta foi interrompida. Atualizar permite tentar novamente."]
    except (OSError, ValueError, UnicodeError):
        return {}, ["CIM indisponível: não foi possível ler uma resposta JSON válida do PowerShell."]


def _records(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    values = data.get(key, [])
    if isinstance(values, dict):
        return [values]
    return [value for value in values if isinstance(value, dict)] if isinstance(values, list) else []


def _registry_cpu() -> str:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
            return _text(winreg.QueryValueEx(key, "ProcessorNameString")[0])
    except (ImportError, OSError):
        return UNAVAILABLE


def _registry_windows_components() -> dict[str, Any]:
    """Firmware and configured GPU fallback; never export device identifiers."""
    try:
        import winreg
    except ImportError:
        return {}
    result: dict[str, Any] = {"gpu": []}

    def field(key, name):
        try:
            value = winreg.QueryValueEx(key, name)[0]
            return " · ".join(str(part) for part in value) if isinstance(value, (list, tuple)) else value
        except OSError:
            return None

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\BIOS") as key:
            result["board"] = {"Manufacturer": field(key, "BaseBoardManufacturer"), "Product": field(key, "BaseBoardProduct")}
            result["bios"] = {"Manufacturer": field(key, "BIOSVendor"), "SMBIOSBIOSVersion": field(key, "BIOSVersion"), "ReleaseDate": field(key, "BIOSReleaseDate")}
    except OSError:
        pass
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}") as adapters:
            for index in range(winreg.QueryInfoKey(adapters)[0]):
                child = winreg.EnumKey(adapters, index)
                if not re.fullmatch(r"\d{4}", child):
                    continue
                try:
                    with winreg.OpenKey(adapters, child) as key:
                        name = field(key, "DriverDesc")
                        if name:
                            result["gpu"].append({"Name": name, "DriverVersion": field(key, "DriverVersion")})
                except OSError:
                    continue
    except OSError:
        pass
    return result


def _windows(result: HardwareInventory, add, token: Cancellation | None) -> None:
    data, notes = _query_windows_cim()
    result.notes.extend(notes)
    if token:
        token.check()
    registry = _registry_windows_components() if any(not _records(data, key) for key in ("gpu", "board", "bios")) else {}
    cpus = _records(data, "cpu")
    if cpus:
        for i, cpu in enumerate(cpus, 1):
            add("CPU", f"Modelo {i}", cpu.get("Name"), "CIM Win32_Processor")
    else:
        add("CPU", "Modelo", _registry_cpu(), "Registo Windows · ProcessorNameString")
    for i, memory in enumerate(_records(data, "memory"), 1):
        speed = _number(memory.get("ConfiguredClockSpeed"))
        value = f"{_bytes(memory.get('Capacity'))} · {_text(memory.get('Manufacturer'))}"
        if speed:
            value += f" · relógio configurado {speed:.0f} MHz (CIM)"
        elif _number(memory.get("Speed")):
            # The legacy Speed property's documented units differ from the
            # modern ConfiguredClockSpeed field; do not silently reinterpret it.
            value += " · relógio configurado indisponível"
        add("Memória", f"Módulo {i} · {_text(memory.get('BankLabel'))}", value, "CIM Win32_PhysicalMemory")
    if not _records(data, "memory"):
        add("Memória", "Módulos físicos", UNAVAILABLE, "CIM Win32_PhysicalMemory")
    for i, gpu in enumerate(_records(data, "gpu"), 1):
        add("GPU", f"Adaptador {i}", gpu.get("Name"), "CIM Win32_VideoController")
        add("GPU", f"Controlador {i}", gpu.get("DriverVersion"), "CIM Win32_VideoController.DriverVersion")
        add("GPU", f"Memória dedicada {i}", "Indisponível · AdapterRAM de 32 bits não confirma a VRAM real", "CIM Win32_VideoController · limitação do fornecedor")
    registry_gpu = _records(registry, "gpu") if not _records(data, "gpu") else []
    for i, gpu in enumerate(registry_gpu, 1):
        add("GPU", f"Adaptador configurado {i}", gpu.get("Name"), "Registo Windows · classe Display · configuração")
        add("GPU", f"Controlador configurado {i}", gpu.get("DriverVersion"), "Registo Windows · DriverVersion")
        add("GPU", f"Memória dedicada {i}", UNAVAILABLE, "Registo Windows · não medida por este fornecedor")
    if registry_gpu:
        result.notes.append("Adaptadores do registo representam configurações de controladores; podem incluir dispositivos antigos ou virtuais e não confirmam atividade ou presença atual.")
    if not _records(data, "gpu") and not registry_gpu:
        add("GPU", "Adaptadores", UNAVAILABLE, "CIM Win32_VideoController")
    result.notes.append("Windows: AdapterRAM (uint32) pode truncar VRAM, incluindo placas com mais de 4 GiB; não é apresentado como capacidade dedicada fiável.")
    boards = _records(data, "board") or _records(registry, "board")
    board_source = "CIM Win32_BaseBoard" if _records(data, "board") else "Registo Windows · HARDWARE/BIOS"
    for row in boards:
        add("Placa principal", "Fabricante / modelo", f"{_text(row.get('Manufacturer'))} · {_text(row.get('Product'))}", board_source)
    if not boards:
        add("Placa principal", "Fabricante / modelo", UNAVAILABLE, "CIM / Registo Windows")
    bios = _records(data, "bios") or _records(registry, "bios")
    bios_source = "CIM Win32_BIOS" if _records(data, "bios") else "Registo Windows · HARDWARE/BIOS"
    for row in bios:
        add("Firmware", "BIOS / UEFI", f"{_text(row.get('Manufacturer'))} · {_text(row.get('SMBIOSBIOSVersion'))}", bios_source)
        add("Firmware", "Data de firmware", row.get("ReleaseDate"), bios_source)
    if not bios:
        add("Firmware", "BIOS / UEFI", UNAVAILABLE, "CIM / Registo Windows")
    for i, disk in enumerate(_records(data, "disks"), 1):
        add("Armazenamento", f"Disco físico {i}", f"{_text(disk.get('Model'))} · {_bytes(disk.get('Size'))} · {_text(disk.get('InterfaceType'))}", "CIM Win32_DiskDrive")
    media = {3: "HDD", 4: "SSD", 5: "SCM"}
    buses = {7: "USB", 11: "SATA", 17: "NVMe"}
    for disk in _records(data, "storage"):
        try:
            kind = media.get(int(disk.get("MediaType", 0)), "tipo indisponível")
            bus = buses.get(int(disk.get("BusType", 0)), "barramento não identificado")
        except (ValueError, TypeError):
            kind, bus = "tipo indisponível", "barramento não identificado"
        add("Armazenamento", f"Tipo · {_text(disk.get('FriendlyName'))}", f"{kind} · {bus} · {_bytes(disk.get('Size'))}", "CIM MSFT_PhysicalDisk")
    if not _records(data, "disks") and not _records(data, "storage"):
        add("Armazenamento", "Discos físicos", UNAVAILABLE, "CIM Win32_DiskDrive / MSFT_PhysicalDisk")
    for row in _records(data, "os"):
        add("Sistema", "Edição / versão", f"{_text(row.get('Caption'))} · {_text(row.get('Version'))} · build {_text(row.get('BuildNumber'))}", "CIM Win32_OperatingSystem")


def _linux(result: HardwareInventory, add, token: Cancellation | None) -> None:
    cpuinfo = _read(Path("/proc/cpuinfo"))
    match = re.search(r"^(?:model name|Hardware|Processor)\s*:\s*(.+)$", cpuinfo, re.MULTILINE)
    add("CPU", "Modelo", match.group(1) if match else platform.processor(), "/proc/cpuinfo / Python platform")
    for category, name, filename in (
        ("Placa principal", "Fabricante", "board_vendor"), ("Placa principal", "Modelo", "board_name"),
        ("Firmware", "Fabricante", "bios_vendor"), ("Firmware", "Versão", "bios_version"),
        ("Firmware", "Data", "bios_date"),
    ):
        add(category, name, _read(Path("/sys/class/dmi/id") / filename), f"sysfs dmi/{filename}")
    disks = []
    for device in sorted(Path("/sys/block").glob("*")):
        if token:
            token.check()
        if device.name.startswith(("loop", "ram", "zram", "dm-")):
            continue
        sectors = _number(_read(device / "size"))
        rotational = _read(device / "queue/rotational")
        kind = {"0": "não rotativo (reportado pelo kernel)", "1": "rotativo"}.get(rotational, "tipo indisponível")
        model = _read(device / "device/model") or device.name
        add("Armazenamento", device.name, f"{model} · {_bytes(sectors * 512 if sectors else None)} · {kind}", "sysfs block · size em setores de 512 B")
        disks.append(device.name)
    if not disks:
        add("Armazenamento", "Discos físicos", UNAVAILABLE, "sysfs /sys/block")
    cards = [card for card in Path("/sys/class/drm").glob("card*") if re.fullmatch(r"card\d+", card.name)]
    vendors = {"0x8086": "Intel", "0x10de": "NVIDIA", "0x1002": "AMD"}
    for card in sorted(cards):
        vendor = _read(card / "device/vendor")
        device = _read(card / "device/device")
        driver = card / "device/driver"
        try:
            driver_name = driver.resolve(strict=True).name
        except OSError:
            driver_name = UNAVAILABLE
        add("GPU", card.name, f"{vendors.get(vendor, vendor or UNAVAILABLE)} · PCI {device or UNAVAILABLE} · controlador {driver_name}", "sysfs drm · identificação PCI")
        dedicated = _number(_read(card / "device/mem_info_vram_total"))
        add("GPU", f"VRAM · {card.name}", _bytes(dedicated), "sysfs mem_info_vram_total · quando exposto pelo controlador")
    if not cards:
        add("GPU", "Adaptadores", UNAVAILABLE, "sysfs /sys/class/drm")
    result.notes.append("Linux: módulos DIMM e memória partilhada da GPU não são inferidos. Firmware pode exigir permissões que esta aplicação não solicita.")
