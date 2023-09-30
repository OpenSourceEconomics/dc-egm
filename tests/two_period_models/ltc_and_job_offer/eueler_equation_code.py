import numpy as np

from tests.two_period_models.ltc_and_job_offer.dcegm_code import flow_util
from tests.two_period_models.ltc_and_job_offer.dcegm_code import marginal_utility


def euler_rhs_two_exog_processes(
    init_cond, params, draws, weights, retirement_choice_1, consumption
):
    beta = params["beta"]
    interest_factor = 1 + params["interest_rate"]

    rhs = 0
    for index_draw, draw in enumerate(draws):
        marg_util_draw = marginal_utility_weighted_two_exog_processes(
            init_cond, params, retirement_choice_1, draw, consumption
        )
        rhs += weights[index_draw] * marg_util_draw
    return rhs * beta * interest_factor


def budget_two_exog_processes(
    lagged_resources,
    lagged_consumption,
    lagged_retirement_choice,
    wage,
    bad_health,
    lagged_job_offer,
    params,
):
    interest_factor = 1 + params["interest_rate"]
    health_costs = params["ltc_cost"]
    resources = (
        interest_factor * (lagged_resources - lagged_consumption)
        + wage * lagged_job_offer * (1 - lagged_retirement_choice)
        - bad_health * health_costs
    ).clip(min=0.5)
    return resources


def choice_prob_retirement(consumption, choice, params):
    v = flow_util(consumption=consumption, params=params, choice=choice)
    v_0 = flow_util(consumption=consumption, params=params, choice=0)
    v_1 = flow_util(consumption=consumption, params=params, choice=1)
    choice_prob = np.exp(v) / (np.exp(v_0) + np.exp(v_1))
    return choice_prob


def wage(nu, params):
    wage = params["wage_avg"] + nu
    return wage


def prob_long_term_care_patient(params, lagged_bad_health, bad_health):
    p = params["ltc_prob"]
    # jnp.array([[0.7, 0.3], [0, 1]])

    if lagged_bad_health == bad_health == 0:
        pi = 1 - p
    elif (lagged_bad_health == 0) and (bad_health == 1):
        pi = p
    elif lagged_bad_health == 1 and bad_health == 0:
        pi = 0
    elif lagged_bad_health == bad_health == 1:
        pi = 1

    return pi


def prob_job_offer(params, lagged_job_offer, job_offer):
    # p = params["job_offer_prob"]

    if (lagged_job_offer == 0) and (job_offer == 1):
        pi = 0.5
    elif lagged_job_offer == job_offer == 0:
        pi = 0.5
    elif lagged_job_offer == 1 and job_offer == 0:
        pi = 0.1
    elif lagged_job_offer == job_offer == 1:
        pi = 0.9

    return pi


def marginal_utility_weighted_two_exog_processes(
    init_cond, params, retirement_choice_1, nu, consumption
):
    """Return the expected marginal utility for one realization of the wage shock."""
    budget_1 = init_cond["wealth"]
    ltc_state_1 = init_cond["bad_health"]
    job_state_1 = init_cond["job_offer"]

    weighted_marginal = 0
    for ltc_state_2 in (0, 1):
        for job_state_2 in (0, 1):
            for retirement_choice_2 in (0, 1):
                budget_2 = budget_two_exog_processes(
                    budget_1,
                    consumption,
                    retirement_choice_1,
                    wage(nu, params),
                    ltc_state_2,
                    job_state_1,
                    params,
                )

                marginal_util = marginal_utility(consumption=budget_2, params=params)
                choice_prob = choice_prob_retirement(
                    consumption=budget_2, choice=retirement_choice_2, params=params
                )

                ltc_prob = prob_long_term_care_patient(params, ltc_state_1, ltc_state_2)
                job_offer_prob = prob_job_offer(params, job_state_1, job_state_2)

                weighted_marginal += (
                    choice_prob * ltc_prob * job_offer_prob * marginal_util
                )

    return weighted_marginal