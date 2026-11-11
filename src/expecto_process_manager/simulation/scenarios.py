def power_profile(name: str, power: float, duration: float):
    if name == "Repouso":
        return lambda t: power * 0.2
    if name == "Aumento súbito":
        return lambda t: power * (0.2 if t < duration/3 else 1)
    if name == "Redução":
        return lambda t: power * (1 if t < duration/2 else 0.2)
    if name == "Arrefecimento":
        return lambda t: power if t < duration/3 else 0
    return lambda t: power


SCENARIOS = ["Constante", "Repouso", "Aumento súbito", "Carga elevada", "Redução", "Arrefecimento"]
