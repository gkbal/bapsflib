# This file is part of the bapsflib package, a Python toolkit for the
# BaPSF group at UCLA.
#
# http://plasma.physics.ucla.edu/
#
# Copyright 2017-2018 Erik T. Everson and contributors
#
# License: Standard 3-clause BSD; see "LICENSES/LICENSE.txt" for full
#   license terms and contributor agreement.
#
"""
Helper functions that are utilized by the the HDF5 utility classes
defined in module :mod:`bapslib._hdf.utils`.
"""
import h5py
import numpy as np

from typing import (Any, Dict, Iterable, List, Tuple)

from .file import File


def condition_controls(hdf_file: File,
                       controls: Any) -> List[Tuple[str, Any]]:
    """
    Conditions the **controls** argument for
    :class:`~.hdfreadcontrol.HDFReadControl` and
    :class:`~.hdfreaddata.HDFReadData`.

    :param hdf_file: HDF5 object instance
    :param controls: `controls` argument to be conditioned
    :return: list containing tuple pairs of control device name and
        desired configuration name

    :Example:

        >>> from bapsflib import lapd
        >>> f = lapd.File('sample.hdf5')
        >>> controls = ['Wavefrom', ('6K Compumotor', 3)]
        >>> conditioned_controls = condition_controls(f, controls)
        >>> conditioned_controls
        [('Waveform', 'config01'), ('6K Compumotor', 3)]

    .. admonition:: Condition Criteria

        #. Input **controls** should be
           :code:`Union[str, Iterable[Union[str, Tuple[str, Any]]]]`
        #. There can only be one control for each
           :class:`~bapsflib._hdf.maps.controls.contype.ConType`.
        #. If a control has multiple configurations, then one must be
           specified.
        #. If a control has ONLY ONE configuration, then that will be
           assumed (and checked against the specified configuration).
    """
    # grab instance of file mapping
    _fmap = hdf_file.file_map

    # -- condition 'controls' argument                              ----
    # - controls is:
    #   1. a string or Iterable
    #   2. each element is either a string or tuple
    #   3. if tuple, then length <= 2
    #      ('control name',) or ('control_name', config_name)
    #
    # check if NULL
    if not bool(controls):
        # catch a null controls
        raise ValueError('controls argument is NULL')

    # make string a list
    if isinstance(controls, str):
        controls = [controls]

    # condition Iterable
    if isinstance(controls, Iterable):
        # all list items have to be strings or tuples
        if not all(isinstance(con, (str, tuple)) for con in controls):
            raise TypeError('all elements of `controls` must be of '
                            'type string or tuple')

        # condition controls
        new_controls = []
        for control in controls:
            if isinstance(control, str):
                name = control
                config_name = None
            else:
                # tuple case
                if len(control) > 2:
                    raise ValueError(
                        "a `controls` tuple element must be specified "
                        "as ('control name') or, "
                        "('control name', config_name)")

                name = control[0]
                config_name = None if len(control) == 1 else control[1]

            # ensure proper control and configuration name are defined
            if name in [cc[0] for cc in new_controls]:
                raise ValueError(
                    'Control device ({})'.format(control)
                    + ' can only have one occurrence in controls')
            elif name in _fmap.controls:
                if config_name in _fmap.controls[name].configs:
                    # all is good
                    pass
                elif len(_fmap.controls[name].configs) == 1 \
                        and config_name is None:
                    config_name = list(_fmap.controls[name].configs)[0]
                else:
                    raise ValueError(
                        "'{}' is not a valid ".format(config_name)
                        + "configuration name for control device "
                        + "'{}'".format(name))
            else:
                raise ValueError('Control device ({})'.format(name)
                                 + ' not in HDF5 file')

            # add control to new_controls
            new_controls.append((name, config_name))
    else:
        raise TypeError('`controls` argument is not Iterable')

    # re-assign `controls`
    controls = new_controls

    # enforce one control per contype
    checked = []
    for control in controls:
        # control is a tuple, not a string
        contype = _fmap.controls[control[0]].contype

        if contype in checked:
            raise TypeError('`controls` has multiple devices per '
                            'contype')
        else:
            checked.append(contype)

    # return conditioned list
    return controls


def condition_shotnum(shotnum: Any,
                      dset_dict: Dict[str, h5py.Dataset],
                      shotnumkey_dict: Dict[str, str]) -> np.ndarray:
    """
    Conditions the **shotnum** argument for
    :class:`~bapsflib._hdf.utils.hdfreadcontrol.HDFReadControl` and
    :class:`~bapsflib._hdf.utils.hdfreaddata.HDFReadData`.

    :param shotnum: desired HDF5 shot numbers
    :param dset_dict: dictionary of all control dataset instances
    :param shotnumkey_dict: dictionary of the shot number field name
        for each control dataset in dset_dict
    :return: conditioned **shotnum** numpy array

    .. admonition:: Condition Criteria

        #. Input **shotnum** should be
           :code:`Union[int, List[int,...], slice, np.ndarray]`
        #. Any :math:`\mathbf{shotnum} \le 0` will be removed.
        #. A :code:`ValueError` will be thrown if the conditioned array
           is NULL.
    """
    # Acceptable `shotnum` types
    # 1. int
    # 2. slice() object
    # 3. List[int, ...]
    # 4. np.array (dtype = np.integer and ndim = 1)
    #
    # Catch each `shotnum` type and convert to numpy array
    #
    if isinstance(shotnum, int):
        if shotnum <= 0 or isinstance(shotnum, bool):
            raise ValueError(
                "Valid `shotnum` ({})".format(shotnum)
                + " not passed. Resulting array would be NULL.")

        # convert
        shotnum = np.array([shotnum], dtype=np.uint32)

    elif isinstance(shotnum, list):
        # ensure all elements are int
        if not all(isinstance(sn, int) for sn in shotnum):
            raise ValueError('Valid `shotnum` not passed. All values '
                             'NOT int.')

        # remove shot numbers <= 0
        shotnum.sort()
        shotnum = list(set(shotnum))
        shotnum.sort()
        if min(shotnum) <= 0:
            # remove values less-than or equal to 0
            new_sn = [sn for sn in shotnum if sn > 0]
            shotnum = new_sn

        # ensure not NULL
        if len(shotnum) == 0:
            raise ValueError('Valid `shotnum` not passed. Resulting '
                             'array would be NULL')

        # convert
        shotnum = np.array(shotnum, dtype=np.uint32)

    elif isinstance(shotnum, slice):
        # determine largest possible shot number
        last_sn = [
            dset_dict[cname][-1, shotnumkey_dict[cname]] + 1
            for cname in dset_dict
        ]
        if shotnum.stop is not None:
            last_sn.append(shotnum.stop)
        stop_sn = max(last_sn)

        # get the start, stop, and step for the shot number array
        start, stop, step = shotnum.indices(stop_sn)

        # re-define `shotnum`
        shotnum = np.arange(start, stop, step, dtype=np.int32)

        # remove shot numbers <= 0
        shotnum = np.delete(shotnum, np.where(shotnum <= 0)[0])
        shotnum = shotnum.astype(np.uint32)

        # ensure not NULL
        if shotnum.size == 0:
            raise ValueError('Valid `shotnum` not passed. Resulting '
                             'array would be NULL')

    elif isinstance(shotnum, np.ndarray):
        shotnum = shotnum.squeeze()
        if shotnum.ndim != 1 \
                or not np.issubdtype(shotnum.dtype, np.integer) \
                or bool(shotnum.dtype.names):
            raise ValueError('Valid `shotnum` not passed')

        # remove shot numbers <= 0
        shotnum.sort()
        shotnum = np.delete(shotnum, np.where(shotnum <= 0)[0])
        shotnum = shotnum.astype(np.uint32)

        # ensure not NULL
        if shotnum.size == 0:
            raise ValueError('Valid `shotnum` not passed. Resulting '
                             'array would be NULL')
    else:
        raise ValueError('Valid `shotnum` not passed')

    # return
    return shotnum
