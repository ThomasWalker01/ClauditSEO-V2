"""A model row stored under `EXP:<brief>` is read against the sweep that owns
its check (channel ruling 20261011-1050, option 4).

Four `EXP:local-signals` candidates on twenty22 (`nap-missing`,
`nap-inconsistent`, `opening-hours-missing`, `thin-location-page`) waited 21
runs for a corroborating reading that could never come: the walk asked for
readings of the `EXP:local-signals` dimension, and the sweep raises these
checks under `LOC`.
"""

from __future__ import annotations

from clauditseo.persistence import runs


def test_an_exp_row_maps_to_its_registered_sweep():
    assert runs._sweep_dimensions("EXP:local-signals", "nap-missing") == ("LOC",)
    assert runs._sweep_dimensions("LOC", "nap-missing") == ("LOC",)


def test_a_check_no_sweep_raises_maps_to_none():
    assert runs._sweep_dimensions("EXP:local-signals", "unclaimed-listing") == ()


def test_a_check_two_sweeps_raise_maps_to_both():
    assert runs._sweep_dimensions("EXP:links", "redirect-chain") == ("LNK", "TEC")


def test_the_walk_reads_the_mapped_dimension():
    import inspect
    src = inspect.getsource(runs.awaiting_confirmation)
    assert 'dims = _sweep_dimensions(r["dimension"], r["check_id"])' in src
    assert "max(unseen.count(d, r[\"check_id\"], urls, r[\"read_at\"])" in src
