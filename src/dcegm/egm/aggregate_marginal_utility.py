from typing import Tuple

import jax.numpy as jnp
import numpy as np


def aggregate_marg_utils_and_exp_values(
    value_state_choice_specific: jnp.ndarray,
    marg_util_state_choice_specific: jnp.ndarray,
    reshape_state_choice_vec_to_mat: np.ndarray,
    taste_shock_scale: float,
    income_shock_weights: jnp.ndarray,
) -> Tuple[jnp.ndarray, jnp.ndarray]:
    """Compute the aggregate marginal utilities and expected values.

    Args:
        value_state_choice_specific (jnp.ndarray): 3d array of shape
            (n_states * n_choices, n_exog_savings, n_income_shocks) of the value
            function for all state-choice combinations and income shocks.
        marg_util_state_choice_specific (jnp.ndarray): 3d array of shape
            (n_states * n_choices, n_exog_savings, n_income_shocks) of the marginal
            utility of consumption for all states-choice combinations and
            income shocks.
        reshape_state_choice_vec_to_mat (np.ndarray): 2d array of shape
            (n_states_current, n_choices_current) that reshapes the current period
            vector of feasible state-choice combinations to a matrix of shape
            (n_choices, n_choices).
        taste_shock_scale (float): The taste shock scale.
        income_shock_weights (jnp.ndarray): 1d array of shape
            (n_stochastic_quad_points,) containing the weights of the income shock
            quadrature.

    Returns:
        tuple:

        - marg_util (np.ndarray): 2d array of shape (n_states, n_exog_savings)
            of the state-specific aggregate marginal utilities.
        - expected_value (np.ndarray): 2d array of shape (n_states, n_exog_savings)
            of the state-specific aggregate expected values.

    """
    choice_values_per_state = jnp.take(
        value_state_choice_specific,
        reshape_state_choice_vec_to_mat,
        axis=0,
        mode="fill",
        fill_value=jnp.nan,
    )
    max_value_per_state = jnp.nanmax(choice_values_per_state, axis=1, keepdims=True)

    rescale_values_per_state = choice_values_per_state - max_value_per_state

    rescaled_exponential = jnp.exp(rescale_values_per_state / taste_shock_scale)

    sum_exp = jnp.nansum(rescaled_exponential, axis=1, keepdims=True)

    log_sum_unsqueezed = max_value_per_state + taste_shock_scale * jnp.log(sum_exp)
    # Because we kept the dimensions in the maximum and sum over choice specific objects
    # to perform subtraction and division, we now need to squeeze the log_sum again
    # to remove the redundant axis.
    log_sum = jnp.squeeze(log_sum_unsqueezed, axis=1)
    choice_probs = rescaled_exponential / sum_exp

    choice_marg_util_per_state = jnp.take(
        marg_util_state_choice_specific,
        reshape_state_choice_vec_to_mat,
        axis=0,
        mode="fill",
        fill_value=jnp.nan,
    )

    weighted_marg_util = choice_probs * choice_marg_util_per_state
    marg_util = jnp.nansum(weighted_marg_util, axis=1)

    shock_integrated_marg_util = marg_util @ income_shock_weights
    shock_integrated_log_sum = log_sum @ income_shock_weights

    return shock_integrated_marg_util, shock_integrated_log_sum
