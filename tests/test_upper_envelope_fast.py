from __future__ import annotations

from functools import partial
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from dcegm.pre_processing import calc_current_value
from dcegm.upper_envelope import upper_envelope
from dcegm.upper_envelope_fast import _augment_grid
from dcegm.upper_envelope_fast import fast_upper_envelope
from dcegm.upper_envelope_fast import fast_upper_envelope_wrapper
from dcegm.upper_envelope_fast_org import fast_upper_envelope_wrapper_org
from numpy.testing import assert_array_almost_equal as aaae
from toy_models.consumption_retirement_model.utility_functions import utility_func_crra

# Obtain the test directory of the package.
TEST_DIR = Path(__file__).parent

# Directory with additional resources for the testing harness
TEST_RESOURCES_DIR = TEST_DIR / "resources"


@pytest.mark.parametrize("period", [2, 4, 10, 18, 9])
def test_fues_wrapper(period):
    policy_egm = np.genfromtxt(TEST_RESOURCES_DIR / f"period_tests/pol{period}.csv", delimiter=",")
    policy_fedor = np.genfromtxt(
        TEST_RESOURCES_DIR / f"period_tests/expec_pol{period}.csv", delimiter=","
    )

    value_egm = np.genfromtxt(TEST_RESOURCES_DIR / f"period_tests/val{period}.csv", delimiter=",")
    value_fedor = np.genfromtxt(
        TEST_RESOURCES_DIR / f"period_tests/expec_val{period}.csv", delimiter=","
    )

    choice = 0
    max_wealth = 50
    n_grid_wealth = 500
    exogenous_savings_grid = np.linspace(0, max_wealth, n_grid_wealth)

    _index = pd.MultiIndex.from_tuples(
        [("utility_function", "theta"), ("delta", "delta")],
        names=["category", "name"],
    )
    params = pd.DataFrame(data=[1.95, 0.35], columns=["value"], index=_index)
    discount_factor = 0.95

    compute_utility = partial(utility_func_crra, params=params)
    compute_value = partial(
        calc_current_value,
        discount_factor=discount_factor,
        compute_utility=compute_utility,
    )

    policy_refined, value_refined = fast_upper_envelope_wrapper(
        value=value_egm,
        policy=policy_egm,
        exog_grid=np.append(0, exogenous_savings_grid),
        choice=choice,
        compute_value=compute_value,
        period=period,
    )

    policy_expected = policy_fedor[:, ~np.isnan(policy_fedor).any(axis=0)]  # noqa: F841
    value_expected = value_fedor[  # noqa: F841
        :,
        ~np.isnan(value_fedor).any(axis=0),
    ]

    endog_grid_got = policy_refined[0, :][~np.isnan(policy_refined[0, :])]
    policy_got = policy_refined[1, :][~np.isnan(policy_refined[1, :]),]
    value_got = value_refined[1, :][~np.isnan(value_refined[1, :])]

    aaae(endog_grid_got, policy_expected[0])
    aaae(policy_got, policy_expected[1])
    value_expected_interp = np.interp(
        endog_grid_got, value_expected[0], value_expected[1]
    )
    aaae(value_got, value_expected_interp)


def test_fast_upper_envelope_against_org_code():
    policy_egm = np.genfromtxt(TEST_RESOURCES_DIR / "period_tests/pol10.csv", delimiter=",")
    value_egm = np.genfromtxt(TEST_RESOURCES_DIR / "period_tests/val10.csv", delimiter=",")

    choice = 0
    max_wealth = 50
    n_grid_wealth = 500
    exogenous_savings_grid = np.linspace(0, max_wealth, n_grid_wealth)

    _index = pd.MultiIndex.from_tuples(
        [("utility_function", "theta"), ("delta", "delta")],
        names=["category", "name"],
    )
    params = pd.DataFrame(data=[1.95, 0.35], columns=["value"], index=_index)
    discount_factor = 0.95

    compute_utility = partial(utility_func_crra, params=params)
    compute_value = partial(
        calc_current_value,
        discount_factor=discount_factor,
        compute_utility=compute_utility,
    )

    endog_grid_refined, value_refined, policy_refined = fast_upper_envelope(
        endog_grid=policy_egm[0],
        value=value_egm[1],
        policy=policy_egm[1],
        exog_grid=np.append(0, exogenous_savings_grid),
    )

    policy_org, value_org = fast_upper_envelope_wrapper_org(
        policy=policy_egm,
        value=value_egm,
        exog_grid=exogenous_savings_grid,
        choice=choice,
        compute_value=compute_value,
    )

    policy_expected = policy_org[:, ~np.isnan(policy_org).any(axis=0)]
    value_expected = value_org[
        :,
        ~np.isnan(value_org).any(axis=0),
    ]

    assert np.all(np.in1d(value_expected[0, :], endog_grid_refined))
    assert np.all(np.in1d(value_expected[1, :], value_refined))
    assert np.all(np.in1d(policy_expected[0, :], endog_grid_refined))
    assert np.all(np.in1d(policy_expected[1, :], policy_refined))
