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
#
import bapsflib
import copy
import numpy as np
import os

from warnings import warn


class HDFReadMSI(np.recarray):
    """
    Reads MSI diagnostic data from the HDF5 file.

    This class constructs and returns a structured numpy array.  The
    data in the array is grouped in three categories:

    1. shot numbers which are contained in the :code:`'shotnum'` field
    2. metadata data that is both shot number and diagnostic specific
       which is stored in the sub-fields of the :code:`'meta'` field
    3. recorded data arrays which get unique fields based on their
       mapping :attr:`configs` attribute

    Data that is not shot number specific is stored in the :attr:`info`
    attribute.

    :Example: Here the :code:`'Discharge'` MSI diagnostic is used as an
        example:

        >>> # open HDF5 file
        >>> f = bapsflib.lapd.File('test.hdf5')
        >>>
        >>> # read MSI data
        >>> # - this is equivalent to f.read_msi('Discharge')
        >>> mdata = HDFReadMSI(f, 'Discharge')
        >>> mdata.dtype
        dtype([('shotnum', '<i4'),
               ('voltage', '<f4', (2048,)),
               ('current', '<f4', (2048,)),
               ('meta', [('timestamp', '<f8'),
                         ('data valid', 'i1'),
                         ('pulse length', '<f4'),
                         ('peak current', '<f4'),
                         ('bank voltage', '<f4')])])
        >>> # display shot numbers
        >>> mdata['shotnum']
        array([    0, 19251], dtype=int32)
        >>>
        >>> # data arrays correspond to fields 'voltage' and 'current'
        >>> # - display first 3 elements of shot number 0 for 'voltage'
        >>> mdata['voltage'][0,0:3:]
        array([-46.99707 , -46.844482, -46.99707], dtype=float32)
        >>>
        >>> # display peak current for shot number 0
        >>> mdata['meta']['peak current'][0]
        6127.1323
        >>>
        >>> # the `info` attribute has diagnostic specific data
        >>> mdata.info
        {'current conversion factor': [0.0],
         'diagnostic name': 'Discharge',
         'diagnostic path': '/MSI/Discharge',
         'dt': [4.88e-05],
         'hdf file': 'test.hdf5',
         't0': [-0.0249856],
         'voltage conversion factor': [0.0]}
        >>>
        >>> # get time step for the data arrays
        >>> mdata.info['dt'][0]
        4.88e-05

    """
    warn("attribute access to numpy array fields will be deprecated "
         "by Oct., access fields like data['shotnum'] NOT like "
         "data.shotnum",
         FutureWarning)

    def __new__(cls, hdf_file: bapsflib.lapd.File, dname: str,
                **kwargs):
        """
        :param hdf_file: HDF5 file object
        :param str dname: name of desired MSI diagnostic
        """
        # ---- Condition `hdf_file` ----
        # grab file_map
        # - also ensure hdf_file is a lapd.file object
        #
        if not isinstance(hdf_file, bapsflib.lapd.File):
            raise TypeError(
                '`hdf_file` needs to be of type `lapd.File`')

        # ---- Condition `dname` ----
        # ensure dname is a string
        if not isinstance(dname, str):
            raise TypeError('arg `dname` needs to be a str')

        # allow for alias names of MSI diagnostics
        aliases = [
            ('Discharge', ['discharge']),
            ('Gas pressure', ['gas pressure',
                              'pressure',
                              'partial pressure'
                              'partial pressures']),
            ('Heater', ['heater']),
            ('Interferometer array', ['interferometer array',
                                      'interferometer',
                                      'interarr']),
            ('Magnetic field', ['magnetic field',
                                'b',
                                'bfield']),
        ]
        for name, alias in aliases:
            if dname.lower() in alias:
                dname = name
                break

        # get diagnostic map
        try:
            diag_map = hdf_file.file_map.msi[dname]
        except KeyError:
            raise ValueError(
                'Specified MSI Diagnostic is not among known'
                'diagnostics')

        # ---- Construct shape and dtype for np.array ----
        shape = diag_map.configs['shape']

        # initialize dtype_list
        # add 'shotnum' field
        dtype_list = [
            ('shotnum', diag_map.configs['shotnum']['dtype']),
        ]

        # add signal fields
        sig_shape = None
        for field in diag_map.configs['signals']:
            shape_list = diag_map.configs['signals'][field]['shape']
            if len(shape_list) != 1:
                # need to ensure all datasets have the same dimensions
                # - currently no handling datasets with differing dims
                if shape_list.count(shape_list[0]) != len(shape_list):
                    raise ValueError(
                        "Can not handle grouping of datasets with "
                        "differing shapes")

            # ensure all signal fields have the same number of rows
            # - if ndims = 1, then assuming one row
            if sig_shape is None:
                sig_shape = shape_list[0]
            else:
                if len(sig_shape) != len(shape_list[0]):
                    raise ValueError(
                        "all signal fields must have the same number"
                        "of rows")
                elif len(sig_shape) != 1:
                    if sig_shape[0] != shape_list[0][0]:
                        raise ValueError(
                            "all signal fields must have the same "
                            "number of rows")

            # add
            dtype_list.append((
                field,
                diag_map.configs['signals'][field]['dtype'],
                shape_list[0]
            ))

        # add 'meta' fields
        # - all 'meta' fields needs to have the same number of rows as
        #   the signal fields
        # TODO: NEED TO ADD MORE CONDITIONING OF CONSISTENT SHAPE VALUES
        meta_shape = diag_map.configs['meta']['shape']
        meta_dtype_list = []
        for field in diag_map.configs['meta']:
            # skip the 'shape' field
            if field == 'shape':
                continue

            # ensure every entry has the same shape
            shape_list = diag_map.configs['meta'][field]['shape']
            if len(shape_list) != 1:
                # need to ensure all datasets have the same dimensions
                # - currently no handling datasets with differing dims
                if shape_list.count(shape_list[0]) != len(shape_list):
                    raise ValueError(
                        "Can not handle grouping of datasets with "
                        "differing shapes")

            # add to meta_dtype_list
            meta_dtype_list.append((
                field,
                diag_map.configs['meta'][field]['dtype'],
                shape_list[0]
            ))

        # add 'meta' to dtype_list
        dtype_list.append((
            'meta',
            meta_dtype_list,
            meta_shape
        ))

        # define dtype
        dtype = np.dtype(dtype_list)

        # ---- Define and Populate Numpy Array ----
        data = np.empty(shape, dtype=dtype)

        # fill 'shotnum'
        # TODO: ADD CASE FOR 'DSET FIELD' IS NONE
        sn_config = diag_map.configs['shotnum']
        for ii, path in enumerate(sn_config['dset paths']):
            # get dataset
            dset = hdf_file[path]

            # fill array
            if ii == 0:
                data['shotnum'] = dset[:, sn_config['dset field']]
            else:
                if not np.array_equal(data['shotnum'],
                                      dset[sn_config['dset field']]):
                    raise ValueError(
                        'Datasets do NOT have the same shot number '
                        'values, do NOT know how to handle')

        # fill 'signals'
        # TODO: ADD CASE FOR 'DSET FIELD' IS NOT NONE
        sig_config = diag_map.configs['signals']
        for field in sig_config:
            if len(sig_config[field]['dset paths']) == 1:
                # get dataset
                path = sig_config[field]['dset paths'][0]
                dset = hdf_file[path]

                # fill array
                data[field] = dset
            else:
                # there are multiple rows in the dataset
                # (e.g. interferometer)
                for ii, path in \
                        enumerate(sig_config[field]['dset paths']):
                    # get dataset
                    dset = hdf_file[path]

                    # fill array
                    data[field][:, ii, ...] = dset

        # fill 'meta'
        # TODO: ADD CASE FOR 'DSET FIELD' IS NONE
        meta_config = diag_map.configs['meta']
        for field in meta_config:
            # skip 'shape' key
            if field == 'shape':
                continue

            # scan thru all datasets
            if len(meta_config[field]['dset paths']) == 1:
                # get dataset
                path = meta_config[field]['dset paths'][0]
                dset = hdf_file[path]

                # fill array
                data['meta'][field] = \
                    dset[meta_config[field]['dset field']]
            else:
                # there are multiple rows in the dataset
                # (e.g. interferometer)
                for ii, path in \
                        enumerate(meta_config[field]['dset paths']):
                    # get dataset
                    dset = hdf_file[path]

                    # fill array
                    data['meta'][field][:, ii, ...] = \
                        dset[meta_config[field]['dset field']]

        # ---- Define `obj` ----
        obj = data.view(cls)

        # ---- Define `info` attribute ----
        obj._info = {
            'source file': os.path.abspath(hdf_file.filename),
            'device name': diag_map.info['group name'],
            'device group path': diag_map.info['group path']
        }
        for key, val in diag_map.configs.items():
            if key not in ['shape', 'shotnum', 'signals', 'meta']:
                obj._info[key] = copy.deepcopy(val)

        # ---- Return `obj` ----
        return obj

    def __array_finalize__(self, obj):
        # This should only be True during explicit construction
        # if obj is None:
        if obj is None or obj.__class__ is np.ndarray:
            return

        # Define _info attribute
        # (for view casting and new from template)
        self._info = getattr(obj, '_info', {
            'source file': None,
            'device name': None,
            'device group path': None,
        })

    @property
    def info(self):
        """A dictionary of metadata for the MSI diagnostic."""
        return self._info
