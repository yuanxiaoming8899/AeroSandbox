import numpy as _onp
import casadi as _cas
from aerosandbox.numpy.determine_type import is_casadi_type
from aerosandbox.numpy.array import array
from aerosandbox.numpy.conditionals import where
from aerosandbox.numpy.logicals import all, any, logical_or
from typing import Tuple
from scipy import interpolate as _interpolate


def interp(x, xp, fp, left=None, right=None, period=None):
    """
    One-dimensional linear interpolation, analogous to numpy.interp().

    Returns the one-dimensional piecewise linear interpolant to a function with given discrete data points (xp, fp),
    evaluated at x.

    See syntax here: https://numpy.org/doc/stable/reference/generated/numpy.interp.html

    Specific notes: xp is assumed to be sorted.
    """
    if not is_casadi_type([x, xp, fp], recursive=True):
        return _onp.interp(
            x=x,
            xp=xp,
            fp=fp,
            left=left,
            right=right,
            period=period
        )

    else:
        ### If xp or x are CasADi types, this is unsupported :(
        if is_casadi_type([x, xp], recursive=True):
            raise NotImplementedError(
                "Unfortunately, CasADi doesn't yet support a dispatch for x or xp as CasADi types."
            )

        ### Handle period argument
        if period is not None:
            if any(
                    logical_or(
                        xp < 0,
                        xp > period
                    )
            ):
                raise NotImplementedError(
                    "Haven't yet implemented handling for if xp is outside the period.")  # Not easy to implement because casadi doesn't have a sort feature.

            x = _cas.mod(x, period)

        ### Make sure x isn't an int
        if isinstance(x, int):
            x = float(x)

        ### Make sure that x is an iterable
        try:
            x[0]
        except TypeError:
            x = array([x], dtype=float)

        ### Make sure xp is an iterable
        xp = array(xp, dtype=float)

        ### Do the interpolation
        f = _cas.interp1d(
            xp,
            fp,
            x
        )

        ### Handle left/right
        if left is not None:
            f = where(
                x < xp[0],
                left,
                f
            )
        if right is not None:
            f = where(
                x > xp[-1],
                right,
                f
            )

        ### Return
        return f


def is_data_structured(
        x_data_coordinates: Tuple[_onp.ndarray],
        y_data_structured: _onp.ndarray
) -> bool:
    """
    Determines if the shapes of a given dataset are consistent with "structured" (i.e. gridded) data.

    For this to evaluate True, the inputs should be:

        x_data_coordinates: A tuple or list of 1D ndarrays that represent coordinates along each axis of a N-dimensional hypercube.

        y_data_structured: The values of some scalar defined on that N-dimensional hypercube, expressed as an
        N-dimesional array. In other words, y_data_structured is evaluated at `np.meshgrid(*x_data_coordinates,
        indexing="ij")`.

    Returns: Boolean of whether the above description is true.
    """
    try:
        for coordinates in x_data_coordinates:
            if len(coordinates.shape) != 1:
                return False

        implied_y_data_shape = tuple(len(coordinates) for coordinates in x_data_coordinates)
        if not y_data_structured.shape == implied_y_data_shape:
            return False
    except TypeError:  # if x_data_coordinates is not iterable, for instance
        return False
    except AttributeError:  # if y_data_structured has no shape, for instance
        return False

    return True


def interpn(
        points: Tuple[_onp.ndarray],
        values: _onp.ndarray,
        xi: _onp.ndarray,
        method: str = "linear",
        bounds_error=True,
        fill_value=_onp.NaN
) -> _onp.ndarray:
    """
    Performs multidimensional interpolation on regular grids. Analogue to scipy.interpolate.interpn().

    See syntax here: https://docs.scipy.org/doc/scipy/reference/generated/scipy.interpolate.interpn.html

    Args:

        points: The points defining the regular grid in n dimensions. Tuple of coordinates of each axis.

        values: The data on the regular grid in n dimensions.

        xi: The coordinates to sample the gridded data at.

        method: The method of interpolation to perform.

        bounds_error: If True, when interpolated values are requested outside of the domain of the input data,
        a ValueError is raised. If False, then fill_value is used.

        fill_value: If provided, the value to use for points outside of the interpolation domain. If None,
        values outside the domain are extrapolated.

    Returns: Interpolated values at input coordinates.

    """
    ### Check input types for points and values
    if is_casadi_type([points, values], recursive=True):
        raise TypeError("The underlying dataset (points, values) must consist of NumPy arrays.")

    ### Check dimensions of points
    for points_axis in points:
        points_axis = array(points_axis)
        if not len(points_axis.shape) == 1:
            raise ValueError("`points` must consist of a tuple of 1D ndarrays defining the coordinates of each axis.")

    ### Check dimensions of values
    implied_values_shape = tuple(len(points_axis) for points_axis in points)
    if not values.shape == implied_values_shape:
        raise ValueError(f"""
        The shape of `values` should be {implied_values_shape}. 
        """)

    if (  ### NumPy implementation
            not is_casadi_type([points, values, xi], recursive=True)
    ) and (
            (method == "linear") or (method == "nearest")
    ):
        return _interpolate.interpn(
            points=points,
            values=values,
            xi=xi,
            method=method,
            bounds_error=bounds_error,
            fill_value=fill_value
        )

    elif (  ### CasADi implementation
            (method == "linear") or (method == "bspline")
    ):

        ### If xi is an int or float, promote it to an array
        if isinstance(xi, int) or isinstance(xi, float):
            xi = array([xi])

        ### If xi is a NumPy array and 1D, convert it to 2D for this.
        if not is_casadi_type(xi, recursive=False) and len(xi.shape) == 1:
            xi = _onp.reshape(xi, (-1, 1))

        ### Check that xi is now 2D
        if not len(xi.shape) == 2:
            raise ValueError("`xi` must have the shape (n_points, n_dimensions)!")

        ### Transpose xi so that xi.shape is [n_points, n_dimensions].
        n_dimensions = len(points)
        if not len(points) in xi.shape:
            raise ValueError("`xi` must have the shape (n_points, n_dimensions)!")

        if not xi.shape[1] == n_dimensions:
            xi = xi.T
            assert xi.shape[1] == n_dimensions

        ### Check bounds_error
        for axis, axis_values in enumerate(points):
            axis_values_min = _onp.min(axis_values)
            axis_values_max = _onp.max(axis_values)

            axis_xi = xi[:, axis]

            if any(
                    logical_or(
                        axis_xi > axis_values_max,
                        axis_xi < axis_values_min
                    )
            ):
                raise ValueError(
                    f"One of the requested xi is out of bounds in dimension {axis}"
                )

        ### Do the interpolation
        values_flattened = _onp.ravel(values, order='F')
        interpolator = _cas.interpolant(
            'name',
            method,
            points,
            values_flattened
        )

        fi = interpolator(xi.T).T

        ### If DM output (i.e. a numeric value, convert that back to an array
        if isinstance(fi, _cas.DM):
            if fi.shape == (1, 1):
                return fi[0, 0]
            else:
                return _onp.array(fi, dtype=float).reshape(-1)

        # TODO bounds_error, fill_value

        return fi

    else:
        raise ValueError("Bad value of `method`!")