"""Unit tests for core.darcy — Darcy flux and seepage velocity."""

import math

import pytest

from core import darcy


def test_darcy_flux_basic():
    # q = K * i
    assert darcy.darcy_flux(2.0, 0.01) == pytest.approx(0.02)


def test_seepage_velocity_basic():
    # vs = q / n_e
    assert darcy.seepage_velocity(0.02, 0.4) == pytest.approx(0.05)


def test_darcy_flux_rejects_nonpositive_K():
    with pytest.raises(ValueError):
        darcy.darcy_flux(0.0, 0.01)
    with pytest.raises(ValueError):
        darcy.darcy_flux(-1.0, 0.01)


def test_darcy_flux_rejects_nonpositive_gradient():
    with pytest.raises(ValueError):
        darcy.darcy_flux(1.0, 0.0)
    with pytest.raises(ValueError):
        darcy.darcy_flux(1.0, -0.01)


def test_seepage_velocity_rejects_bad_porosity():
    for bad in (0.0, -0.1, 1.5):
        with pytest.raises(ValueError):
            darcy.seepage_velocity(0.02, bad)


def test_seepage_velocity_allows_porosity_of_one():
    assert darcy.seepage_velocity(0.02, 1.0) == pytest.approx(0.02)
