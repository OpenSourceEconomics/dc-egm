import pickle
from typing import Callable, Dict

import jax

from dcegm.pre_processing.batches import create_batches_and_information
from dcegm.pre_processing.exog_processes import create_exog_state_mapping
from dcegm.pre_processing.model_functions import process_model_functions
from dcegm.pre_processing.state_space import (
    check_options,
    create_array_with_smallest_int_dtype,
    create_state_space_and_choice_objects,
)


def setup_model(
    options: Dict,
    utility_functions: Dict[str, Callable],
    utility_functions_final_period: Dict[str, Callable],
    budget_constraint: Callable,
    state_space_functions: Dict[str, Callable] = None,
):
    """Set up the model for dcegm.

    It consists of two steps. First it processes the user supplied functions to make
    them compatible with the interface the dcegm software expects. Second it creates
    the states and choice objects used by the dcegm software.

    Args:
        options (Dict[str, int]): Options dictionary.
        state_space_functions (Dict[str, Callable]): Dictionary of user supplied
        functions for computation of:
            (i) next period endogenous states
            (ii) next period exogenous states
            (iii) next period discrete choices
        utility_functions (Dict[str, Callable]): Dictionary of three user-supplied
            functions for computation of:
            (i) utility
            (ii) inverse marginal utility
            (iii) next period marginal utility
        utility_functions_final_period (Dict[str, Callable]): Dictionary of two
            user-supplied functions for computation of:
            (i) utility
            (ii) next period marginal utility
        budget_constraint (Callable): User supplied budget constraint.

    """
    state_space_functions = (
        {} if state_space_functions is None else state_space_functions
    )
    options = check_options(options)

    model_funcs = process_model_functions(
        options,
        state_space_functions=state_space_functions,
        utility_functions=utility_functions,
        utility_functions_final_period=utility_functions_final_period,
        budget_constraint=budget_constraint,
    )

    model_structure = create_state_space_and_choice_objects(
        options=options,
        model_funcs=model_funcs,
    )

    model_funcs["exog_state_mapping"] = create_exog_state_mapping(
        model_structure["exog_state_space"],
        model_structure["exog_states_names"],
    )

    batch_info = create_batches_and_information(
        model_structure=model_structure,
        options=options,
    )

    model = {
        "model_funcs": model_funcs,
        "model_structure": model_structure,
        "batch_info": jax.tree.map(create_array_with_smallest_int_dtype, batch_info),
    }
    return model


def setup_and_save_model(
    options: Dict,
    utility_functions: Dict[str, Callable],
    utility_functions_final_period: Dict[str, Callable],
    budget_constraint: Callable,
    state_space_functions: Dict[str, Callable] = None,
    path: str = "model.pkl",
):
    """Set up the model and save.

    Model creation is time-consuming. This function creates the model and saves it to
    file. This way the model can be loaded from file in the future, which is much faster
    than recreating the model from scratch.

    """
    options = check_options(options)

    model = setup_model(
        options=options,
        state_space_functions=state_space_functions,
        utility_functions=utility_functions,
        utility_functions_final_period=utility_functions_final_period,
        budget_constraint=budget_constraint,
    )

    dict_to_save = {
        "model_structure": model["model_structure"],
        "batch_info": model["batch_info"],
    }
    pickle.dump(dict_to_save, open(path, "wb"))

    return model


def load_and_setup_model(
    options: Dict,
    utility_functions: Dict[str, Callable],
    utility_functions_final_period: Dict[str, Callable],
    budget_constraint: Callable,
    state_space_functions: Dict[str, Callable] = None,
    path: str = "model.pkl",
):
    """Load the model from file."""
    options = check_options(options)

    model = pickle.load(open(path, "rb"))

    state_space_functions = (
        {} if state_space_functions is None else state_space_functions
    )
    model["model_funcs"] = process_model_functions(
        options,
        state_space_functions=state_space_functions,
        utility_functions=utility_functions,
        utility_functions_final_period=utility_functions_final_period,
        budget_constraint=budget_constraint,
    )

    model["model_funcs"]["exog_state_mapping"] = create_exog_state_mapping(
        exog_state_space=model["model_structure"]["exog_state_space"],
        exog_names=model["model_structure"]["exog_states_names"],
    )

    return model


def process_tuning_parameters(options):
    """Process the tuning parameters."""
    options["extra_wealth_grid_factor"] = (
        options["extra_wealth_grid_factor"]
        if "extra_wealth_grid_factor" in options
        else 0.2
    )

    if (
        options["n_grid_points"] * (1 + options["extra_wealth_grid_factor"])
        < options["n_grid_points"] + options["n_constrained_points_to_add"]
    ):
        raise ValueError(
            "The number of grid points is too large. Please reduce the number of grid points or the extra_wealth_grid_factor."
        )
    return options
