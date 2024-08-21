from typing import Callable, Dict, Tuple

from jax import numpy as jnp
from jax import vmap

from dcegm.interpolation.interp1d import interp1d_policy_and_value_on_wealth
from dcegm.interpolation.interp2d import (
    interp2d_policy_and_value_on_wealth_and_regular_grid,
)


def interpolate_value_and_marg_util(
    compute_marginal_utility: Callable,
    compute_utility: Callable,
    state_choice_vec: Dict[str, int],
    exog_grids: Tuple[jnp.ndarray, jnp.ndarray],
    wealth_and_continuous_state_next: jnp.ndarray,
    endog_grid_child_state_choice: jnp.ndarray,
    policy_child_state_choice: jnp.ndarray,
    value_child_state_choice: jnp.ndarray,
    has_second_continuous_state: bool,
    params: Dict[str, float],
) -> Tuple[jnp.ndarray, jnp.ndarray]:
    """Interpolate value and policy for all child states and compute marginal utility.

    Args:
        compute_marginal_utility (callable): User-defined function to compute the
            agent's marginal utility of consumption.
        compute_utility (callable): Function for calculating the utility of consumption.
        state_choice_vec (dict): Dictionary containing the state and choice of the agent.
        wealth_beginning_of_next_period (jnp.ndarray): 2d array of shape
            (n_quad_stochastic, n_grid_wealth,) containing the agent's beginning of
            period wealth.
        endog_grid_child_state_choice (jnp.ndarray): 1d array containing the endogenous
            wealth grid of the child state/choice pair. Shape (n_grid_wealth,).
        policy_child_state_choice (jnp.ndarray): 1d array containing the
            corresponding policy function values of the endogenous wealth grid of the
            child state/choice pair. Shape (n_grid_wealth,).
        value_child_state_choice (jnp.ndarray): 1d array containing the
            corresponding value function values of the endogenous wealth grid of the
            child state/choice pair. Shape (n_grid_wealth,).
        has_second_continuous_state (bool): Boolean indicating whether the model
            features a second continuous state variable. If False, the only
            continuous state variable is consumption/savings.
        params (dict): Dictionary containing the model parameters.

    Returns:
        tuple:

        - value_interp (jnp.ndarray): 2d array of shape (n_wealth_grid, n_income_shocks)
            containing the interpolated value function.
        - marg_util_interp (jnp.ndarray): 2d array of shape (n_wealth_grid, n_income_shocks)
            containing the interpolated marginal utilities for each wealth level and
            income shock.

    """

    if has_second_continuous_state:
        wealth_next, continuous_state_next = wealth_and_continuous_state_next
        regular_grid = exog_grids[1]

        # interp_for_single_state_choice = vmap(
        #     interp2d_value_and_marg_util_for_state_choice,
        #     in_axes=(None, None, 0, 0, 0, 0, 0, 0, None),
        # )
        # interp_for_single_state_choice = vmap(
        #     interp_for_single_state_choice, in_axes=(None, None, 0, 1, 1, 0, 0, 0, None)
        # )

        interp_for_single_state_choice = vmap(
            vmap(
                interp2d_value_and_marg_util_for_state_choice,
                in_axes=(None, None, None, 0, 0, 0, 0, 0, 0, None),  # state-choice
            ),
            in_axes=(None, None, None, 0, 1, 1, 0, 0, 0, None),  # continuous state
        )

        return interp_for_single_state_choice(
            compute_marginal_utility,
            compute_utility,
            state_choice_vec,
            regular_grid,
            wealth_next,
            continuous_state_next,
            endog_grid_child_state_choice,
            policy_child_state_choice,
            value_child_state_choice,
            params,
        )

    else:
        interp_for_single_state_choice = vmap(
            interp1d_value_and_marg_util_for_state_choice,
            in_axes=(None, None, 0, 0, 0, 0, 0, None),
        )

        return interp_for_single_state_choice(
            compute_marginal_utility,
            compute_utility,
            state_choice_vec,
            wealth_and_continuous_state_next,
            endog_grid_child_state_choice,
            policy_child_state_choice,
            value_child_state_choice,
            params,
        )


def interp1d_value_and_marg_util_for_state_choice(
    compute_marginal_utility: Callable,
    compute_utility: Callable,
    state_choice_vec: Dict[str, int],
    wealth_beginning_of_next_period: jnp.ndarray,
    endog_grid_child_state_choice: jnp.ndarray,
    policy_child_state_choice: jnp.ndarray,
    value_child_state_choice: jnp.ndarray,
    params: Dict[str, float],
) -> Tuple[jnp.ndarray, jnp.ndarray]:
    """Interpolate value and policy for given child state and compute marginal utility.

    Args:
        compute_marginal_utility (callable): User-defined function to compute the
            agent's marginal utility of consumption.
        compute_utility (callable): Function for calculating the utility of consumption.
        state_choice_vec (dict): Dictionary containing the state and choice of the agent.
        wealth_beginning_of_next_period (jnp.ndarray): 2d array of shape
            (n_quad_stochastic, n_grid_wealth,) containing the agent's beginning of
            period wealth.
        endog_grid_child_state_choice (jnp.ndarray): 1d array containing the endogenous
            wealth grid of the child state/choice pair. Shape (n_grid_wealth,).
        policy_child_state_choice (jnp.ndarray): 1d array containing the
            corresponding policy function values of the endogenous wealth grid of the
            child state/choice pair. Shape (n_grid_wealth,).
        value_child_state_choice (jnp.ndarray): 1d array containing the
            corresponding value function values of the endogenous wealth grid of the
            child state/choice pair. Shape (n_grid_wealth,).
        has_second_continuous_state (bool): Boolean indicating whether the model
            features a second continuous state variable. If False, the only
            continuous state variable is consumption/savings.
        params (dict): Dictionary containing the model parameters.

    Returns:
        tuple:

        - marg_utils (jnp.ndarray): 2d array of shape (n_wealth_grid, n_income_shocks)
            containing the interpolated marginal utilities for each wealth level and
            income shock.
        - value_interp (jnp.ndarray): 2d array of shape (n_wealth_grid, n_income_shocks)
            containing the interpolated value function.

    """

    def interp_on_single_wealth_point(wealth_point):
        policy_interp, value_interp = interp1d_policy_and_value_on_wealth(
            wealth=wealth_point,
            endog_grid=endog_grid_child_state_choice,
            policy=policy_child_state_choice,
            value=value_child_state_choice,
            compute_utility=compute_utility,
            state_choice_vec=state_choice_vec,
            params=params,
        )
        marg_util_interp = compute_marginal_utility(
            consumption=policy_interp, params=params, **state_choice_vec
        )

        return value_interp, marg_util_interp

    interp_over_single_wealth_and_income_shock_draw = vmap(  # outer: income shocks
        vmap(interp_on_single_wealth_point)  # inner: wealth
    )

    value_interp, marg_util_interp = interp_over_single_wealth_and_income_shock_draw(
        wealth_beginning_of_next_period
    )

    return value_interp, marg_util_interp


def interp2d_value_and_marg_util_for_state_choice(
    compute_marginal_utility: Callable,
    compute_utility: Callable,
    state_choice_vec: Dict[str, int],
    wealth_beginning_of_next_period: jnp.ndarray,
    # regular_grid_child_state_choice: jnp.ndarray,
    endog_grid_child_state_choice: jnp.ndarray,
    policy_child_state_choice: jnp.ndarray,
    value_child_state_choice: jnp.ndarray,
    has_second_continuous_state: bool,
    params: Dict[str, float],
) -> Tuple[jnp.ndarray, jnp.ndarray]:
    """Interpolate value and policy for given child state and compute marginal utility.

    Args:
        compute_marginal_utility (callable): User-defined function to compute the
            agent's marginal utility of consumption.
        compute_utility (callable): Function for calculating the utility of consumption.
        state_choice_vec (dict): Dictionary containing the state and choice of the agent.
        wealth_beginning_of_next_period (jnp.ndarray): 2d array of shape
            (n_quad_stochastic, n_grid_wealth,) containing the agent's beginning of
            period wealth.
        endog_grid_child_state_choice (jnp.ndarray): 1d array containing the endogenous
            wealth grid of the child state/choice pair. Shape (n_grid_wealth,).
        policy_child_state_choice (jnp.ndarray): 1d array containing the
            corresponding policy function values of the endogenous wealth grid of the
            child state/choice pair. Shape (n_grid_wealth,).
        value_child_state_choice (jnp.ndarray): 1d array containing the
            corresponding value function values of the endogenous wealth grid of the
            child state/choice pair. Shape (n_grid_wealth,).
        has_second_continuous_state (bool): Boolean indicating whether the model
            features a second continuous state variable. If False, the only
            continuous state variable is consumption/savings.
        params (dict): Dictionary containing the model parameters.

    Returns:
        tuple:

        - marg_utils (jnp.ndarray): 2d array of shape (n_wealth_grid, n_income_shocks)
            containing the interpolated marginal utilities for each wealth level and
            income shock.
        - value_interp (jnp.ndarray): 2d array of shape (n_wealth_grid, n_income_shocks)
            containing the interpolated value function.

    """

    def interp_on_single_wealth_point(regular_point, wealth_point):

        # regular_grid_child_state_choice = endog_grid_child_state_choice[]

        # To-Do: Add second vmap for regular grid point

        policy_interp, value_interp = (
            interp2d_policy_and_value_on_wealth_and_regular_grid(
                # regular_grid=regular_grid_child_state_choice,
                wealth_grid=endog_grid_child_state_choice,
                policy_grid=policy_child_state_choice,
                value_grid=value_child_state_choice,
                wealth_point_to_interp=wealth_point,
                regular_point_to_interp=regular_point,
                compute_utility=compute_utility,
                state_choice_vec=state_choice_vec,
                params=params,
            )
        )
        marg_util_interp = compute_marginal_utility(
            consumption=policy_interp, params=params, **state_choice_vec
        )

        return value_interp, marg_util_interp

    interp_over_single_wealth_and_income_shock_draw = vmap(  # income shocks
        vmap(vmap(interp_on_single_wealth_point))  # wealth, regular grid
    )

    # To-Do: Interpolate over next period regular and wealth point
    # Old points regular grid and endog grid
    # New points: continuous state next period and wealth next period
    value_interp, marg_util_interp = interp_over_single_wealth_and_income_shock_draw(
        wealth_beginning_of_next_period
    )

    return value_interp, marg_util_interp
