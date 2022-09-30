"""Model specific utility, wealth, and value functions."""
from typing import Dict

import numpy as np
import pandas as pd


def utility_func_crra(
    consumption: np.ndarray, choice: int, params: pd.DataFrame
) -> np.ndarray:
    """Computes the agent's current utility based on a CRRA utility function.

    Args:
        consumption (np.ndarray): Level of the agent's consumption.
            Array of shape (i) (n_quad_stochastic * n_grid_wealth,)
            when called by :func:`~dcgm.call_egm_step.map_exog_to_endog_grid`
            and :func:`~dcgm.call_egm_step.get_next_period_value`, or
            (ii) of shape (n_grid_wealth,) when called by
            :func:`~dcgm.call_egm_step.get_current_period_value`.
        choice (int): Choice of the agent, e.g. 0 = "retirement", 1 = "working".
        params (pd.DataFrame): Model parameters indexed with multi-index of the
            form ("category", "name") and two columns ["value", "comment"].
            Relevant here is the CRRA coefficient theta.

    Returns:
        utility (np.ndarray): Agent's utility . Array of shape
            (n_quad_stochastic * n_grid_wealth,) or (n_grid_wealth,).
    """
    theta = params.loc[("utility_function", "theta"), "value"]
    delta = params.loc[("delta", "delta"), "value"]

    if theta == 1:
        utility_consumption = np.log(consumption)
    else:
        utility_consumption = (consumption ** (1 - theta) - 1) / (1 - theta)

    utility = utility_consumption - (1 - choice) * delta

    return utility


def inverse_marginal_utility_crra(
    marginal_utility: np.ndarray,
    params: pd.DataFrame,
) -> np.ndarray:
    """Computes the inverse marginal utility of a CRRA utility function.

    Args:
        marginal_utility (np.ndarray): Level of marginal CRRA utility.
            Array of shape (n_grid_wealth,).
        params (pd.DataFrame): Model parameters indexed with multi-index of the
            form ("category", "name") and two columns ["value", "comment"].

    Returns:
        inverse_marginal_utility(np.ndarray): Inverse of the marginal utility of
            a CRRA consumption function. Array of shape (n_grid_wealth,).
    """
    theta = params.loc[("utility_function", "theta"), "value"]
    inverse_marginal_utility = marginal_utility ** (-1 / theta)

    return inverse_marginal_utility


def compute_next_period_marginal_utility(
    child_node_choice_set,
    next_period_consumption: np.ndarray,
    next_period_value: np.ndarray,
    params: pd.DataFrame,
    options: Dict[str, int],
) -> np.ndarray:
    """Computes the marginal utility of the next period.

    Args:
        choice (int): State of the agent, e.g. 0 = "retirement", 1 = "working".
        next_period_consumption (np.ndarray): Array of next period consumption
            of shape (n_choices, n_quad_stochastic * n_grid_wealth). Contains
            interpolated values.
        next_period_value (np.ndarray): Array containing values of next period
            choice-specific value function.
            Shape (n_choices, n_quad_stochastic * n_grid_wealth).
        params (pd.DataFrame): Model parameters indexed with multi-index of the
            form ("category", "name") and two columns ["value", "comment"].
        options (dict): Options dictionary.

    Returns:
        next_period_marg_util (np.ndarray): Array of next period's
            marginal utility of shape (n_quad_stochastic * n_grid_wealth,).
    """

    next_period_marg_util = np.zeros_like(next_period_consumption[0, :])
    for choice_index in range(child_node_choice_set.shape[0]):
        choice_prob = _calc_next_period_choice_probs(
            next_period_value, choice_index, params, options
        )
        next_period_marg_util += choice_prob * _marginal_utility_crra(
            next_period_consumption[choice_index, :], params
        )

    return next_period_marg_util


def compute_expected_value(
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
        expected_value (np.ndarray): Expected value of next period. Array of
            shape (n_grid_wealth,).
    """
    # Taste shock (scale) parameter
    lambda_ = params.loc[("shocks", "lambda"), "value"]

    expected_value = np.dot(
        quad_weights.T,
        _calc_logsum(next_period_value, lambda_).reshape(
            matrix_next_period_wealth.shape, order="F"
        ),
    )
    return expected_value


def _marginal_utility_crra(consumption: np.ndarray, params: pd.DataFrame) -> np.ndarray:
    """Computes marginal utility of CRRA utility function.

    Args:
        consumption (np.ndarray): Level of the agent's consumption.
            Array of shape (n_quad_stochastic * n_grid_wealth,).
        params (pd.DataFrame): Model parameters indexed with multi-index of the
            form ("category", "name") and two columns ["value", "comment"].
            Relevant here is the CRRA coefficient theta.

    Returns:
        marginal_utility (np.ndarray): Marginal utility of CRRA consumption
            function. Array of shape (n_quad_stochastic * n_grid_wealth,).
    """
    theta = params.loc[("utility_function", "theta"), "value"]
    marginal_utility = consumption ** (-theta)

    return marginal_utility


def _calc_next_period_choice_probs(
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

    # Eq. (15), p. 334 IJRS (2017
    prob_working = np.exp(next_period_value_[choice, :] / lambda_) / np.sum(
        np.exp(next_period_value_ / lambda_), axis=0
    )

    return prob_working


def _calc_logsum(next_period_value: np.ndarray, lambda_: float) -> np.ndarray:
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


def get_next_period_wealth_matrices(
    child_state,
    savings: np.ndarray,
    quad_points: np.ndarray,
    params: pd.DataFrame,
    options: Dict[str, int],
) -> np.ndarray:
    """Computes all possible levels of next period (marginal) wealth M_(t+1).

    Args:
        child_state (np.ndarray): Current individual child state.
        savings (np.ndarray): Array of shape (n_grid_wealth,) containing the
            exogenous savings grid.
        quad_points (np.ndarray): Array of shape (n_quad_stochastic,)
            containing (normally distributed) stochastic income components,
            which induce shocks to the wage equation.
        params (pd.DataFrame): Model parameters indexed with multi-index of the
            form ("category", "name") and two columns ["value", "comment"].
        options (dict): Options dictionary.
    Returns:
        (tuple): Tuple containing
        - matrix_next_period_wealth (np.ndarray): Array of all possible next period
            wealths with shape (n_quad_stochastic, n_grid_wealth).
    """
    r = params.loc[("assets", "interest_rate"), "value"]

    n_grid_wealth = options["grid_points_wealth"]
    n_quad_stochastic = options["quadrature_points_stochastic"]

    # Calculate stochastic labor income
    next_period_income = _calc_stochastic_income(
        child_state[0], quad_points, params=params, options=options
    )

    matrix_next_period_wealth = np.full(
        (n_grid_wealth, n_quad_stochastic),
        next_period_income * (1 - child_state[1]),
    ).T + np.full((n_quad_stochastic, n_grid_wealth), savings * (1 + r))

    # Retirement safety net, only in retirement model
    consump_floor_index = ("assets", "consumption_floor")
    if (
        consump_floor_index in params.index
        or params.loc[consump_floor_index, "value"] > 0
    ):
        consump_floor = params.loc[consump_floor_index, "value"]

        matrix_next_period_wealth[
            matrix_next_period_wealth < consump_floor
        ] = consump_floor

    return matrix_next_period_wealth


# def wage_systematic(state, params, options):


def calc_next_period_marginal_wealth(state, params, options):
    """
    Calculate next periods marginal wealth.
    Args:
        child_state (np.ndarray): Current individual child state.
        params (pd.DataFrame): Model parameters indexed with multi-index of the
            form ("category", "name") and two columns ["value", "comment"].
        options (dict): Options dictionary.

    Returns:
        - next_period_marginal_wealth (np.ndarray): Array of all possible next period
            marginal wealths. Also of shape (n_quad_stochastic, n_grid_wealth).

    """
    r = params.loc[("assets", "interest_rate"), "value"]
    n_grid_wealth = options["grid_points_wealth"]
    n_quad_stochastic = options["quadrature_points_stochastic"]

    out = np.full((n_quad_stochastic, n_grid_wealth), (1 + r))

    return out


def _calc_stochastic_income(
    period: int, shock: np.ndarray, params: pd.DataFrame, options: Dict[str, int]
) -> float:
    """Computes the current level of deterministic and stochastic income.

    Note that income is paid at the end of the current period, i.e. after
    the (potential) labor supply choice has been made. This is equivalent to
    allowing income to be dependent on a lagged choice of labor supply.
    The agent starts working in period t = 0.
    Relevant for the wage equation (deterministic income) are age-dependent
    coefficients of work experience:
    labor_income = constant + alpha_1 * age + alpha_2 * age**2
    They include a constant as well as two coefficients on age and age squared,
    respectively. Note that the last one (alpha_2) typically has a negative sign.

    Args:
        period (int): Current period t.
        shock (float): Stochastic shock on labor income, which may or may not
            be normally distributed.
        params (pd.DataFrame): Model parameters indexed with multi-index of the
            form ("category", "name") and two columns ["value", "comment"].
            Relevant here are the coefficients of the wage equation.
        options (dict): Options dictionary.

    Returns:
        stochastic_income (float): End of period income composed of a
            deterministic component, i.e. age-dependent labor income, and a
            stochastic shock.
    """
    # For simplicity, assume current_age - min_age = experience
    min_age = options["min_age"]
    age = period + min_age

    # Determinisctic component of income depending on experience:
    # constant + alpha_1 * age + alpha_2 * age**2
    exp_coeffs = np.asarray(params.loc["wage", "value"])
    labor_income = exp_coeffs @ (age ** np.arange(len(exp_coeffs)))

    stochastic_income = np.exp(labor_income + shock)

    return stochastic_income