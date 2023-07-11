"""Extension of the Fast Upper-Envelope Scan.

The original algorithm is based on Loretti I. Dobrescu and Akshay Shanker (2022) 'Fast
Upper-Envelope Scan for Solving Dynamic Optimization Problems',
https://dx.doi.org/10.2139/ssrn.4181302

"""
from typing import Callable
from typing import Optional
from typing import Tuple

import jax.numpy as jnp  # noqa: F401
import numpy as np
from jax import jit  # noqa: F401
from numba import njit


def fast_upper_envelope_wrapper(
    endog_grid: np.ndarray,
    policy: np.ndarray,
    value: np.ndarray,
    exog_grid: np.ndarray,
    expected_value_zero_savings: float,
    choice: int,
    compute_value: Callable,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Drop suboptimal points and refine the endogenous grid, policy, and value.

    Computes the upper envelope over the overlapping segments of the
    decision-specific value functions, which in fact are value "correspondences"
    in this case, where multiple solutions are detected. The dominated grid
    points are then eliminated from the endogenous wealth grid.
    Discrete choices introduce kinks and non-concave regions in the value
    function that lead to discontinuities in the policy function of the
    continuous (consumption) choice. In particular, the value function has a
    non-concave region where the decision-specific values of the
    alternative discrete choices (e.g. continued work or retirement) cross.
    These are referred to as "primary" kinks.
    As a result, multiple local optima for consumption emerge and the Euler
    equation has multiple solutions.
    Moreover, these "primary" kinks propagate back in time and manifest
    themselves in an accumulation of "secondary" kinks in the choice-specific
    value functions in earlier time periods, which, in turn, also produce an
    increasing number of discontinuities in the consumption functions
    in earlier periods of the life cycle.
    These discontinuities in consumption rules in period t are caused by the
    worker's anticipation of landing exactly at the kink points in the
    subsequent periods t + 1, t + 2, ..., T under the optimal consumption policy.

    Args:
        endog_grid (np.ndarray): 1d array of shape (n_grid_wealth + 1,)
            containing the current state- and choice-specific endogenous grid.
        policy (np.ndarray): 1d array of shape (n_grid_wealth + 1,)
            containing the current state- and choice-specific policy function.
        value (np.ndarray): 1d array of shape (n_grid_wealth + 1,)
            containing the current state- and choice-specific value function.
        exog_grid (np.ndarray): 1d array of shape (n_grid_wealth,) of the
            exogenous savings grid.
        expected_value_zero_savings (float): The agent's expected value given that she
            saves zero.
        choice (int): The current choice.
        compute_value (callable): Function to compute the agent's value.

    Returns:
        tuple:

        - endog_grid_refined (np.ndarray): 1d array of shape (1.1 * n_grid_wealth,)
            containing the refined state- and choice-specific endogenous grid.
        - policy_refined_with_nans (np.ndarray): 1d array of shape (1.1 * n_grid_wealth)
            containing refined state- and choice-specificconsumption policy.
        - value_refined_with_nans (np.ndarray): 1d array of shape (1.1 * n_grid_wealth)
            containing refined state- and choice-specific value function.

    """
    min_wealth_grid = np.min(endog_grid)
    if endog_grid[0] > min_wealth_grid:
        # Non-concave region coincides with credit constraint.
        # This happens when there is a non-monotonicity in the endogenous wealth grid
        # that goes below the first point.
        # Solution: Value function to the left of the first point is analytical,
        # so we just need to add some points to the left of the first grid point.

        endog_grid, value, policy = _augment_grids(
            endog_grid=endog_grid,
            value=value,
            policy=policy,
            choice=choice,
            expected_value_zero_savings=expected_value_zero_savings,
            min_wealth_grid=min_wealth_grid,
            points_to_add=len(endog_grid) // 10,
            compute_value=compute_value,
        )

    endog_grid = np.append(0, endog_grid)
    policy = np.append(0, policy)
    value = np.append(expected_value_zero_savings, value)

    endog_grid_refined, value_refined, policy_refined = fast_upper_envelope(
        endog_grid, value, policy, jump_thresh=2
    )

    return (
        endog_grid_refined,
        policy_refined,
        value_refined,
    )


def fast_upper_envelope(
    endog_grid: np.ndarray,
    value: np.ndarray,
    policy: np.ndarray,
    jump_thresh: Optional[float] = 2,
    lower_bound_wealth: Optional[float] = 1e-10,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Remove suboptimal points from the endogenous grid, policy, and value function.

    Args:
        endog_grid (np.ndarray): 1d array containing the unrefined endogenous wealth
            grid of shape (n_grid_wealth + 1,).
        value (np.ndarray): 1d array containing the unrefined value correspondence
            of shape (n_grid_wealth + 1,).
        policy (np.ndarray): 1d array containing the unrefined policy correspondence
            of shape (n_grid_wealth + 1,).
        exog_grid (np.ndarray): 1d array containing the exogenous wealth grid
            of shape (n_grid_wealth + 1,).
        jump_thresh (float): Jump detection threshold.
        lower_bound_wealth (float): Lower bound on wealth.

    Returns:
        tuple:

        - endog_grid_refined (np.ndarray): 1d array containing the refined endogenous
            wealth grid of shape (n_grid_clean,), which maps only to the optimal points
            in the value function.
        - value_refined (np.ndarray): 1d array containing the refined value function
            of shape (n_grid_clean,). Overlapping segments have been removed and only
            the optimal points are kept.
        - policy_refined (np.ndarray): 1d array containing the refined policy function
            of shape (n_grid_clean,). Overlapping segments have been removed and only
            the optimal points are kept.

    """
    # Comment by Akshay: Determine locations where endogenous grid points are
    # equal to the lower bound. Not relevant for us.
    # mask = endog_grid <= lower_bound_wealth
    # if np.any(mask):
    #     max_value_lower_bound = np.nanmax(value[mask])
    #     mask &= value < max_value_lower_bound
    #     value[mask] = np.nan

    idx_sort = np.argsort(endog_grid, kind="mergesort")
    value = np.take(value, idx_sort)
    policy = np.take(policy, idx_sort)
    endog_grid = np.take(endog_grid, idx_sort)

    (
        value_refined,
        policy_refined,
        endog_grid_refined,
    ) = scan_value_function(
        endog_grid=endog_grid,
        value=value,
        policy=policy,
        jump_thresh=jump_thresh,
        n_points_to_scan=10,
    )

    return endog_grid_refined, value_refined, policy_refined


def scan_value_function(
    endog_grid: np.ndarray,
    value: np.ndarray,
    policy: np.ndarray,
    jump_thresh: float,
    n_points_to_scan: Optional[int] = 0,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Scan the value function to remove suboptimal points and add intersection points.

    Args:
        value (np.ndarray): 1d array containing the unrefined value correspondence
            of shape (n_grid_wealth + 1,).
        policy (np.ndarray): 1d array containing the unrefined policy correspondence
            of shape (n_grid_wealth + 1,).
        endog_grid (np.ndarray): 1d array containing the unrefined endogenous wealth
            grid of shape (n_grid_wealth + 1,).
        jump_thresh (float): Jump detection threshold.
        n_points_to_scan (int): Number of points to scan for suboptimal points.

    Returns:
        tuple:

        - (np.ndarray): 1d array of shape (n_grid_clean,) containing the refined
            value function. Overlapping segments have been removed and only
            the optimal points are kept.

    """
    exog_grid = endog_grid - policy
    value_refined, policy_refined, endog_grid_refined = _initialize_refined_arrays(
        value, policy, endog_grid
    )

    suboptimal_points = np.zeros(n_points_to_scan, dtype=np.int64)

    # j = 1
    # k = 0

    value_j = value[1]
    endog_grid_j = endog_grid[1]
    policy_j = policy[1]
    exog_grid_j = endog_grid_j - policy_j

    value_k = value[0]
    endog_grid_k = endog_grid[0]
    policy_k = policy[0]
    exog_grid_k = endog_grid_k - policy_k

    idx_refined = 2
    for i in range(1, len(endog_grid) - 2):
        # In each iteration we calculate the gradient of the value function
        grad_before_denominator = jnp.maximum(endog_grid_j - endog_grid_k, 1e-16)
        grad_before = (value_j - value_k) / grad_before_denominator

        # gradient with leading index to be checked
        grad_next_denominator = jnp.maximum(endog_grid[i + 1] - endog_grid_j, 1e-16)
        grad_next = (value[i + 1] - value_j) / grad_next_denominator

        switch_value_denominator = jnp.maximum(endog_grid[i + 1] - endog_grid_j, 1e-16)
        switch_value_func = (
            np.abs((exog_grid[i + 1] - exog_grid_j) / switch_value_denominator)
            > jump_thresh
        )

        (
            grad_next_forward,
            idx_next_on_lower_curve,
            found_next_point_on_same_value,
        ) = _forward_scan(
            value=value,
            endog_grid=endog_grid,
            exog_grid=exog_grid,
            jump_thresh=jump_thresh,
            endog_grid_current=endog_grid_j,
            exog_grid_current=exog_grid_j,
            idx_next=i + 1,
            n_points_to_scan=n_points_to_scan,
        )

        (
            grad_next_backward,
            sub_idx_point_before_on_same_value,
        ) = _backward_scan(
            value=value,
            endog_grid=endog_grid,
            exog_grid=exog_grid,
            suboptimal_points=suboptimal_points,
            jump_thresh=jump_thresh,
            value_current=value_j,
            endog_grid_current=endog_grid_j,
            idx_next=i + 1,
        )
        idx_before_on_upper_curve = suboptimal_points[
            sub_idx_point_before_on_same_value
        ]

        # Check for suboptimality. This is either with decreasing value function, the
        # value function not montone in consumption or
        # if the gradient joining the leading point i+1 and the point j (the last point
        # on the same choice specific policy) is shallower than the
        # gradient joining the i+1 and j, then delete j'th point
        if (
            value[i + 1] < value_j
            or exog_grid[i + 1] < exog_grid_j
            or (grad_next < grad_next_forward and switch_value_func)
        ):
            suboptimal_points = _append_index(suboptimal_points, i + 1)

        elif not switch_value_func:
            value_refined[idx_refined] = value[i + 1]
            policy_refined[idx_refined] = policy[i + 1]
            endog_grid_refined[idx_refined] = endog_grid[i + 1]
            idx_refined += 1

            value_k = value_j
            endog_grid_k = endog_grid_j
            exog_grid_k = exog_grid_j
            policy_k = policy_j

            value_j = value[i + 1]
            endog_grid_j = endog_grid[i + 1]
            policy_j = policy[i + 1]
            exog_grid_j = endog_grid_j - policy_j

        elif grad_before > grad_next or grad_next < grad_next_backward:
            intersect_grid, intersect_value = _linear_intersection(
                x1=endog_grid[idx_next_on_lower_curve],
                y1=value[idx_next_on_lower_curve],
                x2=endog_grid_j,
                y2=value_j,
                x3=endog_grid[i + 1],
                y3=value[i + 1],
                x4=endog_grid[idx_before_on_upper_curve],
                y4=value[idx_before_on_upper_curve],
            )

            intersect_policy_left = _evaluate_point_on_line(
                x1=endog_grid[idx_next_on_lower_curve],
                y1=policy[idx_next_on_lower_curve],
                x2=endog_grid_j,
                y2=policy_j,
                point_to_evaluate=intersect_grid,
            )
            intersect_policy_right = _evaluate_point_on_line(
                x1=endog_grid[i + 1],
                y1=policy[i + 1],
                x2=endog_grid[idx_before_on_upper_curve],
                y2=policy[idx_before_on_upper_curve],
                point_to_evaluate=intersect_grid,
            )

            value_refined[idx_refined] = intersect_value
            policy_refined[idx_refined] = intersect_policy_left
            endog_grid_refined[idx_refined] = intersect_grid
            idx_refined += 1

            value_refined[idx_refined] = intersect_value
            policy_refined[idx_refined] = intersect_policy_right
            endog_grid_refined[idx_refined] = intersect_grid
            idx_refined += 1

            value_refined[idx_refined] = value[i + 1]
            policy_refined[idx_refined] = policy[i + 1]
            endog_grid_refined[idx_refined] = endog_grid[i + 1]
            idx_refined += 1

            value_k = value_j
            endog_grid_k = endog_grid_j
            exog_grid_k = exog_grid_j
            policy_k = policy_j

            value_j = value[i + 1]
            endog_grid_j = endog_grid[i + 1]
            policy_j = policy[i + 1]
            exog_grid_j = endog_grid_j - policy_j

            # k = j
            # j = i + 1

        elif grad_next > grad_next_backward:
            intersect_grid, intersect_value = _linear_intersection(
                x1=endog_grid_j,
                y1=value_j,
                x2=endog_grid_k,
                y2=value_k,
                x3=endog_grid[i + 1],
                y3=value[i + 1],
                x4=endog_grid[idx_before_on_upper_curve],
                y4=value[idx_before_on_upper_curve],
            )

            # The next two interpolations is just to show that from
            # interpolation from each side leads to the same result
            intersect_policy_left = _evaluate_point_on_line(
                x1=endog_grid_k,
                y1=policy_k,
                x2=endog_grid_j,
                y2=policy_j,
                point_to_evaluate=intersect_grid,
            )
            intersect_policy_right = _evaluate_point_on_line(
                x1=endog_grid[i + 1],
                y1=policy[i + 1],
                x2=endog_grid[idx_before_on_upper_curve],
                y2=policy[idx_before_on_upper_curve],
                point_to_evaluate=intersect_grid,
            )

            value_refined[idx_refined - 1] = intersect_value
            policy_refined[idx_refined - 1] = intersect_policy_left
            endog_grid_refined[idx_refined - 1] = intersect_grid

            value_refined[idx_refined] = intersect_value
            policy_refined[idx_refined] = intersect_policy_right
            endog_grid_refined[idx_refined] = intersect_grid
            idx_refined += 1

            value_refined[idx_refined] = value[i + 1]
            policy_refined[idx_refined] = policy[i + 1]
            endog_grid_refined[idx_refined] = endog_grid[i + 1]
            idx_refined += 1

            value_j = intersect_value
            endog_grid_j = intersect_grid
            policy_j = intersect_policy_right
            exog_grid_j = endog_grid_j - policy_j

            # j = i + 1

    value_refined[idx_refined] = value[-1]
    endog_grid_refined[idx_refined] = endog_grid[-1]
    policy_refined[idx_refined] = policy[-1]

    return value_refined, policy_refined, endog_grid_refined


@njit
def _forward_scan(
    value: np.ndarray,
    endog_grid: np.ndarray,
    exog_grid: np.ndarray,
    jump_thresh: float,
    endog_grid_current: float,
    exog_grid_current: float,
    idx_next: int,
    n_points_to_scan: int,
) -> Tuple[float, int, int]:
    """Scan forward to check whether next point is optimal.

    Args:
        value (np.ndarray): 1d array containing the value function of shape
            (n_grid_wealth + 1,).
        endog_grid (np.ndarray): 1d array containing the endogenous wealth grid of
            shape (n_grid_wealth + 1,).
        exog_grid (np.ndarray): 1d array containing the exogenous wealth grid of
            shape (n_grid_wealth + 1,).
        jump_thresh (float): Threshold for the jump in the value function.
        idx_current (int): Index of the current point in the value function.
        idx_next (int): Index of the next point in the value function.
        n_points_to_scan (int): The number of points to scan forward.

    Returns:
        tuple:

        - grad_next_forward (float): The gradient of the next point on the same
            value function.
        - is_point_on_same_value (int): Indicator for whether the next point is on
            the same value function.
        - dist_next_point_on_same_value (int): The distance to the next point on
            the same value function.

    """

    is_next_on_same_value = 0
    idx_on_same_value = 0
    grad_next_on_same_value = 0

    idx_max = len(exog_grid) - 1

    for i in range(1, n_points_to_scan + 1):
        idx_to_check = min(idx_next + i, idx_max)
        if endog_grid_current < endog_grid[idx_to_check]:
            is_on_same_value = (
                np.abs(
                    (exog_grid_current - exog_grid[idx_to_check])
                    / (endog_grid_current - endog_grid[idx_to_check])
                )
                < jump_thresh
            )
            is_next = is_on_same_value * (1 - is_next_on_same_value)
            idx_on_same_value = (
                idx_to_check * is_next + (1 - is_next) * idx_on_same_value
            )

            grad_next_on_same_value = (
                (value[idx_next] - value[idx_to_check])
                / (endog_grid[idx_next] - endog_grid[idx_to_check])
            ) * is_next + (1 - is_next) * grad_next_on_same_value

            is_next_on_same_value = (
                is_next_on_same_value * is_on_same_value
                + (1 - is_on_same_value) * is_next_on_same_value
                + is_on_same_value * (1 - is_next_on_same_value)
            )

    return (
        grad_next_on_same_value,
        idx_on_same_value,
        is_next_on_same_value,
    )


@njit
def _backward_scan(
    value: np.ndarray,
    endog_grid: np.ndarray,
    exog_grid: np.ndarray,
    suboptimal_points: np.ndarray,
    jump_thresh: float,
    endog_grid_current,
    value_current,
    idx_next: int,
) -> Tuple[float, int]:
    """Scan backward to check whether current point is optimal.

    Args:
        value (np.ndarray): 1d array containing the value function of shape
            (n_grid_wealth + 1,).
        endog_grid (np.ndarray): 1d array containing the endogenous wealth grid of
            shape (n_grid_wealth + 1,).
        exog_grid (np.ndarray): 1d array containing the exogenous wealth grid of
            shape (n_grid_wealth + 1,).
        suboptimal_points (list): List of suboptimal points in the value functions.
        jump_thresh (float): Threshold for the jump in the value function.
        idx_current (int): Index of the current point in the value function.
        idx_next (int): Index of the next point in the value function.

    Returns:
        tuple:

        - grad_before_on_same_value (float): The gradient of the previous point on
            the same value function.
        - is_before_on_same_value (int): Indicator for whether we have found a
            previous point on the same value function.

    """

    is_before_on_same_value = 0
    sub_idx_point_before_on_same_value = 0
    grad_before_on_same_value = 0

    indexes_reversed = len(suboptimal_points) - 1

    for i, idx_to_check in enumerate(suboptimal_points[::-1]):
        if endog_grid_current > endog_grid[idx_to_check]:
            is_on_same_value = (
                np.abs(
                    (exog_grid[idx_next] - exog_grid[idx_to_check])
                    / (endog_grid[idx_next] - endog_grid[idx_to_check])
                )
                < jump_thresh
            )
            is_before = is_on_same_value * (1 - is_before_on_same_value)
            sub_idx_point_before_on_same_value = (indexes_reversed - i) * is_before + (
                1 - is_before
            ) * sub_idx_point_before_on_same_value

            grad_before_on_same_value = (
                (value_current - value[idx_to_check])
                / (endog_grid_current - endog_grid[idx_to_check])
            ) * is_before + (1 - is_before) * grad_before_on_same_value

            is_before_on_same_value = (
                (is_before_on_same_value * is_on_same_value)
                + (1 - is_on_same_value) * is_before_on_same_value
                + is_on_same_value * (1 - is_before_on_same_value)
            )

    return (
        grad_before_on_same_value,
        sub_idx_point_before_on_same_value,
    )


@njit
def _evaluate_point_on_line(
    x1: float, y1: float, x2: float, y2: float, point_to_evaluate: float
) -> float:
    """Evaluate a point on a line.

    Args:
        x1 (float): x coordinate of the first point.
        y1 (float): y coordinate of the first point.
        x2 (float): x coordinate of the second point.
        y2 (float): y coordinate of the second point.
        point_to_evaluate (float): The point to evaluate.

    Returns:
        float: The value of the point on the line.

    """
    return (y2 - y1) / (x2 - x1) * (point_to_evaluate - x1) + y1


@njit
def _linear_intersection(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    x3: float,
    y3: float,
    x4: float,
    y4: float,
) -> Tuple[float, float]:
    """Find the intersection of two lines.

    Args:

        x1 (float): x-coordinate of the first point of the first line.
        y1 (float): y-coordinate of the first point of the first line.
        x2 (float): x-coordinate of the second point of the first line.
        y2 (float): y-coordinate of the second point of the first line.
        x3 (float): x-coordinate of the first point of the second line.
        y3 (float): y-coordinate of the first point of the second line.
        x4 (float): x-coordinate of the second point of the second line.
        y4 (float): y-coordinate of the second point of the second line.

    Returns:
        tuple: x and y coordinates of the intersection point.

    """

    slope1 = (y2 - y1) / (x2 - x1)
    slope2 = (y4 - y3) / (x4 - x3)

    x_intersection = (slope1 * x1 - slope2 * x3 + y3 - y1) / (slope1 - slope2)
    y_intersection = slope1 * (x_intersection - x1) + y1

    return x_intersection, y_intersection


@njit
def _append_index(x_array: np.ndarray, m: int):
    """Append a new point to an array."""
    for i in range(len(x_array) - 1):
        x_array[i] = x_array[i + 1]

    x_array[-1] = m
    return x_array


def _augment_grids(
    endog_grid: np.ndarray,
    value: np.ndarray,
    policy: np.ndarray,
    choice: int,
    expected_value_zero_savings: np.ndarray,
    min_wealth_grid: float,
    points_to_add: int,
    compute_value: Callable,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Extends the endogenous wealth grid, value, and policy functions to the left.

    Args:
        endog_grid (np.ndarray): 1d array containing the endogenous wealth grid of
            shape (n_endog_wealth_grid,), where n_endog_wealth_grid is of variable
            length depending on the number of kinks and non-concave regions in the
            value function.
        value (np.ndarray):  1d array storing the choice-specific
            value function of shape (n_endog_wealth_grid,), where
            n_endog_wealth_grid is of variable length depending on the number of
            kinks and non-concave regions in the value function.
            In the presence of kinks, the value function is a "correspondence"
            rather than a function due to non-concavities.
        policy (np.ndarray):  1d array storing the choice-specific
            policy function of shape (n_endog_wealth_grid,), where
            n_endog_wealth_grid is of variable length depending on the number of
            discontinuities in the policy function.
            In the presence of discontinuities, the policy function is a
            "correspondence" rather than a function due to multiple local optima.
        choice (int): The agent's choice.
        expected_value_zero_savings (float): The agent's expected value given that she
            saves zero.
        min_wealth_grid (float): Minimal wealth level in the endogenous wealth grid.
        points_to_add (int): Number of grid points to add. Roughly num_wealth / 10.
        compute_value (callable): Function to compute the agent's value.

    Returns:
        tuple:

        - grid_augmented (np.ndarray): 1d array containing the augmented
            endogenous wealth grid with ancillary points added to the left.
        - policy_augmented (np.ndarray): 1d array containing the augmented
            policy function with ancillary points added to the left.
        - value_augmented (np.ndarray): 1d array containing the augmented
            value function with ancillary points added to the left.

    """
    grid_points_to_add = np.linspace(min_wealth_grid, endog_grid[0], points_to_add)[:-1]

    grid_augmented = np.append(grid_points_to_add, endog_grid)
    values_to_add = compute_value(
        grid_points_to_add,
        expected_value_zero_savings,
        choice,
    )
    value_augmented = np.append(values_to_add, value)
    policy_augmented = np.append(grid_points_to_add, policy)

    return grid_augmented, value_augmented, policy_augmented


def _initialize_refined_arrays(
    value: np.ndarray, policy: np.ndarray, endog_grid: np.ndarray
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    value_refined = np.empty_like(value)
    policy_refined = np.empty_like(policy)
    endog_grid_refined = np.empty_like(endog_grid)

    value_refined[:] = np.nan
    policy_refined[:] = np.nan
    endog_grid_refined[:] = np.nan

    value_refined[:2] = value[:2]
    policy_refined[:2] = policy[:2]
    endog_grid_refined[:2] = endog_grid[:2]

    return value_refined, policy_refined, endog_grid_refined
