import platform

SYSTEM = platform.system()
if SYSTEM == "Linux":
    from .linux import temperatures
else:
    from .windows import temperatures
