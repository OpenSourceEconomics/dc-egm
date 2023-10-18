from typing import Callable
from typing import Dict
from typing import Tuple

import jax.numpy as jnp
from jax import vmap

"""Wrapper function to solve the final period of the model."""


def solve_final_period(
    state_objects_final_period: Dict[str, jnp.ndarray],
    compute_final_period: Callable,
    resources_beginning_of_period: jnp.ndarray,
    params: Dict[str, float],
) -> Tuple[
    jnp.ndarray, jnp.ndarray, jnp.ndarray, jnp.ndarray, jnp.ndarray, jnp.ndarray
]:
    """Computes solution to final period for policy and value function.
    In the last period, everything is consumed, i.e. consumption = savings.
    Args:


    Returns:
        tuple:
        - marginal_utilities_choices (np.ndarray): 3d array of shape
            (n_states, n_grid_wealth, n_income_shocks) of the marginal utility of
            consumption for all final states, end of period assets, and
            income shocks.
        - final_value (np.ndarray): 3d array of shape
            (n_states, n_grid_wealth, n_income_shocks) of the optimal
            value function for all final states, end of period assets, and
            income shocks.
        - final_policy (np.ndarray): 3d array of shape
            (n_states, n_grid_wealth, n_income_shocks) of the optimal
            policy for all final states, end of period assets, and
            income shocks.
    """

    resources_final_period = resources_beginning_of_period[
        state_objects_final_period["idx_parent_states"]
    ]

    # Calculate the final period solution for each gridpoint
    marg_util_interpolated, value_interpolated = vmap(
        vmap(
            vmap(
                calculate_final_period_solution_for_each_gridpoint,
                in_axes=(None, 0, None, None),
            ),
            in_axes=(None, 0, None, None),
        ),
        in_axes=(0, 0, None, None),
    )(
        state_objects_final_period["state_choice_mat"],
        resources_final_period,
        params,
        compute_final_period,
    )

    # Choose which draw we take for policy and value function as those are not
    # saved with respect to the draws
    middle_of_draws = int(value_interpolated.shape[2] + 1 / 2)

    value_calc = value_interpolated[:, :, middle_of_draws]
    # The policy in the last period is eat it all. Either as bequest or by consuming.
    # The user defines this by the bequest functions.
    resources_to_save = resources_final_period[:, :, middle_of_draws]
    nans_to_add = jnp.full(
        (resources_to_save.shape[0], int(resources_to_save.shape[1] * 0.2)), jnp.nan
    )
    policy_left = policy_right = endog_grid = jnp.append(
        resources_to_save,
        nans_to_add,
        axis=1,
    )
    value_final = jnp.append(value_calc, nans_to_add, axis=1)

    return (
        value_final,
        policy_left,
        policy_right,
        endog_grid,
        marg_util_interpolated,
        value_interpolated,
    )


def calculate_final_period_solution_for_each_gridpoint(
    state_choice_vec, resources, params, compute_final_period
):
    marg_util_interpolated, value_interpolated, _ = compute_final_period(
        **state_choice_vec,
        begin_of_period_resources=resources,
        params=params,
    )
    return marg_util_interpolated, value_interpolated
