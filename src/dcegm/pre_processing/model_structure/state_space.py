"""Functions for creating internal state space objects."""

import numpy as np

from dcegm.pre_processing.model_structure.endogenous_states import (
    process_endog_state_specifications,
)
from dcegm.pre_processing.model_structure.exogenous_processes import (
    process_exog_model_specifications,
)
from dcegm.pre_processing.model_structure.shared import create_indexer_for_space
from dcegm.pre_processing.shared import create_array_with_smallest_int_dtype


def create_state_space(options):
    """Create state space object and indexer.

    We need to add the convention for the state space objects.

    Args:
        options (dict): Options dictionary.

    Returns:
        Dict:

        - state_vars (list): List of state variables.
        - state_space (np.ndarray): 2d array of shape (n_states, n_state_variables + 1)
            which serves as a collection of all possible states. By convention,
            the first column must contain the period and the last column the
            exogenous processes. Any other state variables are in between.
            E.g. if the two state variables are period and lagged choice and all choices
            are admissible in each period, the shape of the state space array is
            (n_periods * n_choices, 3).
        - map_state_to_index (np.ndarray): Indexer array that maps states to indexes.
            The shape of this object is quite complicated. For each state variable it
            has the number of possible states as rows, i.e.
            (n_poss_states_state_var_1, n_poss_states_state_var_2, ....).

    """

    state_space_options = options["state_space"]
    model_params = options["model_params"]

    n_periods = state_space_options["n_periods"]
    n_choices = len(state_space_options["choices"])

    (
        add_endog_state_func,
        endog_states_names,
        n_endog_states,
        sparsity_func,
    ) = process_endog_state_specifications(
        state_space_options=state_space_options, model_params=model_params
    )
    state_names_without_exog = ["period", "lagged_choice"] + endog_states_names

    (
        exog_states_names,
        exog_state_space_raw,
    ) = process_exog_model_specifications(state_space_options=state_space_options)
    discrete_states_names = state_names_without_exog + exog_states_names

    n_exog_states = exog_state_space_raw.shape[0]

    state_space_list = []
    list_of_states_proxied_from = []
    list_of_states_proxied_to = []
    proxies_exist = False

    for period in range(n_periods):
        for endog_state_id in range(n_endog_states):
            for lagged_choice in range(n_choices):
                # Select the endogenous state combination
                endog_states = add_endog_state_func(endog_state_id)

                for exog_state_id in range(n_exog_states):
                    exog_states = exog_state_space_raw[exog_state_id, :]

                    # Create the state vector
                    state = [period, lagged_choice] + endog_states + list(exog_states)

                    # Transform to dictionary to call sparsity function from user
                    state_dict = {
                        discrete_states_names[i]: state_value
                        for i, state_value in enumerate(state)
                    }

                    # Check if the state is valid by calling the sparsity function
                    sparsity_output = sparsity_func(**state_dict)

                    # The sparsity condition can either return a boolean indicating if the state
                    # is valid or not, or a dictionary which contains the valid state which is used
                    # instead as a child state for other states. If a state is invalid because of the
                    # exogenous state component, the user must specify a valid state to use instead, as
                    # we assume a state choice combination has n_exog_states children.
                    # We do check later if the user correctly specified the proxy state. Here we just check
                    # the format of the output.
                    if isinstance(sparsity_output, dict):
                        # Check if dictionary keys are the same and the items are ints
                        if set(sparsity_output.keys()) != set(
                            discrete_states_names
                        ) or not all(
                            isinstance(value, int) for value in sparsity_output.values()
                        ):
                            raise ValueError(
                                f" The state \n\n{sparsity_output}\n\n returned by the sparsity condition"
                                f"does not have the correct format. The dictionary keys should be the same as"
                                f"the discrete state names: \n\n{discrete_states_names}\n\n and the values should "
                                f"be integers."
                            )
                        else:
                            state_is_valid = False
                            proxies_exist = True
                            list_of_states_proxied_from += [state]
                            state_list_proxied_to = [
                                sparsity_output[key] for key in discrete_states_names
                            ]
                            list_of_states_proxied_to += [state_list_proxied_to]
                    elif isinstance(sparsity_output, bool):
                        state_is_valid = sparsity_output
                    else:
                        raise ValueError(
                            f"The sparsity condition for the state \n\n{state_dict}\n\n"
                            f"returned an output of the wrong type. It should return either a boolean"
                            f"or a dictionary."
                        )

                    if state_is_valid:
                        state_space_list += [state]

    state_space_raw = np.array(state_space_list)
    state_space = create_array_with_smallest_int_dtype(state_space_raw)
    map_state_to_index = create_indexer_for_space(state_space)

    if proxies_exist:
        # If proxies exist we create a different indexer, to map
        # the child states of state choices later to proxied states
        map_state_to_index_with_proxies = create_indexer_inclucing_proxies(
            map_state_to_index, list_of_states_proxied_from, list_of_states_proxied_to
        )
        map_child_state_to_index = map_state_to_index_with_proxies
    else:
        map_child_state_to_index = map_state_to_index

    state_space_dict = {
        key: create_array_with_smallest_int_dtype(state_space[:, i])
        for i, key in enumerate(discrete_states_names)
    }

    exog_state_space = create_array_with_smallest_int_dtype(exog_state_space_raw)

    dict_of_state_space_objects = {
        "state_space": state_space,
        "state_space_dict": state_space_dict,
        "map_state_to_index": map_state_to_index,
        "map_child_state_to_index": map_child_state_to_index,
        "exog_state_space": exog_state_space,
        "exog_states_names": exog_states_names,
        "state_names_without_exog": state_names_without_exog,
        "discrete_states_names": discrete_states_names,
    }

    return dict_of_state_space_objects


def create_indexer_inclucing_proxies(
    map_state_to_index, list_of_states_proxied_from, list_of_states_proxied_to
):
    """Create an indexer that includes the index of proxied invalid states."""
    array_of_states_proxied_from = np.array(list_of_states_proxied_from)
    array_of_states_proxied_to = np.array(list_of_states_proxied_to)

    tuple_of_states_proxied_from = tuple(
        array_of_states_proxied_from[:, i]
        for i in range(array_of_states_proxied_from.shape[1])
    )
    tuple_of_states_proxied_to = tuple(
        array_of_states_proxied_to[:, i]
        for i in range(array_of_states_proxied_to.shape[1])
    )
    map_state_to_index_with_proxies = map_state_to_index.copy()
    map_state_to_index_with_proxies[tuple_of_states_proxied_from] = map_state_to_index[
        tuple_of_states_proxied_to
    ]
    return map_state_to_index_with_proxies
