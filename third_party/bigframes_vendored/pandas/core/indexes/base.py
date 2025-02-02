# Contains code from https://github.com/pandas-dev/pandas/blob/main/pandas/core/indexes/base.py
from __future__ import annotations

import typing

from bigframes import constants


class Index:
    """Immutable sequence used for indexing and alignment.

    The basic object storing axis labels for all objects.

    Args:
        data (pandas.Series | pandas.Index | bigframes.series.Series | bigframes.core.indexes.base.Index):
            Labels (1-dimensional).
        dtype:
            Data type for the output Index. If not specified, this will be
            inferred from `data`.
        name:
            Name to be stored in the index.
        session (Optional[bigframes.session.Session]):
            BigQuery DataFrames session where queries are run. If not set,
            a default session is used.
    """

    @property
    def name(self):
        """Returns Index name."""
        raise NotImplementedError(constants.ABSTRACT_METHOD_ERROR_MESSAGE)

    @property
    def values(self):
        """Return an array representing the data in the Index."""
        raise NotImplementedError(constants.ABSTRACT_METHOD_ERROR_MESSAGE)

    @property
    def shape(self):
        """
        Return a tuple of the shape of the underlying data.
        """
        raise NotImplementedError(constants.ABSTRACT_METHOD_ERROR_MESSAGE)

    @property
    def nlevels(self) -> int:
        """Number of levels."""
        raise NotImplementedError(constants.ABSTRACT_METHOD_ERROR_MESSAGE)

    @property
    def is_unique(self) -> bool:
        """Return if the index has unique values."""
        raise NotImplementedError(constants.ABSTRACT_METHOD_ERROR_MESSAGE)

    @property
    def has_duplicates(self) -> bool:
        """Check if the Index has duplicate values."""
        raise NotImplementedError(constants.ABSTRACT_METHOD_ERROR_MESSAGE)

    @property
    def dtype(self):
        """Return the dtype object of the underlying data."""

        raise NotImplementedError(constants.ABSTRACT_METHOD_ERROR_MESSAGE)

    @property
    def dtypes(self):
        """Return the dtypes as a Series for the underlying MultiIndex."""
        raise NotImplementedError(constants.ABSTRACT_METHOD_ERROR_MESSAGE)

    @property
    def T(self) -> Index:
        """Return the transpose, which is by definition self."""
        raise NotImplementedError(constants.ABSTRACT_METHOD_ERROR_MESSAGE)

    def copy(
        self,
        name=None,
    ) -> Index:
        """
        Make a copy of this object.

        Name is set on the new object.

        Args:
            name (Label, optional):
                Set name for new object.
        Returns:
            Index: Index reference to new object, which is a copy of this object.
        """
        raise NotImplementedError(constants.ABSTRACT_METHOD_ERROR_MESSAGE)

    def transpose(self) -> Index:
        """
        Return the transpose, which is by definition self.

        Returns:
            Index
        """
        raise NotImplementedError(constants.ABSTRACT_METHOD_ERROR_MESSAGE)

    def astype(self, dtype):
        """Create an Index with values cast to dtypes.

        The class of a new Index is determined by dtype. When conversion is
        impossible, a TypeError exception is raised.

        Args:
            dtype (str or pandas.ExtensionDtype):
                A dtype supported by BigQuery DataFrame include ``'boolean'``,
                ``'Float64'``, ``'Int64'``, ``'int64\\[pyarrow\\]'``,
                ``'string'``, ``'string\\[pyarrow\\]'``,
                ``'timestamp\\[us, tz=UTC\\]\\[pyarrow\\]'``,
                ``'timestamp\\[us\\]\\[pyarrow\\]'``,
                ``'date32\\[day\\]\\[pyarrow\\]'``,
                ``'time64\\[us\\]\\[pyarrow\\]'``.
                A pandas.ExtensionDtype include ``pandas.BooleanDtype()``,
                ``pandas.Float64Dtype()``, ``pandas.Int64Dtype()``,
                ``pandas.StringDtype(storage="pyarrow")``,
                ``pd.ArrowDtype(pa.date32())``,
                ``pd.ArrowDtype(pa.time64("us"))``,
                ``pd.ArrowDtype(pa.timestamp("us"))``,
                ``pd.ArrowDtype(pa.timestamp("us", tz="UTC"))``.
            errors ({'raise', 'null'}, default 'raise'):
                Control raising of exceptions on invalid data for provided dtype.
                If 'raise', allow exceptions to be raised if any value fails cast
                If 'null', will assign null value if value fails cast

        Returns:
            Index: Index with values cast to specified dtype.
        """
        raise NotImplementedError(constants.ABSTRACT_METHOD_ERROR_MESSAGE)

    def get_level_values(self, level) -> Index:
        """
        Return an Index of values for requested level.

        This is primarily useful to get an individual level of values from a
        MultiIndex, but is provided on Index as well for compatibility.

        Args:
            level (int or str):
                It is either the integer position or the name of the level.

        Returns:
            Index: Calling object, as there is only one level in the Index.
        """
        raise NotImplementedError(constants.ABSTRACT_METHOD_ERROR_MESSAGE)

    def to_series(self):
        """
        Create a Series with both index and values equal to the index keys.

        Useful with map for returning an indexer based on an index.

        Args:
            index (Index, optional):
                Index of resulting Series. If None, defaults to original index.
            name (str, optional):
                Name of resulting Series. If None, defaults to name of original
                index.

        Returns:
            Series: The dtype will be based on the type of the Index values.
        """
        raise NotImplementedError(constants.ABSTRACT_METHOD_ERROR_MESSAGE)

    def isin(self, values):
        """
        Return a boolean array where the index values are in `values`.

        Compute boolean array to check whether each index value is found in the
        passed set of values. The length of the returned boolean array matches
        the length of the index.

        Args:
            values (set or list-like):
                Sought values.

        Returns:
            Series: Series of boolean values.
        """
        raise NotImplementedError(constants.ABSTRACT_METHOD_ERROR_MESSAGE)

    def all(self) -> bool:
        """Return whether all elements are Truthy.

        Returns:
            bool: A single element array-like may be converted to bool.
        """
        raise NotImplementedError(constants.ABSTRACT_METHOD_ERROR_MESSAGE)

    def any(self) -> bool:
        """Return whether any element is Truthy.

        Returns:
            bool: A single element array-like may be converted to bool.
        """
        raise NotImplementedError(constants.ABSTRACT_METHOD_ERROR_MESSAGE)

    def min(self):
        """Return the minimum value of the Index.

        Returns:
            scalar: Minimum value.
        """
        raise NotImplementedError(constants.ABSTRACT_METHOD_ERROR_MESSAGE)

    def max(self):
        """Return the maximum value of the Index.

        Returns:
            scalar: Maximum value.
        """
        raise NotImplementedError(constants.ABSTRACT_METHOD_ERROR_MESSAGE)

    def argmin(self) -> int:
        """
        Return int position of the smallest value in the series.

        If the minimum is achieved in multiple locations,
        the first row position is returned.

        Returns:
            int: Row position of the minimum value.
        """
        raise NotImplementedError(constants.ABSTRACT_METHOD_ERROR_MESSAGE)

    def argmax(self) -> int:
        """
        Return int position of the largest value in the Series.

        If the maximum is achieved in multiple locations,
        the first row position is returned.

        Returns:
            int: Row position of the maximum value.
        """
        raise NotImplementedError(constants.ABSTRACT_METHOD_ERROR_MESSAGE)

    def nunique(self) -> int:
        """Return number of unique elements in the object.

        Excludes NA values by default.

        Returns:
            int
        """
        raise NotImplementedError(constants.ABSTRACT_METHOD_ERROR_MESSAGE)

    def sort_values(
        self, *, ascending: bool = True, na_position: str = "last"
    ) -> Index:
        """
        Return a sorted copy of the index.

        Return a sorted copy of the index, and optionally return the indices
        that sorted the index itself.

        Args:
            ascending (bool, default True):
                Should the index values be sorted in an ascending order.
            na_position ({'first' or 'last'}, default 'last'):
                Argument 'first' puts NaNs at the beginning, 'last' puts NaNs at
                the end.

        Returns:
            pandas.Index: Sorted copy of the index.
        """
        raise NotImplementedError(constants.ABSTRACT_METHOD_ERROR_MESSAGE)

    def value_counts(
        self,
        normalize: bool = True,
        sort: bool = True,
        ascending: bool = False,
        *,
        dropna: bool = True,
    ):
        """Return a Series containing counts of unique values.

        The resulting object will be in descending order so that the
        first element is the most frequently-occurring element.
        Excludes NA values by default.

        Args:
            normalize (bool, default False):
                If True, then the object returned will contain the relative
                frequencies of the unique values.
            sort (bool, default True):
                Sort by frequencies.
            ascending (bool, default False):
                Sort in ascending order.
            dropna (bool, default True):
                Don't include counts of NaN.

        Returns:
            Series
        """
        raise NotImplementedError(constants.ABSTRACT_METHOD_ERROR_MESSAGE)

    def fillna(self, value) -> Index:
        """
        Fill NA/NaN values with the specified value.

        Args:
            value (scalar):
                Scalar value to use to fill holes (e.g. 0).
                This value cannot be a list-likes.

        Returns:
            Index
        """
        raise NotImplementedError(constants.ABSTRACT_METHOD_ERROR_MESSAGE)

    def rename(self, name) -> Index:
        """
        Alter Index or MultiIndex name.

        Able to set new names without level. Defaults to returning new index.
        Length of names must match number of levels in MultiIndex.

        Args:
            name (label or list of labels):
                Name(s) to set.

        Returns:
            Index: The same type as the caller.
        """
        raise NotImplementedError(constants.ABSTRACT_METHOD_ERROR_MESSAGE)

    def drop(self, labels) -> Index:
        """
        Make new Index with passed list of labels deleted.

        Args:
            labels (array-like or scalar):

        Returns:
            Index: Will be same type as self.
        """
        raise NotImplementedError(constants.ABSTRACT_METHOD_ERROR_MESSAGE)

    def dropna(self, how: typing.Literal["all", "any"] = "any"):
        """Return Index without NA/NaN values.

        Args:
            how ({'any', 'all'}, default 'any'):
                If the Index is a MultiIndex, drop the value when any or all levels
                are NaN.

        Returns:
            Index
        """
        raise NotImplementedError(constants.ABSTRACT_METHOD_ERROR_MESSAGE)

    def drop_duplicates(self, *, keep: str = "first"):
        """
        Return Index with duplicate values removed.

        Args:
            keep ({'first', 'last', ``False``}, default 'first'):
                One of:
                'first' : Drop duplicates except for the first occurrence.
                'last' : Drop duplicates except for the last occurrence.
                ``False`` : Drop all duplicates.

        Returns:
            Index
        """
        raise NotImplementedError(constants.ABSTRACT_METHOD_ERROR_MESSAGE)

    def to_numpy(self, dtype):
        """
        A NumPy ndarray representing the values in this Series or Index.

        Args:
            dtype:
                The dtype to pass to :meth:`numpy.asarray`.
            **kwargs:
                Additional keywords passed through to the ``to_numpy`` method
                of the underlying array (for extension arrays).

        Returns:
            numpy.ndarray
        """
        raise NotImplementedError(constants.ABSTRACT_METHOD_ERROR_MESSAGE)
