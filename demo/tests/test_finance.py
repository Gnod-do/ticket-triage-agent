from pathlib import Path

from fbagent.finance import annual_benefit, deposit_alternative, max_capex, scenarios, tornado

ASSUMPTIONS = Path(__file__).resolve().parents[1] / "finance" / "assumptions.yaml"

ZERO = dict(managers=0, h_week=0, hour_cost_rub=0, aht_min=0, clusters_per_year=0, accept_rate=0,
            weekly_rate=0, lead_gain_weeks=0, extra_fixed_clusters=0, remaining_weeks=0, r=0.1, g=0.0)


def test_benefit_components():
    p = dict(ZERO, managers=40, h_week=2, hour_cost_rub=900)
    assert annual_benefit(p)["b2"] == 40 * 2 * 48 * 900
    p = dict(ZERO, clusters_per_year=10, accept_rate=0.5, weekly_rate=4, lead_gain_weeks=5, aht_min=12,
             hour_cost_rub=1000)
    b = annual_benefit(p)
    assert b["avoided_tickets"] == 100 and b["b1"] == 100 * 12 / 60 * 1000


def test_max_capex_formula():
    p = dict(ZERO, managers=1, h_week=1, hour_cost_rub=1_000_000 / 48)
    assert abs(max_capex(p) - 2_486_852) <= 1


def test_growth_increases_capex():
    p = dict(ZERO, managers=1, h_week=1, hour_cost_rub=1_000_000 / 48)
    assert max_capex(dict(p, g=0.08)) > max_capex(p)


def test_deposit_alternative():
    assert abs(deposit_alternative(1_000_000, 0.1, 3) - 331_000) < 1


def test_scenarios_ordered():
    rows = scenarios(ASSUMPTIONS)
    caps = {r["name"]: r["max_capex"] for r in rows}
    assert caps["pessimistic"] < caps["base"] < caps["optimistic"]


def test_tornado_writes_png(tmp_path):
    base = next(r for r in scenarios(ASSUMPTIONS) if r["name"] == "base")["params"]
    out = tmp_path / "t.png"
    order = tornado(base, out)
    assert out.stat().st_size > 1000 and len(order) >= 5
