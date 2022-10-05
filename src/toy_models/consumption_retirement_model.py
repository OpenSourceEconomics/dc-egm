"""Model specific utility, wealth, and value functions."""
from typing import Callable
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


def marginal_utility_crra(consumption: np.ndarray, params: pd.DataFrame) -> np.ndarray:
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
    beta = params.loc[("beta", "beta"), "value"]

    inverse_marginal_utility = (marginal_utility * beta) ** (-1 / theta)

    return inverse_marginal_utility


def calc_next_period_wealth_matrices(
    child_state,
    savings: np.ndarray,
    params: pd.DataFrame,
    options: Dict[str, int],
    compute_income: Callable,
) -> np.ndarray:
    """Computes all possible levels of next period (marginal) wealth M_(t+1).

    Args:
        child_state (np.ndarray): 1d array of shape (n_state_variables,) denoting
            the current child state.
        savings (np.ndarray): 1d array of shape (n_grid_wealth,) containing the
            exogenous savings grid.
        params (pd.DataFrame): Model parameters indexed with multi-index of the
            form ("category", "name") and two columns ["value", "comment"].
        options (dict): Options dictionary.
        compute_income (callable): User-defined function to calculate the agent's
            end-of-period (labor) income, where the inputs ```quad_points```,
                ```params``` and ```options``` are already partialled in.

    Returns:
        (np.ndarray): 2d array of shape (n_quad_stochastic, n_grid_wealth)
            containing all possible next period wealths.
    """
    r = params.loc[("assets", "interest_rate"), "value"]
    n_grid_wealth = options["grid_points_wealth"]
    n_quad_stochastic = options["quadrature_points_stochastic"]

    # Calculate stochastic labor income
    _next_period_income = compute_income(child_state)
    income_matrix = np.repeat(_next_period_income[:, np.newaxis], n_grid_wealth, 1)
    savings_matrix = np.full((n_quad_stochastic, n_grid_wealth), savings * (1 + r))

    matrix_next_period_wealth = income_matrix + savings_matrix

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
        expected_value (np.ndarray): Expected value of next period. Array of
            shape (n_grid_wealth,).
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


# def wage_systematic(state, params, options):


def calc_stochastic_income(
    child_state: int,
    wage_shock: np.ndarray,
    params: pd.DataFrame,
    options: Dict[str, int],
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
        child_state (np.ndarray): 1d array of shape (n_state_variables,) denoting
            the current child state.
        wage_shock (float): Stochastic shock on labor income, which may or may not
            be normally distributed.
        params (pd.DataFrame): Model parameters indexed with multi-index of the
            form ("category", "name") and two columns ["value", "comment"].
            Relevant here are the coefficients of the wage equation.
        options (dict): Options dictionary.

    Returns:
        stochastic_income (np.ndarray): 1d array of shape (n_quad_points,) containing
            potential end of period incomes. It consists of a deterministic component,
            i.e. age-dependent labor income, and a stochastic shock.
    """
    if child_state[1] == 0:  # working
        # For simplicity, assume current_age - min_age = experience
        min_age = options["min_age"]
        age = child_state[0] + min_age

        # Determinisctic component of income depending on experience:
        # constant + alpha_1 * age + alpha_2 * age**2
        exp_coeffs = np.asarray(params.loc["wage", "value"])
        labor_income = exp_coeffs @ (age ** np.arange(len(exp_coeffs)))

        stochastic_income = np.exp(labor_income + wage_shock)

    elif child_state[1] == 1:  # retired
        stochastic_income = np.zeros_like(wage_shock)

    return stochastic_income


def calc_next_period_marginal_wealth(state, params, options):
    """Calculate next periods marginal wealth.

    Args:
        child_state (np.ndarray): 1d array of shape (n_state_variables,) denoting
            the current child state.
        params (pd.DataFrame): Model parameters indexed with multi-index of the
            form ("category", "name") and two columns ["value", "comment"].
        options (dict): Options dictionary.

    Returns:
         (np.ndarray): 2d array of shape (n_quad_stochastic, n_grid_wealth)
            containing all possible next marginal period wealths.

    """
    r = params.loc[("assets", "interest_rate"), "value"]
    n_grid_wealth = options["grid_points_wealth"]
    n_quad_stochastic = options["quadrature_points_stochastic"]

    out = np.full((n_quad_stochastic, n_grid_wealth), (1 + r))

    return out
