import numpy as np


def create_batches_and_information(
    model_structure,
    model_funcs,
    options,
):
    n_periods = options["state_space"]["n_periods"]
    state_choice_space = model_structure["state_choice_space"]
    state_space = model_structure["state_space"]
    state_space_names = model_structure["state_space_names"]
    map_state_choice_to_parent_state = model_structure[
        "map_state_choice_to_parent_state"
    ]
    map_state_choice_to_child_states = model_structure[
        "map_state_choice_to_child_states"
    ]
    map_state_choice_to_index = model_structure["map_state_choice_to_index"]

    if n_periods == 2:
        # In the case of a two period model, we just need the information of the last
        # two periods
        batch_info = {
            "two_period_model": True,
            "n_state_choices": state_choice_space.shape[0],
        }
        batch_info = add_last_two_period_information(
            n_periods=n_periods,
            state_choice_space=state_choice_space,
            map_state_choice_to_parent_state=map_state_choice_to_parent_state,
            map_state_choice_to_child_states=map_state_choice_to_child_states,
            map_state_choice_to_index=map_state_choice_to_index,
            state_space_names=state_space_names,
            state_space=state_space,
            batch_info=batch_info,
        )

        return batch_info

    (
        batches_list,
        child_state_choice_idxs_to_interp_list,
        child_state_choices_to_aggr_choice_list,
        child_states_to_integrate_exog_list,
    ) = determine_optimal_batch_size(
        state_choice_space,
        n_periods,
        map_state_choice_to_child_states,
        map_state_choice_to_index,
        state_space,
    )

    if len(batches_list) == 1:
        # This is the case of a two period model. Then by construction there is only one
        # batch which covers the first period.
        batches_cover_all = True
    else:
        # In the case of more periods we determine if the last two batches have equal
        # size
        batches_cover_all = len(batches_list[-1]) == len(batches_list[-2])

    if not batches_cover_all:
        # In the case batches don't cover everything, we have to solve the last batch
        # separately. Delete the last element from the relevant lists and save it in
        # an extra dictionary
        last_batch = batches_list[-1]
        last_child_states_to_integrate_exog = child_states_to_integrate_exog_list[-1]
        last_idx_to_aggregate_choice = child_state_choices_to_aggr_choice_list[-1]
        last_child_state_idx_interp = child_state_choice_idxs_to_interp_list[-1]
        last_state_choices = {
            key: state_choice_space[:, i][last_batch]
            for i, key in enumerate(state_space_names + ["choice"])
        }
        last_state_choices_childs = {
            key: state_choice_space[:, i][last_child_state_idx_interp]
            for i, key in enumerate(state_space_names + ["choice"])
        }
        last_parent_state_idx_of_state_choice = map_state_choice_to_parent_state[
            last_child_state_idx_interp
        ]

        last_batch_info = {
            "state_choice_idx": last_batch,
            "state_choices": last_state_choices,
            "child_states_to_integrate_exog": last_child_states_to_integrate_exog,
            # Child state infos.
            "child_state_choices_to_aggr_choice": last_idx_to_aggregate_choice,
            "child_state_choice_idxs_to_interp": last_child_state_idx_interp,
            "child_states_idxs": last_parent_state_idx_of_state_choice,
            "state_choices_childs": last_state_choices_childs,
        }
        batches_list = batches_list[:-1]
        child_states_to_integrate_exog_list = child_states_to_integrate_exog_list[:-1]
        child_state_choices_to_aggr_choice_list = (
            child_state_choices_to_aggr_choice_list[:-1]
        )
        child_state_choice_idxs_to_interp_list = child_state_choice_idxs_to_interp_list[
            :-1
        ]

    # First convert batch information
    batch_array = np.array(batches_list)
    child_states_to_integrate_exog = np.array(child_states_to_integrate_exog_list)

    state_choices_batches = {
        key: state_choice_space[:, i][batch_array]
        for i, key in enumerate(state_space_names + ["choice"])
    }

    # Now create the child state arrays. As these can have different shapes than the
    # batches, we have to extend them:
    max_child_state_index_batch = np.max(child_states_to_integrate_exog, axis=(1, 2))
    (
        child_state_choice_idxs_to_interp,
        child_state_choices_to_aggr_choice,
    ) = extend_child_state_choices_to_aggregate_choices(
        idx_to_aggregate_choice=child_state_choices_to_aggr_choice_list,
        max_child_state_index_batch=max_child_state_index_batch,
        idx_to_interpolate=child_state_choice_idxs_to_interp_list,
    )
    parent_state_idx_of_state_choice = map_state_choice_to_parent_state[
        child_state_choice_idxs_to_interp
    ]
    state_choices_childs = {
        key: state_choice_space[:, i][child_state_choice_idxs_to_interp]
        for i, key in enumerate(state_space_names + ["choice"])
    }

    batch_info = {
        # First two bools determining the structure of solution functions we call
        "two_period_model": False,
        "batches_cover_all": batches_cover_all,
        # Now the batch array information. First the batch itself
        "batches_state_choice_idx": batch_array,
        "state_choices": state_choices_batches,
        "child_states_to_integrate_exog": child_states_to_integrate_exog,
        # Then the child states
        "child_state_choices_to_aggr_choice": child_state_choices_to_aggr_choice,
        "child_state_choice_idxs_to_interp": child_state_choice_idxs_to_interp,
        "child_states_idxs": parent_state_idx_of_state_choice,
        "state_choices_childs": state_choices_childs,
    }
    if not batches_cover_all:
        batch_info["last_batch_info"] = last_batch_info
    batch_info = add_last_two_period_information(
        n_periods=n_periods,
        state_choice_space=state_choice_space,
        map_state_choice_to_parent_state=map_state_choice_to_parent_state,
        map_state_choice_to_child_states=map_state_choice_to_child_states,
        map_state_choice_to_index=map_state_choice_to_index,
        state_space_names=state_space_names,
        state_space=state_space,
        batch_info=batch_info,
    )

    return batch_info


def extend_child_state_choices_to_aggregate_choices(
    idx_to_aggregate_choice, max_child_state_index_batch, idx_to_interpolate
):
    """In case of uneven batches, we need to extend the child state objects to cover the
    same number of state choices in each batch.

    As this object has in each batch the shape of n_state_choices x n_

    """
    # There can be also be an uneven number of child states across batches. The
    # indexes recorded in state_choice_times_exog_child_state_idxs only contain
    # the indexes up the length. So we can just fill up without of bounds indexes.
    # We also test this here
    max_n_state_unique_in_batches = list(
        map(lambda x: x.shape[0], idx_to_aggregate_choice)
    )

    # We check for internal constincy. The size (i.e. the number of states) of the
    # state_choice idx to aggregate choices in each state has to correspond to the
    # maximum state index in child indexes we integrate over.
    if not np.all(
        np.equal(
            np.array(max_n_state_unique_in_batches) - 1, max_child_state_index_batch
        )
    ):
        raise ValueError(
            "\n\nInternal error in the batch creation \n\n. "
            "Please contact developer."
        )

    # Now span an array with n_states time the maximum number of child states across
    # all batches and the number of choices. Fill with invalid(negative) numbers
    # otherwise
    n_batches = len(idx_to_aggregate_choice)
    max_n_child_states = np.max(max_n_state_unique_in_batches)
    n_choices = idx_to_aggregate_choice[0].shape[1]
    child_state_choices_to_aggr_choice = np.full(
        (n_batches, max_n_child_states, n_choices),
        fill_value=-9999,
        dtype=int,
    )

    for id_batch in range(n_batches):
        child_state_choices_to_aggr_choice[
            id_batch, : max_n_state_unique_in_batches[id_batch], :
        ] = idx_to_aggregate_choice[id_batch]

    # The second array are the state choice indexes in the child states. As child
    # states can have different admissible state choices this can be different in
    # each batch. We fill up with invalid numbers.
    max_child_state_choices = np.max(list(map(len, idx_to_interpolate)))
    child_state_choice_idxs_to_interp = np.full(
        (n_batches, max_child_state_choices),
        fill_value=-9999,
        dtype=int,
    )
    for id_batch in range(n_batches):
        child_state_choice_idxs_to_interp[
            id_batch, : len(idx_to_interpolate[id_batch])
        ] = idx_to_interpolate[id_batch]

    return child_state_choice_idxs_to_interp, child_state_choices_to_aggr_choice


def add_last_two_period_information(
    n_periods,
    state_choice_space,
    map_state_choice_to_parent_state,
    map_state_choice_to_child_states,
    map_state_choice_to_index,
    state_space_names,
    state_space,
    batch_info,
):
    # Select state_choice idxs in final period
    idx_state_choice_final_period = np.where(state_choice_space[:, 0] == n_periods - 1)[
        0
    ]
    # To solve the second last period, we need the child states in the last period
    # and the corresponding matrix, where each row is a state with the state choice
    # ids as entry in each choice
    states_final_period = state_space[state_space[:, 0] == n_periods - 1]
    # Now construct a tuple for indexing
    n_state_vars = states_final_period.shape[1]
    states_tuple = tuple(states_final_period[:, i] for i in range(n_state_vars))

    # Now get the matrix we use for choice aggregation
    state_to_choices_final_period = map_state_choice_to_index[states_tuple]
    # Normalize to be able to index in the interpolated values
    min_val = np.min(state_to_choices_final_period[state_to_choices_final_period > 0])
    state_to_choices_final_period -= min_val

    idx_state_choice_second_last_period = np.where(
        state_choice_space[:, 0] == n_periods - 2
    )[0]
    # Also normalize the state choice idxs
    child_states_second_last_period = map_state_choice_to_child_states[
        idx_state_choice_second_last_period
    ]
    min_val = np.min(
        child_states_second_last_period[child_states_second_last_period > 0]
    )
    child_states_second_last_period -= min_val

    # Also add parent states in last period
    parent_states_final_period = map_state_choice_to_parent_state[
        idx_state_choice_final_period
    ]
    batch_info = {
        **batch_info,
        "idx_state_choices_final_period": idx_state_choice_final_period,
        "idx_state_choices_second_last_period": idx_state_choice_second_last_period,
        "idxs_parent_states_final_period": parent_states_final_period,
        "state_to_choices_final_period": state_to_choices_final_period,
        "child_states_second_last_period": child_states_second_last_period,
    }

    # Also add state choice mat as dictionary for each of the two periods
    for idx, period_name in [
        (idx_state_choice_final_period, "final"),
        (idx_state_choice_second_last_period, "second_last"),
    ]:
        batch_info[f"state_choice_mat_{period_name}_period"] = {
            key: state_choice_space[:, i][idx]
            for i, key in enumerate(state_space_names + ["choice"])
        }
    return batch_info


def determine_optimal_batch_size(
    state_choice_space,
    n_periods,
    map_state_choice_to_child_states,
    map_state_choice_to_index,
    state_space,
):
    state_choice_space_wo_last_two = state_choice_space[
        state_choice_space[:, 0] < n_periods - 2
    ]
    state_choice_index_back = np.arange(
        state_choice_space_wo_last_two.shape[0], dtype=int
    )

    # Filter out last period state_choice_ids
    child_states_idx_backward = map_state_choice_to_child_states[
        state_choice_space[:, 0] < n_periods - 2
    ]
    breakpoint()
    child_states = np.take(state_space, child_states_idx_backward, axis=0)
    n_state_vars = state_space.shape[1]

    size_last_batch = state_choice_space[
        state_choice_space[:, 0] == state_choice_space_wo_last_two[-1, 0]
    ].shape[0]

    batch_not_found = True
    current_batch_size = size_last_batch
    need_to_reduce_batchsize = False
    while batch_not_found:
        if need_to_reduce_batchsize:
            current_batch_size = int(current_batch_size * 0.95)
            need_to_reduce_batchsize = False
        # Split state choice indexes in
        index_to_spilt = np.arange(
            current_batch_size,
            state_choice_index_back.shape[0],
            current_batch_size,
        )

        batches_to_check = np.split(
            np.flip(state_choice_index_back),
            index_to_spilt,
        )
        child_states_to_integrate_exog = []
        child_state_choices_to_aggr_choice = []
        child_state_choice_idxs_to_interpolate = []

        for i, batch in enumerate(batches_to_check):
            child_states_idxs = map_state_choice_to_child_states[batch]
            unique_child_states, unique_ids, inverse_ids = np.unique(
                child_states_idxs, return_index=True, return_inverse=True
            )

            child_states_to_integrate_exog += [
                inverse_ids.reshape(child_states_idxs.shape)
            ]

            # Get child states for current batch of state choices
            child_states_batch = np.take(child_states, batch, axis=0).reshape(
                -1, n_state_vars
            )

            # Make tuple out of columns of child states
            child_states_tuple = tuple(
                child_states_batch[:, i] for i in range(n_state_vars)
            )

            # Get ids of state choices for each child state
            unique_state_choice_idxs_childs = map_state_choice_to_index[
                child_states_tuple
            ][unique_ids]

            # Get minimum of the positive numbers in state_choice_idxs_childs
            min_state_choice_idx = np.min(
                unique_state_choice_idxs_childs[unique_state_choice_idxs_childs > 0]
            )
            # Save the unique normalized child states
            child_state_choices_to_aggr_choice += [
                unique_state_choice_idxs_childs - min_state_choice_idx
            ]
            # Unique child state choices
            child_state_choice_idxs_to_interpolate += [
                np.unique(
                    unique_state_choice_idxs_childs[unique_state_choice_idxs_childs > 0]
                )
            ]
            # Now check if the smallest index of the child state choices is larger than
            # the maximum index of the batch, i.e. if all state choice relevant to
            # solve the current state choices of the batch are in previous batches
            if batch.max() > min_state_choice_idx:
                batch_not_found = True
                need_to_reduce_batchsize = True
                break

        if not need_to_reduce_batchsize:
            batch_not_found = False

        print("The batch size of the backwards induction is ", current_batch_size)
        print("It failed in batch ", i)

    return (
        batches_to_check,
        child_state_choice_idxs_to_interpolate,
        child_state_choices_to_aggr_choice,
        child_states_to_integrate_exog,
    )
