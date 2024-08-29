from typing import Any, Dict

import jax
import jax.numpy as jnp
import numpy as np
import pytest
from numpy.testing import assert_array_almost_equal as aaae

from dcegm.pre_processing.setup_model import setup_model
from dcegm.solve import solve_dcegm
from tests.utils.interp1d_auxiliary import (
    interpolate_policy_and_value_on_wealth_grid,
    linear_interpolation_with_extrapolation,
)

# from toy_models.consumption_retirement_model.budget_functions import budget_constraint
from toy_models.consumption_retirement_model.state_space_objects import (
    create_state_space_function_dict,
)
from toy_models.consumption_retirement_model.utility_functions import (
    create_final_period_utility_function_dict,
    create_utility_function_dict,
    utiility_log_crra,
    utiility_log_crra_final_consume_all,
)


def sparsity_condition(
    period,
    experience,
):

    max_init_experience = 0

    cond = True

    if (period < experience) | (experience > N_PERIODS):
        cond = False

    # if (age >= options["max_ret_age"] + 1) & (is_retired(lagged_choice) is False):
    #     cond = False

    return cond


MAX_WEALTH = 50
WEALTH_GRID_POINTS = 100
EXPERIENCE_GRID_POINTS = 6  # 9

N_PERIODS = 20

OPTIONS_DISCRETE_EXP = {
    "model_params": {
        "n_grid_points": WEALTH_GRID_POINTS,
        "max_wealth": MAX_WEALTH,
        "quadrature_points_stochastic": 5,
        "n_choices": 2,
    },
    "state_space": {
        "n_periods": N_PERIODS,
        "choices": np.arange(2),
        "endogenous_states": {
            "married": [0, 1],
            "experience": np.arange(N_PERIODS),
            "sparsity_condition": sparsity_condition,
        },
        "continuous_states": {
            "wealth": np.linspace(0, MAX_WEALTH, WEALTH_GRID_POINTS),
        },
    },
}

OPTIONS_CONTINUOUS_EXP = {
    "model_params": {
        "n_grid_points": WEALTH_GRID_POINTS,
        "max_wealth": MAX_WEALTH,
        "quadrature_points_stochastic": 5,
        "n_choices": 2,
    },
    "state_space": {
        "n_periods": N_PERIODS,
        "choices": np.arange(2),
        "endogenous_states": {
            "married": [0, 1],
        },
        "continuous_states": {
            "wealth": np.linspace(0, MAX_WEALTH, WEALTH_GRID_POINTS),
            "experience": np.linspace(0, 1, EXPERIENCE_GRID_POINTS),
        },
    },
}

PARAMS = {
    "beta": 0.95,
    "delta": 0.35,
    "rho": 1.95,
    "savings_rate": 0.04,
    "constant": 0.75,
    "exp": 0.04,
    "exp_squared": -0.0002,
    "consumption_floor": 0.001,
}

# wage,constant,0.75,age-independent labor income
# wage,exp,0.04,return to experience
# wage,exp_squared,-0.0002,return to experience squared
# ====================================================================================
# Model functions
# ====================================================================================


def budget_constraint_continuous(
    period: int,
    lagged_choice: int,
    experience: float,
    savings_end_of_previous_period: float,
    income_shock_previous_period: float,
    options: Dict[str, Any],
    params: Dict[str, float],
) -> float:

    working = lagged_choice == 0

    experience_years = experience * period

    # Calculate stochastic labor income
    income_from_previous_period = _calc_stochastic_income(
        experience=experience_years * 100,
        wage_shock=income_shock_previous_period,
        params=params,
    )

    wealth_beginning_of_period = (
        income_from_previous_period * working
        + (1 + params["interest_rate"]) * savings_end_of_previous_period
    )

    # Retirement safety net, only in retirement model, but we require to have it always
    # as a parameter
    return jnp.maximum(wealth_beginning_of_period, params["consumption_floor"])


def budget_constraint_discrete(
    # period: int,
    lagged_choice: int,
    experience: int,
    savings_end_of_previous_period: float,
    income_shock_previous_period: float,
    options: Dict[str, Any],
    params: Dict[str, float],
) -> float:

    working = lagged_choice == 0

    # Calculate stochastic labor income
    income_from_previous_period = _calc_stochastic_income(
        experience=experience * 100,
        wage_shock=income_shock_previous_period,
        params=params,
    )

    wealth_beginning_of_period = (
        income_from_previous_period * working
        + (1 + params["interest_rate"]) * savings_end_of_previous_period
    )

    # Retirement safety net, only in retirement model, but we require to have it always
    # as a parameter
    return jnp.maximum(wealth_beginning_of_period, params["consumption_floor"])


@jax.jit
def _calc_stochastic_income(
    experience: int,
    wage_shock: float,
    params: Dict[str, float],
) -> float:

    labor_income = (
        params["constant"]
        + params["exp"] * experience
        + params["exp_squared"] * experience**2
    )

    return jnp.exp(labor_income + wage_shock)


def get_next_period_experience(period, choice, experience, options, params):

    working = choice == 0

    return 1 / (period + 1) * (period * experience + working)


def get_next_period_state(period, choice, experience):

    next_state = {}

    next_state["period"] = period + 1
    next_state["lagged_choice"] = choice

    next_state["experience"] = experience + (choice == 0)

    return next_state


def get_next_period_discrete_state(period, choice):

    next_state = {}

    next_state["period"] = period + 1
    next_state["lagged_choice"] = choice

    return next_state


def get_state_specific_feasible_choice_set(
    lagged_choice: int,
    options: Dict,
) -> np.ndarray:
    """Select state-specific feasible choice set such that retirement is absorbing."""

    n_choices = options["n_choices"]
    # n_choices = len(options["state_space"]["choices"])

    # Once the agent choses retirement, she can only choose retirement thereafter.
    # Hence, retirement is an absorbing state.
    if lagged_choice == 1:
        feasible_choice_set = np.array([1])
    else:
        feasible_choice_set = np.arange(n_choices)

    return feasible_choice_set


def sparsity_condition(
    period,
    experience,
):

    max_init_experience = 0

    cond = True

    if (period + max_init_experience == experience) & (period > 0) | (
        experience > N_PERIODS
    ):
        cond = False

    # if (age >= options["max_ret_age"] + 1) & (is_retired(lagged_choice) is False):
    #     cond = False

    return cond


# ====================================================================================
# Test
# ====================================================================================


def test_discrete_exp():

    exog_savings_grid = jnp.linspace(
        0,
        OPTIONS_DISCRETE_EXP["model_params"]["max_wealth"],
        OPTIONS_DISCRETE_EXP["model_params"]["n_grid_points"],
    )
    utility_functions = create_utility_function_dict()
    utility_functions_final_period = create_final_period_utility_function_dict()

    # =================================================================================
    # Discrete experience
    # =================================================================================

    state_space_functions_discrete = {
        "get_next_period_state": get_next_period_state,
        "get_state_specific_feasible_choice_set": get_state_specific_feasible_choice_set,
    }

    model_discrete = setup_model(
        options=OPTIONS_DISCRETE_EXP,
        exog_grids=(exog_savings_grid,),
        state_space_functions=state_space_functions_discrete,
        utility_functions=utility_functions,
        utility_functions_final_period=utility_functions_final_period,
        budget_constraint=budget_constraint_discrete,
    )
    value_discrete, policy_discrete, endog_grid_discrete = solve_dcegm(
        PARAMS,
        OPTIONS_DISCRETE_EXP,
        exog_grids=(exog_savings_grid,),
        state_space_functions=state_space_functions_discrete,
        utility_functions=utility_functions,
        utility_functions_final_period=utility_functions_final_period,
        budget_constraint=budget_constraint_discrete,
    )

    state_choice_space_discrete = model_discrete["model_structure"][
        "state_choice_space"
    ]

    # =================================================================================
    # Continuous experience
    # =================================================================================

    state_space_functions_continuous = {
        "get_next_period_state": get_next_period_discrete_state,
        "update_continuous_state": get_next_period_experience,
        "get_state_specific_feasible_choice_set": get_state_specific_feasible_choice_set,
    }

    model_cont = setup_model(
        options=OPTIONS_CONTINUOUS_EXP,
        exog_grids=(exog_savings_grid, jnp.linspace(0, 1, EXPERIENCE_GRID_POINTS)),
        state_space_functions=state_space_functions_continuous,
        utility_functions=utility_functions,
        utility_functions_final_period=utility_functions_final_period,
        budget_constraint=budget_constraint_continuous,
    )
    value_cont, policy_cont, endog_grid_cont = solve_dcegm(
        PARAMS,
        OPTIONS_CONTINUOUS_EXP,
        exog_grids=(exog_savings_grid, jnp.linspace(0, 1, EXPERIENCE_GRID_POINTS)),
        state_space_functions=state_space_functions_continuous,
        utility_functions=utility_functions,
        utility_functions_final_period=utility_functions_final_period,
        budget_constraint=budget_constraint_continuous,
    )

    state_choice_space_cont = model_cont["model_structure"]["state_choice_space"]

    # pick example where agent worked less than t periods

    where_experience = model_discrete["model_structure"]["state_space_names"].index(
        "experience"
    )

    # idx_discrete = state_choice_space_discrete[state_choice_space_discrete[:, 0] == 15]
    idx_discrete = state_choice_space_discrete[
        (state_choice_space_discrete[:, 0] == 15)
        & (state_choice_space_discrete[:, where_experience] == 10)
    ]
    idx_cont = state_choice_space_cont[state_choice_space_cont[:, 0] == 15]
    # idx_continuous = state_choice_space_discrete.shape[1] - 1

    exp = 10
    exp_share = exp / 15
    val_disc = value_discrete[idx_discrete[-1]]

    val_cont = value_cont[idx_cont[-1]]

    breakpoint()
