"""Event processors for SiPM data."""
from __future__ import annotations

from collections.abc import Sequence

import awkward as ak
import numpy as np
from lgdo import lh5, types

from .. import utils


def gather_pulse_data(
    datainfo: utils.DataInfo,
    tcm: utils.TCMData,
    table_names: Sequence[str],
    *,
    observable: str,
    pulse_mask: types.VectorOfVectors = None,
    a_thr_pe: float = None,
    t_loc_ns: float = None,
    dt_range_ns: Sequence[float] = None,
    t_loc_default_ns: float = None,
    drop_empty: bool = True,
) -> types.VectorOfVectors:
    """Gathers SiPM pulse data into a 3D :class:`~lgdo.types.vectorofvectors.VectorOfVectors`.

    The returned data structure specifies the event in the first axis, the SiPM
    channel in the second and the pulse index in the last.

    Pulse data can be optionally masked with `pulse_mask` or a mask can be
    built on the fly from the `a_thr_pe`, `t_loc_ns`, `dt_range_ns`,
    `t_loc_default_ns` arguments (see :func:`make_pulse_data_mask`).

    If `pulse_mask`, `a_thr_pe`, `t_loc_ns`, `dt_range_ns`, `t_loc_default_ns`
    are all ``None``, no masking is applied and the full data set is returned.

    Parameters
    ----------
    datainfo, tcm, table_names
        positional arguments automatically supplied by :func:`.build_evt`.
    observable
        name of the pulse parameter to be gathered, optionally prefixed by tier
        name (e.g. ``hit.energy_in_pe``). If no tier is specified, it defaults
        to ``hit``.
    pulse_mask
        3D mask object used to filter out pulse data. See
        :func:`make_pulse_data_mask`.
    a_thr_pe
        amplitude threshold (in photoelectrons) used to build a pulse mask with
        :func:`make_pulse_data_mask`, if `pulse_mask` is ``None``. The output
        pulse data will be such that the pulse amplitude is above this value.
    t_loc_ns
        location of the time window in which pulses must sit. If a 1D array is
        provided, it is interpreted as a list of locations for each event (can
        be employed to e.g. provide the actual HPGe pulse position)
    dt_range_ns
        tuple with dimension of the time window in which pulses must sit
        relative to `t_loc_ns`. If, for example, `t_loc_ns` is 48000 ns and
        `dt_range_ns` is (-1000, 5000) ns, the resulting window will be (47000,
        53000) ns.
    t_loc_default_ns
        default value for `t_loc_ns`, in case the supplied value is
        :any:`numpy.nan`.
    drop_empty
        if ``True``, drop empty arrays at the last axis (the pulse axis), i.e.
        drop channels with no pulse data. The filtering is applied after the
        application of the mask.
    """
    # parse observables string. default to hit tier
    p = observable.split(".")
    tier = p[0] if len(p) > 1 else "hit"
    column = p[1] if len(p) > 1 else p[0]

    tierinfo = datainfo._asdict()[tier]

    # loop over selected table_names and load hit data
    concatme = []
    for channel in table_names:
        table_id = utils.get_tcm_id_by_pattern(tierinfo.table_fmt, channel)

        # determine list of indices found in the TCM that we want to load for channel
        idx = tcm.idx[tcm.id == table_id]

        # read the data in
        lgdo_obj = lh5.read(
            f"/{channel}/{tierinfo.group}/{column}", tierinfo.file, idx=idx
        )
        data = lgdo_obj.view_as(library="ak")

        # remove nans (this happens when SiPM data is stored as ArrayOfEqualSizedArrays)
        data = ak.drop_none(ak.nan_to_none(data))

        # increase the dimensionality by one (events)
        data = ak.unflatten(data, np.full(data.layout.length, 1, dtype="uint8"))

        concatme.append(data)

    # concatenate along the event axes (i.e. gather table_names together)
    data = ak.concatenate(concatme, axis=1)

    # check if user wants to apply a mask
    if pulse_mask is None and any(
        [kwarg is not None for kwarg in (a_thr_pe, t_loc_ns, dt_range_ns)]
    ):
        # generate the time/amplitude mask from parameters
        pulse_mask = make_pulse_data_mask(
            datainfo,
            tcm,
            table_names,
            a_thr_pe=a_thr_pe,
            t_loc_ns=t_loc_ns,
            dt_range_ns=dt_range_ns,
            t_loc_default_ns=t_loc_default_ns,
        )

    if pulse_mask is not None:
        if not isinstance(pulse_mask, ak.Array):
            pulse_mask = pulse_mask.view_as("ak")

        # apply the mask
        data = data[pulse_mask]

    # remove empty arrays = table_names with no pulses
    if drop_empty:
        data = data[ak.count(data, axis=-1) > 0]

    return types.VectorOfVectors(data, attrs=utils.copy_lgdo_attrs(lgdo_obj))


def gather_tcm_id_data(
    datainfo: utils.DataInfo,
    tcm: utils.TCMData,
    table_names: Sequence[str],
    *,
    pulse_mask=None,
    a_thr_pe=None,
    t_loc_ns=None,
    dt_range_ns=None,
    t_loc_default_ns=None,
    drop_empty=True,
) -> types.VectorOfVectors:
    """Gather TCM ids (i.e. channel identifiers) into a 2D :class:`~lgdo.types.vectorofvectors.VectorOfVectors`.

    The returned data structure specifies the event in the first axis and the
    SiPM channel identifier. Can be used to filter out data from
    :func:`gather_pulse_data` based on SiPM channel provenance.

    If `drop_empty` is ``True``, channel ids with no pulse data associated are
    removed.

    See :func:`gather_pulse_data` for documentation about the other function
    arguments.
    """
    # loop over selected table_names and load hit data
    table_ids = [
        utils.get_tcm_id_by_pattern(datainfo.hit.table_fmt, channel)
        for channel in table_names
    ]

    data = ak.Array(
        np.full(
            shape=(len(tcm.cumulative_length), len(table_ids)), fill_value=table_ids
        )
    )

    # check if user wants to apply a mask
    if drop_empty:
        if pulse_mask is None and any(
            [kwarg is not None for kwarg in (a_thr_pe, t_loc_ns, dt_range_ns)]
        ):
            # generate the time/amplitude mask from parameters
            pulse_mask = make_pulse_data_mask(
                datainfo,
                tcm,
                table_names,
                a_thr_pe=a_thr_pe,
                t_loc_ns=t_loc_ns,
                dt_range_ns=dt_range_ns,
                t_loc_default_ns=t_loc_default_ns,
            )

        if pulse_mask is None:
            msg = "need a valid pulse mask in order to drop table_ids with no pulses"
            raise ValueError(msg)

        if not isinstance(pulse_mask, ak.Array):
            pulse_mask = pulse_mask.view_as("ak")

        if pulse_mask.ndim != 3:
            msg = "pulse_mask must be 3D"
            raise ValueError(msg)

        # convert the 3D mask to a 2D mask (can be used to filter table_ids)
        ch_mask = ak.sum(pulse_mask, axis=-1) > 0

        # apply the mask
        data = data[ch_mask]

    return types.VectorOfVectors(data)


# NOTE: the mask never gets the empty arrays removed
def make_pulse_data_mask(
    datainfo: utils.DataInfo,
    tcm: utils.TCMData,
    table_names: Sequence[str],
    *,
    a_thr_pe=None,
    t_loc_ns=None,
    dt_range_ns=None,
    t_loc_default_ns=None,
) -> types.VectorOfVectors:
    """Calculate a 3D :class:`~lgdo.types.vectorofvectors.VectorOfVectors` pulse data mask.

    Useful to filter any pulse data based on pulse amplitude and start time.

    Parameters
    ----------
    datainfo, tcm, table_names
        positional arguments automatically supplied by :func:`.build_evt`.
    a_thr_pe
        amplitude threshold (in photoelectrons) used to build a pulse mask with
        :func:`make_pulse_data_mask`, if `pulse_mask` is ``None``. The output
        pulse data will be such that the pulse amplitude is above this value.
    t_loc_ns
        location of the time window in which pulses must sit. If a 1D array is
        provided, it is interpreted as a list of locations for each event (can
        be employed to e.g. provide the actual HPGe pulse position)
    dt_range_ns
        tuple with dimension of the time window in which pulses must sit
        relative to `t_loc_ns`. If, for example, `t_loc_ns` is 48000 ns and
        `dt_range_ns` is (-1000, 5000) ns, the resulting window will be (47000,
        53000) ns.
    t_loc_default_ns
        default value for `t_loc_ns`, in case the supplied value is
        :any:`numpy.nan`.
    """
    # get the t0 of each single pulse
    pulse_t0 = gather_pulse_data(
        datainfo,
        tcm,
        table_names,
        observable="hit.trigger_pos",
        drop_empty=False,
    )

    # HACK: handle units
    # HACK: remove me once units are fixed in the dsp tier
    if "units" in pulse_t0.attrs and pulse_t0.attrs["units"] == "ns":
        pulse_t0_ns = pulse_t0.view_as("ak")
    else:
        pulse_t0_ns = pulse_t0.view_as("ak") * 16

    pulse_amp = gather_pulse_data(
        datainfo,
        tcm,
        table_names,
        observable="hit.energy_in_pe",
        drop_empty=False,
    ).view_as("ak")

    # (HPGe) trigger position can vary among events!
    if isinstance(t_loc_ns, types.Array):
        t_loc_ns = t_loc_ns.view_as("ak")

    if isinstance(t_loc_ns, ak.Array):
        if t_loc_ns.ndim != 1:
            msg = "t_loc_ns must be 0- or 1-dimensional"
            raise ValueError(msg)

        # NOTE: the assumption is that t0 is np.nan when missing -> replace
        # with default value
        t_loc_ns = ak.fill_none(ak.nan_to_none(t_loc_ns), t_loc_default_ns)

    mask = pulse_t0_ns == pulse_t0_ns

    if a_thr_pe is not None:
        mask = mask & (pulse_amp > a_thr_pe)

    if t_loc_ns is not None and dt_range_ns is not None:
        if not isinstance(dt_range_ns, (tuple, list)):
            msg = "dt_range_ns must be a tuple"
            raise ValueError(msg)

        mask = mask & (
            (pulse_t0_ns < (t_loc_ns + dt_range_ns[1]))
            & (pulse_t0_ns > (t_loc_ns + dt_range_ns[0]))
        )

    return types.VectorOfVectors(mask)
