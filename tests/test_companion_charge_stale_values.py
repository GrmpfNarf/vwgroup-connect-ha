# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Charge-detail remaining time / power must not outlive the active charge.

The sheet shows them only while the car charges. Once it reports conservation
charging (target reached) or a stopped charge, the walk finds neither value and
the nav cache used to replay the last active-charge figures for up to 24 h.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from custom_components.vag_connect.companion.channel import CompanionChannel
from custom_components.vag_connect.companion.presets import PRESETS
from custom_components.vag_connect.companion.screen import parse_ui_dump

FIXTURES = Path(__file__).parent / "fixtures" / "companion_battery"
VW = PRESETS["volkswagen"]
CHARGE = next(nav for nav in VW.nav_reads if nav.name == "charge_detail")


def _channel() -> CompanionChannel:
    return CompanionChannel(object(), VW, time_fn=time.monotonic)


def _read(channel: CompanionChannel, name: str) -> dict[str, object]:
    nodes = parse_ui_dump((FIXTURES / (name + ".xml")).read_text(encoding="utf-8"))
    fields: dict[str, object] = {}
    channel._apply_nav_values(CHARGE, nodes, fields)
    return fields


def _replay(channel: CompanionChannel, fields: dict[str, object]) -> dict[str, object]:
    """The cache backfill ``read`` performs after the walk."""
    for key, val in channel._nav_cache.items():
        fields.setdefault(key, val)
    return fields


def test_target_reached_drops_the_figures_of_the_active_charge():
    channel = _channel()
    active = _read(channel, "id4_charging")
    assert active["charging_power_kw"] == 10.0
    assert active["remaining_charge_time_min"] == 270

    after = _replay(channel, _read(channel, "tiguan_target_reached"))
    assert after["is_charging"] is False
    assert "charging_power_kw" not in after
    assert "remaining_charge_time_min" not in after


@pytest.mark.parametrize("state", ["conservationCharging", "Conservation charging"])
def test_conservation_charging_drops_the_figures(state):
    channel = _channel()
    channel._nav_cache.update({"charging_power_kw": 11.0, "remaining_charge_time_min": 5})
    channel._drop_stale_charge_values({"is_charging": True, "charging_state": state})
    assert "charging_power_kw" not in channel._nav_cache
    assert "remaining_charge_time_min" not in channel._nav_cache


def test_active_charge_keeps_the_cache_as_a_flap_guard():
    channel = _channel()
    channel._nav_cache.update({"charging_power_kw": 11.0, "remaining_charge_time_min": 5})
    channel._drop_stale_charge_values({"is_charging": True, "charging_state": "Currently charging"})
    assert channel._nav_cache == {"charging_power_kw": 11.0, "remaining_charge_time_min": 5}


def test_a_walk_that_did_not_read_the_state_keeps_the_cache():
    channel = _channel()
    channel._nav_cache.update({"charging_power_kw": 11.0})
    channel._drop_stale_charge_values({"battery_soc": 80})
    assert channel._nav_cache == {"charging_power_kw": 11.0}


def test_a_value_read_in_the_same_walk_is_kept():
    channel = _channel()
    values = {"is_charging": False, "charging_power_kw": 0.0}
    channel._nav_cache.update({"charging_power_kw": 0.0})
    channel._drop_stale_charge_values(values)
    assert channel._nav_cache == {"charging_power_kw": 0.0}
