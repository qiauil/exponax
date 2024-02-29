from typing import Callable, Union

import jax
import jax.numpy as jnp
import jax.random as jr
import jax.tree_util as jtu
import matplotlib.pyplot as plt
from jaxtyping import Array, Float, PRNGKeyArray, PyTree
from matplotlib.animation import FuncAnimation


def get_grid(
    num_spatial_dims: int,
    domain_extent: float,
    num_points: int,
    *,
    full: bool = False,
    zero_centered: bool = False,
    indexing: str = "ij",
) -> Float[Array, "D ... N"]:
    """
    Return a grid in the spatial domain. A grid in d dimensions is an array of
    shape (d,) + (num_points,)*d with the first axis representing all coordiate
    inidices.

    Notice, that if `num_spatial_dims = 1`, the returned array has a singleton
    dimension in the first axis, i.e., the shape is `(1, num_points)`.

    **Arguments:**
        - `num_spatial_dims`: The number of spatial dimensions.
        - `domain_extent`: The extent of the domain in each spatial dimension.
        - `num_points`: The number of points in each spatial dimension.
        - `full`: Whether to include the right boundary point in the grid.
          Default: `False`. The right point is redundant for periodic boundary
            conditions and is not considered a degree of freedom. Use this
            option, for example, if you need a full grid for plotting.
        - `zero_centered`: Whether to center the grid around zero. Default:
            `False`. By default the grid considers a domain of (0,
            domain_extent)^(num_spatial_dims).
        - `indexing`: The indexing convention to use. Default: `'ij'`.

    **Returns:**
        - `grid`: The grid in the spatial domain. Shape: `(num_spatial_dims,
            ..., num_points)`.
    """
    if full:
        grid_1d = jnp.linspace(0, domain_extent, num_points + 1, endpoint=True)
    else:
        grid_1d = jnp.linspace(0, domain_extent, num_points, endpoint=False)

    if zero_centered:
        grid_1d -= domain_extent / 2

    grid_list = [
        grid_1d,
    ] * num_spatial_dims

    grid = jnp.stack(
        jnp.meshgrid(*grid_list, indexing=indexing),
    )

    return grid


def wrap_bc(u):
    """
    Wraps the periodic boundary conditions around the array `u`.

    This can be used to plot the solution of a periodic problem on the full
    interval [0, L] by plotting `wrap_bc(u)` instead of `u`.

    **Parameters:**
        - `u`: The array to wrap, shape `(N,)`.

    **Returns:**
        - `u_wrapped`: The wrapped array, shape `(N + 1,)`.
    """
    _, *spatial_shape = u.shape
    num_spatial_dims = len(spatial_shape)

    padding_config = ((0, 0),) + ((0, 1),) * num_spatial_dims
    u_wrapped = jnp.pad(u, padding_config, mode="wrap")

    return u_wrapped


def rollout(
    stepper_fn: Union[Callable[[PyTree], PyTree], Callable[[PyTree, PyTree], PyTree]],
    n: int,
    *,
    include_init: bool = False,
    takes_aux: bool = False,
    constant_aux: bool = True,
):
    """
    Transform a stepper function into a function that autoregressively (i.e.,
    recursively applied to its own output) produces a trajectory of length `n`.

    Based on `takes_aux`, the stepper function is either fully automomous, just
    mapping state to state, or takes an additional auxiliary input. This can be
    a force/control or additional metadata (like physical parameters, or time
    for non-autonomous systems).

    Args:
        - `stepper_fn`: The time stepper to transform. If `takes_aux = False`
            (default), expected signature is `u_next = stepper_fn(u)`, else
            `u_next = stepper_fn(u, aux)`. `u` and `u_next` need to be PyTrees
            of identical structure, in the easiest case just arrays of same
            shape.
        - `n`: The number of time steps to rollout the trajectory into the
            future. If `include_init = False` (default) produces the `n` steps
            into the future.
        - `include_init`: Whether to include the initial condition in the
            trajectory. If `True`, the arrays in the returning PyTree have shape
            `(n + 1, ...)`, else `(n, ...)`. Default: `False`.
        - `takes_aux`: Whether the stepper function takes an additional PyTree
            as second argument.
        - `constant_aux`: Whether the auxiliary input is constant over the
            trajectory. If `True`, the auxiliary input is repeated `n` times,
            otherwise the leading axis in the PyTree arrays has to be of length
            `n`.

    Returns:
        - `rollout_stepper_fn`: A function that takes an initial condition `u_0`
            and an auxiliary input `aux` (if `takes_aux = True`) and produces
            the trajectory by autoregressively applying the stepper `n` times.
            If `include_init = True`, the trajectory has shape `(n + 1, ...)`,
            else `(n, ...)`. Returns a PyTree of the same structure as the
            initial condition, but with an additional leading axis of length
            `n`.
    """

    if takes_aux:

        def scan_fn(u, aux):
            u_next = stepper_fn(u, aux)
            return u_next, u_next

        def rollout_stepper_fn(u_0, aux):
            if constant_aux:
                aux = jtu.tree_map(
                    lambda x: jnp.repeat(jnp.expand_dims(x, axis=0), n, axis=0), aux
                )

            _, trj = jax.lax.scan(scan_fn, u_0, aux, length=n)

            if include_init:
                trj_with_init = jtu.tree_map(
                    lambda init, history: jnp.concatenate(
                        [jnp.expand_dims(init, axis=0), history], axis=0
                    ),
                    u_0,
                    trj,
                )
                return trj_with_init
            else:
                return trj

        return rollout_stepper_fn

    else:

        def scan_fn(u, _):
            u_next = stepper_fn(u)
            return u_next, u_next

        def rollout_stepper_fn(u_0):
            _, trj = jax.lax.scan(scan_fn, u_0, None, length=n)

            if include_init:
                trj_with_init = jtu.tree_map(
                    lambda init, history: jnp.concatenate(
                        [jnp.expand_dims(init, axis=0), history], axis=0
                    ),
                    u_0,
                    trj,
                )
                return trj_with_init
            else:
                return trj

        return rollout_stepper_fn


def repeat(
    stepper_fn: Union[Callable[[PyTree], PyTree], Callable[[PyTree, PyTree], PyTree]],
    n: int,
    *,
    takes_aux: bool = False,
    constant_aux: bool = True,
):
    """
    Transform a stepper function into a function that autoregressively (i.e.,
    recursively applied to its own output) applies the stepper `n` times and
    returns the final state.

    Based on `takes_aux`, the stepper function is either fully automomous, just
    mapping state to state, or takes an additional auxiliary input. This can be
    a force/control or additional metadata (like physical parameters, or time
    for non-autonomous systems).

    Args:
        - `stepper_fn`: The time stepper to transform. If `takes_aux = False`
            (default), expected signature is `u_next = stepper_fn(u)`, else
            `u_next = stepper_fn(u, aux)`. `u` and `u_next` need to be PyTrees
            of identical structure, in the easiest case just arrays of same
            shape.
        - `n`: The number of times to apply the stepper.
        - `takes_aux`: Whether the stepper function takes an additional PyTree
            as second argument.
        - `constant_aux`: Whether the auxiliary input is constant over the
            trajectory. If `True`, the auxiliary input is repeated `n` times,
            otherwise the leading axis in the PyTree arrays has to be of length
            `n`.

    Returns:
        - `repeated_stepper_fn`: A function that takes an initial condition
            `u_0` and an auxiliary input `aux` (if `takes_aux = True`) and
            produces the final state by autoregressively applying the stepper
            `n` times. Returns a PyTree of the same structure as the initial
            condition.
    """

    if takes_aux:

        def scan_fn(u, aux):
            u_next = stepper_fn(u, aux)
            return u_next, None

        def repeated_stepper_fn(u_0, aux):
            if constant_aux:
                aux = jtu.tree_map(
                    lambda x: jnp.repeat(jnp.expand_dims(x, axis=0), n, axis=0), aux
                )

            final, _ = jax.lax.scan(scan_fn, u_0, aux, length=n)
            return final

        return repeated_stepper_fn

    else:

        def scan_fn(u, _):
            u_next = stepper_fn(u)
            return u_next, None

        def repeated_stepper_fn(u_0):
            final, _ = jax.lax.scan(scan_fn, u_0, None, length=n)
            return final

        return repeated_stepper_fn


def stack_sub_trajectories(
    trj: PyTree[Float[Array, "n_timesteps ..."]],
    sub_len: int,
) -> PyTree[Float[Array, "n_stacks sub_len ..."]]:
    """
    Slice a trajectory into subtrajectories of length `n` and stack them
    together. Useful for rollout training neural operators with temporal mixing.

    !!! Note that this function can produce very large arrays.

    **Arguments:**
        - `trj`: The trajectory to slice. Expected shape: `(n_timesteps, ...)`.
        - `sub_len`: The length of the subtrajectories. If you want to perform rollout
            training with k steps, note that `n=k+1` to also have an initial
            condition in the subtrajectories.

    **Returns:**
        - `sub_trjs`: The stacked subtrajectories. Expected shape: `(n_stacks,
            n, ...)`. `n_stacks` is the number of subtrajectories stacked
            together, i.e., `n_timesteps - n + 1`.
    """
    n_time_steps = [leaf.shape[0] for leaf in jtu.tree_leaves(trj)]

    if len(set(n_time_steps)) != 1:
        raise ValueError(
            "All arrays in trj must have the same number of time steps in the leading axis"
        )
    else:
        n_time_steps = n_time_steps[0]

    if sub_len > n_time_steps:
        raise ValueError(
            "n must be smaller than or equal to the number of time steps in trj"
        )

    n_sub_trjs = n_time_steps - sub_len + 1

    sub_trjs = jtu.tree_map(
        lambda trj: jnp.stack(
            [trj[i : i + sub_len] for i in range(n_sub_trjs)], axis=0
        ),
        trj,
    )

    return sub_trjs


def get_animation(trj, *, vlim=(-1, 1)):
    fig, ax = plt.subplots()
    im = ax.imshow(
        trj[0].squeeze().T, vmin=vlim[0], vmax=vlim[1], cmap="RdBu_r", origin="lower"
    )
    im.set_data(jnp.zeros_like(trj[0]).squeeze())

    def animate(i):
        im.set_data(trj[i].squeeze().T)
        fig.suptitle(f"t_i = {i:04d}")
        return im

    plt.close(fig)

    ani = FuncAnimation(fig, animate, frames=trj.shape[0], interval=100, blit=False)

    return ani


def get_grouped_animation(
    trj, *, vlim=(-1, 1), grid=(3, 3), figsize=(10, 10), titles=None
):
    """
    trj.shape = (n_trjs, n_timesteps, ...)
    """
    fig, ax_s = plt.subplots(*grid, sharex=True, sharey=True, figsize=figsize)
    im_s = []
    for i, ax in enumerate(ax_s.flatten()):
        im = ax.imshow(
            trj[i, 0].squeeze().T,
            vmin=vlim[0],
            vmax=vlim[1],
            cmap="RdBu_r",
            origin="lower",
        )
        im.set_data(jnp.zeros_like(trj[i, 0]).squeeze())
        im_s.append(im)

    def animate(i):
        for j, im in enumerate(im_s):
            im.set_data(trj[j, i].squeeze().T)
            if titles is not None:
                ax_s.flatten()[j].set_title(titles[j])
        fig.suptitle(f"t_i = {i:04d}")
        return im_s

    plt.close(fig)

    ani = FuncAnimation(fig, animate, frames=trj.shape[1], interval=100, blit=False)

    return ani


def build_ic_set(
    ic_generator,
    *,
    num_points: int,
    num_samples: int,
    key: PRNGKeyArray,
) -> Float[Array, "S 1 ... N"]:
    """
    Generate a set of initial conditions by sampling from a given initial
    condition distribution and evaluating the function on the given grid.

    **Arguments:**
        - `ic_generator`: A function that takes a PRNGKey and returns a
            function that takes a grid and returns a sample from the initial
            condition distribution.
        - `num_samples`: The number of initial conditions to sample.
        - `key`: The PRNGKey to use for sampling.

    **Returns:**
        - `ic_set`: The set of initial conditions. Shape: `(S, 1, ..., N)`.
            `S = num_samples`.
    """

    def scan_fn(k, _):
        k, sub_k = jr.split(k)
        ic = ic_generator(num_points, key=sub_k)
        return k, ic

    _, ic_set = jax.lax.scan(scan_fn, key, None, length=num_samples)

    return ic_set
