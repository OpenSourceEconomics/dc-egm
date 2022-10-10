from typing import Callable
from typing import Dict

import numpy as np
import pandas as pd


def calc_current_period_policy(
    next_period_marginal_utility: np.ndarray,
    next_period_marginal_wealth: np.ndarray,
    quad_weights: np.ndarray,
    compute_inverse_marginal_utility: Callable,
) -> np.ndarray:
    """Computes the current period policy.

    Args:
        next_period_marginal_utility (np.ndarray): Array of next period's
            marginal utility of shape (n_quad_stochastic, n_grid_wealth,).
        next_period_marginal_wealth (np.ndarray): Array of all possible next period
            marginal wealths. Also of shape (n_quad_stochastic, n_grid_wealth)
        quad_weights (np.ndarray): Weights associated with the quadrature points
            of shape (n_quad_stochastic,). Used for integration over the
            stochastic income component in the Euler equation.
        compute_value_credit_constrained (callable): User-defined function to compute
            the agent's inverse marginal utility.
            The input ```params``` is already partialled in.

    Returns:
        (np.ndarray): 1d array of shape (n_grid_wealth,) containing the current
            period's policy rule.
    """
    # RHS of Euler Eq., p. 337 IJRS (2017)
    # Integrate out uncertainty over stochastic income y
    rhs_euler = quad_weights @ (
        next_period_marginal_utility * next_period_marginal_wealth
    )

    current_period_policy = compute_inverse_marginal_utility(rhs_euler)

    return current_period_policy


def calc_expected_value(
    matrix_next_period_wealth: np.ndarray,
    next_period_value: np.ndarray,
    quad_weights: np.ndarray,
    params: pd.DataFrame,
) -> np.ndarray:
    """Computes the expected value of the next period.

    Args:
        matrix_next_period_wealth (np.ndarray): Array of all possible next period
            wealths with shape (n_quad_stochastic, n_grid_wealth).
        next_period_value (np.ndarray): Array containing values of next period
            choice-specific value function.
            Shape (n_choices, n_quad_stochastic * n_grid_wealth).
        quad_weights (np.ndarray): Weights associated with the stochastic
            quadrature points of shape (n_quad_stochastic,).
        params (pd.DataFrame): Model parameters indexed with multi-index of the
            form ("category", "name") and two columns ["value", "comment"].

    Returns:
        (np.ndarray): 1d array of the agent's expected value of the next period.
            Shape (n_grid_wealth,).
    """
    log_sum = _calc_log_sum(
        next_period_value, lambda_=params.loc[("shocks", "lambda"), "value"]
    )

    expected_value = quad_weights @ log_sum.reshape(
        matrix_next_period_wealth.shape, order="F"
    )
    return expected_value


def calc_value_constrained(
    wealth: np.ndarray,
    next_period_value: np.ndarray,
    choice: int,
    beta: float,
    compute_utility: Callable,
) -> np.ndarray:
    """Compute the agent's value in the credit constrained region.

    Args:
        compute_utility (callable): User-defined function to compute the agent's
            utility. The input ``params``` is already partialled in.

    """
    utility = compute_utility(wealth, choice)
    value_constrained = utility + beta * next_period_value

    return value_constrained


def calc_next_period_choice_probs(
    next_period_value: np.ndarray,
    choice: int,
    params: pd.DataFrame,
    options: Dict[str, int],
) -> np.ndarray:
    """Calculates the probability of working in the next period.

    Args:
        next_period_value (np.ndarray): Array containing values of next period
            choice-specific value function.
            Shape (n_choices, n_quad_stochastic * n_grid_wealth).
        choice (int): State of the agent, e.g. 0 = "retirement", 1 = "working".
        params (pd.DataFrame): Model parameters indexed with multi-index of the
            form ("category", "name") and two columns ["value", "comment"].
        options (dict): Options dictionary.

    Returns:
        prob_working (np.ndarray): Probability of working next period. Array of
            shape (n_quad_stochastic * n_grid_wealth,).
    """
    # Taste shock (scale) parameter
    lambda_ = params.loc[("shocks", "lambda"), "value"]

    col_max = np.amax(next_period_value, axis=0)
    next_period_value_ = next_period_value - col_max

    # Eq. (15), p. 334 IJRS (2017)
    choice_prob = np.exp(next_period_value_[choice, :] / lambda_) / np.sum(
        np.exp(next_period_value_ / lambda_), axis=0
    )

    return choice_prob


def _calc_log_sum(next_period_value: np.ndarray, lambda_: float) -> np.ndarray:
    """Calculates the log-sum needed for computing the expected value function.

    The log-sum formula may also be referred to as the 'smoothed max function',
    see eq. (50), p. 335 (Appendix).

    Args:
        next_period_value (np.ndarray): Array containing values of next period
            choice-specific value function.
            Shape (n_choices, n_quad_stochastic * n_grid_wealth).
        lambda_ (float): Taste shock (scale) parameter.

    Returns:
        logsum (np.ndarray): Log-sum formula inside the expected value function.
            Array of shape (n_quad_stochastic * n_grid_wealth,).
    """
    col_max = np.amax(next_period_value, axis=0)
    next_period_value_ = next_period_value - col_max

    # Eq. (14), p. 334 IJRS (2017)
    logsum = col_max + lambda_ * np.log(
        np.sum(np.exp((next_period_value_) / lambda_), axis=0)
    )

    return logsum