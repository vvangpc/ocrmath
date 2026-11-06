"""Grow-only per-installation counters with a shared legacy baseline."""
from copy import deepcopy

KEYS = ("image_count", "pdf_page_count")


def state(payload: dict) -> dict:
    raw = payload.get("counter_state")
    if raw is None:
        return {"legacy": {k: _count(payload.get(k, 0)) for k in KEYS},
                "devices": {}}
    if not isinstance(raw, dict) or set(raw) != {"legacy", "devices"}:
        raise ValueError("Invalid counter state")
    if not isinstance(raw["legacy"], dict) or not isinstance(raw["devices"], dict):
        raise ValueError("Invalid counter components")
    result = deepcopy(raw)
    for component in [result["legacy"], *result["devices"].values()]:
        if not isinstance(component, dict):
            raise ValueError("Invalid device counter")
        for key in KEYS:
            component[key] = _count(component.get(key, 0))
    return result


def _count(value):
    if type(value) is not int or value < 0:
        raise ValueError("Counters must be nonnegative integers")
    return value


def merge(left: dict, right: dict) -> dict:
    a, b = state(left), state(right)
    for key in KEYS:
        a["legacy"][key] = max(a["legacy"][key], b["legacy"][key])
    for device, component in b["devices"].items():
        target = a["devices"].setdefault(device, {})
        for key in KEYS:
            target[key] = max(target.get(key, 0), component[key])
    return fields(a)


def fields(value: dict) -> dict:
    return {"counter_state": value, **{
        key: value["legacy"][key] + sum(c.get(key, 0) for c in value["devices"].values())
        for key in KEYS}}


def increment(payload: dict, device: str, key: str, amount: int) -> None:
    _count(amount)
    value = state(payload)
    component = value["devices"].setdefault(device, {})
    component[key] = component.get(key, 0) + amount
    payload.update(fields(value))
