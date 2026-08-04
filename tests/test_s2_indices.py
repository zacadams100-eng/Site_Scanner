"""
Check the Sentinel-2 index formulas arithmetically.

These cannot be verified against Earth Engine here — there are no credentials
— but the formulas are just algebra over band values, and algebra can be
checked. A tiny stub stands in for `ee.Image` and does the arithmetic in
Python, so feeding known reflectances gives numbers that can be compared with
values worked out by hand.

This catches the errors that actually happen in band maths: operands the wrong
way round (NDBI is SWIR−NIR, NDWI is green−NIR, and swapping either just flips
the sign of a plausible-looking number), a missing reflectance scale on the
indices that mix in additive constants, and typos in the MSAVI radical.
"""

import math

import pytest

import ee_series


class FakeImage:
    """Enough of the ee.Image arithmetic surface to evaluate the formulas."""

    def __init__(self, bands):
        self.bands = dict(bands)

    # -- selection ---------------------------------------------------------
    def select(self, which):
        if isinstance(which, str):
            return FakeImage({which: self.bands[which]})
        return FakeImage({k: self.bands[k] for k in which})

    def rename(self, name):
        names = [name] if isinstance(name, str) else list(name)
        return FakeImage(dict(zip(names, self.bands.values())))

    # -- arithmetic --------------------------------------------------------
    def _value(self):
        (v,) = self.bands.values()
        return v

    def _combine(self, other, op):
        b = other._value() if isinstance(other, FakeImage) else other
        return FakeImage({"v": op(self._value(), b)})

    def add(self, o): return self._combine(o, lambda a, b: a + b)
    def subtract(self, o): return self._combine(o, lambda a, b: a - b)
    def multiply(self, o):
        if isinstance(o, FakeImage):
            return self._combine(o, lambda a, b: a * b)
        return FakeImage({k: v * o for k, v in self.bands.items()})
    def divide(self, o): return self._combine(o, lambda a, b: a / b)
    def pow(self, n): return FakeImage({"v": self._value() ** n})
    def sqrt(self): return FakeImage({"v": math.sqrt(self._value())})


class FakeEE:
    class Image:
        @staticmethod
        def cat(images):
            out = {}
            for img in images:
                out.update(img.bands)
            return FakeImage(out)


# Plausible reflectances for a vegetated field, as raw Sentinel-2 DNs.
REFLECTANCE = {"B2": 0.05, "B3": 0.08, "B4": 0.06,
               "B5": 0.15, "B8": 0.40, "B11": 0.25, "B12": 0.15}
DN = {k: v / ee_series.S2_SCALE for k, v in REFLECTANCE.items()}


@pytest.fixture
def indices():
    img, names = ee_series._s2_index_image(FakeEE, FakeImage(DN))
    return {n: img.bands[n] for n in names}


def nd(a, b):
    return (a - b) / (a + b)


R = REFLECTANCE


@pytest.mark.parametrize("factor_id, expected", [
    ("ndvi", nd(R["B8"], R["B4"])),
    ("gndvi", nd(R["B8"], R["B3"])),
    ("ndmi", nd(R["B8"], R["B11"])),
    ("nbr", nd(R["B8"], R["B12"])),
    # SWIR minus NIR, not the other way round — built-up is bright in SWIR.
    ("ndbi", nd(R["B11"], R["B8"])),
    # Green minus NIR. Reversing this gives NDVI's sign and looks fine.
    ("ndwi", nd(R["B3"], R["B8"])),
    ("bare_soil_index", nd(R["B11"] + R["B4"], R["B8"] + R["B2"])),
])
def test_normalised_differences(indices, factor_id, expected):
    assert indices[factor_id] == pytest.approx(expected, rel=1e-9)


def test_evi(indices):
    expected = 2.5 * (R["B8"] - R["B4"]) / (
        R["B8"] + 6 * R["B4"] - 7.5 * R["B2"] + 1)
    assert indices["evi"] == pytest.approx(expected, rel=1e-9)


def test_savi(indices):
    expected = 1.5 * (R["B8"] - R["B4"]) / (R["B8"] + R["B4"] + 0.5)
    assert indices["savi"] == pytest.approx(expected, rel=1e-9)


def test_msavi(indices):
    n, r = R["B8"], R["B4"]
    expected = (2 * n + 1 - math.sqrt((2 * n + 1) ** 2 - 8 * (n - r))) / 2
    assert indices["msavi"] == pytest.approx(expected, rel=1e-9)


def test_chlorophyll_index(indices):
    assert indices["chlorophyll_index"] == pytest.approx(
        R["B8"] / R["B5"] - 1, rel=1e-9)


def test_reflectance_is_scaled_before_the_additive_indices(indices):
    """EVI, SAVI, MSAVI and CI mix reflectance with constants like +1 and
    +0.5. Feed them raw 0-10000 DNs and those constants vanish into rounding,
    which yields numbers that are wrong but still land in a plausible range."""
    unscaled = 2.5 * (DN["B8"] - DN["B4"]) / (
        DN["B8"] + 6 * DN["B4"] - 7.5 * DN["B2"] + 1)
    assert indices["evi"] != pytest.approx(unscaled, rel=1e-6)
    assert indices["evi"] == pytest.approx(0.6137, abs=1e-3)


def test_every_index_lands_inside_its_catalogue_range(indices):
    """lo/hi drive the colour ramp and the axis. A value outside them is
    either a formula error or a mis-declared range."""
    import catalog

    for factor_id, value in indices.items():
        f = catalog.FACTOR_BY_ID[factor_id]
        assert f["lo"] <= value <= f["hi"], (
            f"{factor_id}={value:.4f} outside declared {f['lo']}..{f['hi']}")


def test_the_indices_computed_are_exactly_those_registered():
    img, names = ee_series._s2_index_image(FakeEE, FakeImage(DN))
    assert sorted(names) == sorted(ee_series.S2_FACTORS)
