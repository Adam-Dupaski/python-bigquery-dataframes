# contains code from https://github.com/geopandas/geopandas/blob/main/geopandas/geoseries.py
from __future__ import annotations

from typing import TYPE_CHECKING

from bigframes import constants

if TYPE_CHECKING:
    import bigframes.series


class GeoSeries:
    """
    A Series object designed to store geometry objects.
    """

    @property
    def x(self) -> bigframes.series.Series:
        """Return the x location of point geometries in a GeoSeries

        **Examples:**

            >>> import bigframes.pandas as bpd
            >>> bpd.options.display.progress_bar = None
            >>> import geopandas.array
            >>> import shapely

            >>> series = bpd.Series(
            ...     [shapely.Point(1, 1), shapely.Point(2, 2), shapely.Point(3, 3)],
            ...     dtype=geopandas.array.GeometryDtype()
            ... )
            >>> series.geo.x
            0    1.0
            1    2.0
            2    3.0
            dtype: float64

        Returns:
            bigframes.series.Series:
                Return the x location (longitude) of point geometries.
        """
        raise NotImplementedError(constants.ABSTRACT_METHOD_ERROR_MESSAGE)

    @property
    def y(self) -> bigframes.series.Series:
        """Return the y location of point geometries in a GeoSeries

        **Examples:**

            >>> import bigframes.pandas as bpd
            >>> bpd.options.display.progress_bar = None
            >>> import geopandas.array
            >>> import shapely

            >>> series = bpd.Series(
            ...     [shapely.Point(1, 1), shapely.Point(2, 2), shapely.Point(3, 3)],
            ...     dtype=geopandas.array.GeometryDtype()
            ... )
            >>> series.geo.y
            0    1.0
            1    2.0
            2    3.0
            dtype: float64

        Returns:
            bigframes.series.Series:
                Return the y location (latitude) of point geometries.
        """
        raise NotImplementedError(constants.ABSTRACT_METHOD_ERROR_MESSAGE)
