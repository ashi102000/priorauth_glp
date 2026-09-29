from datetime import date

import pytest

from pa_bench.calc import age_on, bmi, days_between, months_between, pct_change, whole_months_between


def test_bmi_basic():
    assert bmi(96.7, 163) == pytest.approx(36.40, abs=0.01)


def test_bmi_boundaries_from_cohort():
    assert bmi(79.7, 163) == pytest.approx(29.997, abs=0.001)   # GLP1-029: recorded 30.0, computed <30
    assert bmi(81.5, 165) == pytest.approx(29.936, abs=0.001)   # GLP1-030


@pytest.mark.parametrize("w,h", [(0, 170), (80, 0), (-1, 170)])
def test_bmi_rejects_nonpositive(w, h):
    with pytest.raises(ValueError):
        bmi(w, h)


def test_age_birthday_edges():
    b = date(1970, 4, 6)
    assert age_on(b, date(2026, 4, 5)) == 55
    assert age_on(b, date(2026, 4, 6)) == 56
    assert age_on(date(2000, 2, 29), date(2026, 2, 28)) == 25
    assert age_on(date(2000, 2, 29), date(2026, 3, 1)) == 26
    with pytest.raises(ValueError):
        age_on(date(2026, 1, 1), date(2025, 1, 1))


def test_whole_months_exact_boundary():
    assert whole_months_between(date(2026, 2, 18), date(2026, 8, 18)) == 6    # GLP1-029 exact 6 months
    assert whole_months_between(date(2026, 2, 18), date(2026, 8, 17)) == 5
    assert whole_months_between(date(2026, 1, 20), date(2026, 7, 28)) == 6    # GLP1-031
    assert whole_months_between(date(2026, 1, 31), date(2026, 2, 28)) == 0
    assert whole_months_between(date(2026, 8, 18), date(2026, 2, 18)) == -6


def test_days_and_fractional_months():
    assert days_between(date(2026, 1, 20), date(2026, 7, 28)) == 189
    assert months_between(date(2026, 1, 20), date(2026, 7, 28)) == pytest.approx(6.21, abs=0.01)


def test_pct_change():
    assert pct_change(99.6, 96.7) == pytest.approx(-2.91, abs=0.01)
    with pytest.raises(ValueError):
        pct_change(0, 1)
