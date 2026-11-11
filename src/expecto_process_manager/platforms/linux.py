import psutil


def temperatures() -> float | None:
    try:
        sensors = psutil.sensors_temperatures()
        # Only known CPU sensor groups; never substitute disk temperatures.
        for key in ("coretemp", "k10temp", "cpu_thermal"):
            if sensors.get(key):
                return sensors[key][0].current
    except (AttributeError, OSError):
        pass
    return None
