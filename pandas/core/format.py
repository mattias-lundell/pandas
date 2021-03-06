from itertools import izip

from StringIO import StringIO
from pandas.core.common import adjoin, _format
from pandas.core.index import MultiIndex, _ensure_index
from pandas.util import py3compat

import pandas.core.common as com
import numpy as np

docstring_to_string = """
    Parameters
    ----------
    frame : DataFrame
        object to render
    buf : StringIO-like, optional
        buffer to write to
    columns : sequence, optional
        the subset of columns to write; default None writes all columns
    col_space : int, optional
        the width of each columns
    header : bool, optional
        whether to print column labels, default True
    index : bool, optional
        whether to print index (row) labels, default True
    na_rep : string, optional
        string representation of NAN to use, default 'NaN'
    formatters : list or dict of one-parameter functions, optional
        formatter functions to apply to columns' elements by position or name,
        default None
    float_format : one-parameter function, optional
        formatter function to apply to columns' elements if they are floats
        default None
    sparsify : bool, optional
        Set to False for a DataFrame with a hierarchical index to print every
        multiindex key at each row, default True
    justify : {'left', 'right'}, default None
        Left or right-justify the column labels. If None uses the option from
        the configuration in pandas.core.common, 'left' out of the box
    index_names : bool, optional
        Prints the names of the indexes, default True
    force_unicode : bool, default False
        Always return a unicode result

    Returns
    -------
    formatted : string (or unicode, depending on data and options)"""

class SeriesFormatter(object):

    def __init__(self, series, buf=None, header=True, length=True,
                 na_rep='NaN', name=False, float_format=None):
        self.series = series
        self.buf = buf if buf is not None else StringIO()
        self.name = name
        self.na_rep = na_rep
        self.float_format = float_format
        self.length = length
        self.header = header

        def formatter(x, col_width=None):
            return _format(x, self.series.dtype,
                           na_rep=self.na_rep,
                           float_format=self.float_format,
                           col_width=col_width)
        self.formatter = formatter

    def _get_footer(self):
        footer = ''
        if self.name:
            footer += ("Name: %s" % str(self.series.name)
                       if self.series.name else '')

        if self.length:
            if footer:
                footer += ', '
            footer += 'Length: %d' % len(self.series)
        return footer

    def _get_formatted_index(self):
        index = self.series.index
        is_multi = isinstance(index, MultiIndex)
        if is_multi:
            have_header = any(name for name in index.names)
            fmt_index = index.format(names=True)
        else:
            have_header = index.name is not None
            fmt_index = index.format(name=True)
        return fmt_index, have_header

    def _get_formatted_values(self):
        series = self.series
        vals = series.values

        if self.float_format is None:
            float_format = com.print_config.float_format
            if float_format is None:
                float_format = com._float_format_default

        # floating point handling
        if series.dtype == 'O':
            is_float = (series.map(com.is_float) & series.notnull()).values
            leading_space = is_float.any()

            fmt_values = []
            for i, v in enumerate(vals):
                if not is_float[i] and leading_space:
                    fmt_values.append(' %s' % self.formatter(v))
                elif is_float[i]:
                    fmt_values.append(float_format(v))
                else:
                    fmt_values.append(' %s' % self.formatter(v))
        else:
            fmt_values = _format_fixed_width(self.series.values,
                                             self.formatter)
        return fmt_values

    def to_string(self):
        series = self.series

        if len(series) == 0:
            return ''

        fmt_index, have_header = self._get_formatted_index()
        fmt_values = self._get_formatted_values()

        maxlen = max(len(x) for x in fmt_index)
        pad_space = min(maxlen, 60)
        result = ['%s   %s' % (k.ljust(pad_space), v)
                  for (k, v) in izip(fmt_index[1:], fmt_values)]

        if self.header and have_header:
            result.insert(0, fmt_index[0])

        footer = self._get_footer()
        if footer:
            result.append(footer)

        return '\n'.join(result)


class DataFrameFormatter(object):
    """
    Render a DataFrame

    self.to_string() : console-friendly tabular output
    self.to_html()   : html table

    """

    __doc__ += docstring_to_string

    def __init__(self, frame, buf=None, columns=None, col_space=None,
                 header=True, index=True, na_rep='NaN', formatters=None,
                 justify=None, float_format=None, sparsify=True,
                 index_names=True, **kwds):
        self.frame = frame
        self.buf = buf if buf is not None else StringIO()
        self.show_index_names = index_names
        self.sparsify = sparsify
        self.float_format = float_format
        self.formatters = formatters
        self.na_rep = na_rep
        self.col_space = col_space
        self.header = header
        self.index = index

        if justify is None:
            self.justify = com.print_config.colheader_justify
        else:
            self.justify = justify

        self.kwds = kwds

        if columns is not None:
            self.columns = _ensure_index(columns)
        else:
            self.columns = frame.columns

    def to_string(self, force_unicode=False):
        """
        Render a DataFrame to a console-friendly tabular output.
        """
        frame = self.frame

        to_write = []

        if len(frame.columns) == 0 or len(frame.index) == 0:
            info_line = (u'Empty %s\nColumns: %s\nIndex: %s'
                         % (type(self.frame).__name__,
                            frame.columns, frame.index))
            to_write.append(info_line)
        else:
            # may include levels names also
            str_index = self._get_formatted_index()
            str_columns = self._get_formatted_column_labels()

            stringified = []

            for i, c in enumerate(self.columns):
                if self.header:
                    fmt_values = self._format_col(c)
                    cheader = str_columns[i]
                    max_len = max(max(len(x) for x in fmt_values),
                                  max(len(x) for x in cheader))
                    if self.justify == 'left':
                        cheader = [x.ljust(max_len) for x in cheader]
                    else:
                        cheader = [x.rjust(max_len) for x in cheader]
                    stringified.append(cheader + fmt_values)
                else:
                    stringified = [self._format_col(c) for c in self.columns]

            if self.index:
                to_write.append(adjoin(1, str_index, *stringified))
            else:
                to_write.append(adjoin(1, *stringified))

        if not py3compat.PY3:
            if force_unicode:
                to_write = [unicode(s) for s in to_write]
            else:
                # generally everything is plain strings, which has ascii
                # encoding.  problem is when there is a char with value over 127
                # - everything then gets converted to unicode.
                try:
                    for s in to_write:
                        str(s)
                except UnicodeError:
                    to_write = [unicode(s) for s in to_write]

        self.buf.writelines(to_write)

    def _get_col_formatter(self, dtype):
        def formatter(x, col_width=None):
            return _format(x, dtype, space=self.col_space,
                           na_rep=self.na_rep,
                           float_format=self.float_format,
                           col_width=col_width)
        return formatter

    def _format_col(self, col, i=None):
        if self.formatters is None:
            self.formatters = {}

        if col in self.formatters:
            formatter = self.formatters[col]

            if i is None:
                return [formatter(x) for x in self.frame[col]]
            else:
                return formatter(self.frame[col][i])
        else:
            dtype = self.frame[col].dtype
            formatter = self._get_col_formatter(dtype)

            if i is not None:
                return formatter(self.frame[col][i])
            else:
                return _format_fixed_width(self.frame[col],
                                           formatter)

    def to_html(self):
        """
        Render a DataFrame to a html table.
        """
        def write(buf, s, indent=0):
            buf.write(unicode((' ' * indent) + str(s) + '\n'))

        def write_th(buf, s, indent=0):
            write(buf, '<th>%s</th>' % str(s), indent)

        def write_td(buf, s, indent=0):
            write(buf, '<td>%s</td>' % str(s), indent)

        def write_tr(buf, l, indent=0, indent_delta=4, header=False):
            write(buf, '<tr>', indent)
            indent += indent_delta
            if header:
                for s in l:
                    write_th(buf, s, indent)
            else:
                for s in l:
                    write_td(buf, s, indent)
            indent -= indent_delta
            write(buf, '</tr>', indent)

        indent = 0
        indent_delta = 2
        frame = self.frame
        buf = self.buf

        write(buf, '<table border="1">', indent)

        def _column_header():
            row = [''] * (frame.index.nlevels - 1)

            if isinstance(frame.columns, MultiIndex):
                if self.has_column_names:
                    row.append(single_column_table(frame.columns.names))
                row.extend([single_column_table(c) for c in frame.columns])
            else:
                row.append(frame.columns.name or '')
                row.extend(frame.columns)
            return row

        if len(frame.columns) == 0 or len(frame.index) == 0:
            write(buf, '<tbody>', indent  + indent_delta)
            write_tr(buf,
                     [repr(frame.index),
                      'Empty %s' % type(self.frame).__name__],
                     indent + (2 * indent_delta),
                     indent_delta)
            write(buf, '</tbody>', indent  + indent_delta)
        else:
            indent += indent_delta

            # header row
            if self.header:
                write(buf, '<thead>', indent)
                row = []

                col_row = _column_header()
                indent += indent_delta
                write_tr(buf, col_row, indent, indent_delta, header=True)
                if self.has_index_names:
                    row = frame.index.names + [''] * len(frame.columns)
                    write_tr(buf, row, indent, indent_delta, header=True)

                write(buf, '</thead>', indent)

            write(buf, '<tbody>', indent)

            _bold_row = self.kwds.get('bold_rows', False)
            def _maybe_bold_row(x):
                temp = '<strong>%s</strong>'
                if _bold_row:
                    return ([temp % y for y in x] if isinstance(x, tuple)
                            else temp % x)
                else:
                    return x

            # write values
            for i in range(len(frame)):
                row = []
                if isinstance(frame.index, MultiIndex):
                    row.extend(_maybe_bold_row(frame.index[i]))
                else:
                    row.append(_maybe_bold_row(frame.index[i]))
                for column in frame.columns:
                    row.append(self._format_col(column, i))
                write_tr(buf, row, indent, indent_delta)
            indent -= indent_delta
            write(buf, '</tbody>', indent)
            indent -= indent_delta

        write(buf, '</table>', indent)

    def _get_formatted_column_labels(self):
        from pandas.core.index import _sparsify

        formatters = self.formatters
        if formatters is None:
            formatters = {}

        def is_numeric_dtype(dtype):
            return issubclass(dtype.type, np.number)

        if isinstance(self.columns, MultiIndex):
            fmt_columns = self.columns.format(sparsify=False, adjoin=False)
            fmt_columns = zip(*fmt_columns)
            dtypes = self.frame.dtypes.values
            need_leadsp = dict(zip(fmt_columns, map(is_numeric_dtype, dtypes)))
            str_columns = zip(*[[u' %s' % y
                                if y not in formatters and need_leadsp[x]
                                else y for y in x]
                               for x in fmt_columns])
            if self.sparsify:
                str_columns = _sparsify(str_columns)

            str_columns = [list(x) for x in zip(*str_columns)]
        else:
            fmt_columns = self.columns.format()
            dtypes = self.frame.dtypes
            need_leadsp = dict(zip(fmt_columns, map(is_numeric_dtype, dtypes)))
            str_columns = [[u' %s' % x
                            if col not in formatters and need_leadsp[x]
                            else x]
                           for col, x in zip(self.columns, fmt_columns)]

        if self.show_index_names and self.has_index_names:
            for x in str_columns:
                x.append('')

        return str_columns

    @property
    def has_index_names(self):
        return _has_names(self.frame.index)

    @property
    def has_column_names(self):
        return _has_names(self.frame.columns)

    def _get_formatted_index(self):
        index = self.frame.index
        columns = self.frame.columns

        show_index_names = self.show_index_names and self.has_index_names
        show_col_names = (self.show_index_names and self.has_column_names)

        if isinstance(index, MultiIndex):
            fmt_index = index.format(sparsify=self.sparsify, adjoin=False,
                                     names=show_index_names)
        else:
            fmt_index = [index.format(name=show_index_names)]

        adjoined = adjoin(1, *fmt_index).split('\n')

        # empty space for columns
        if show_col_names:
            col_header = ['%s' % x for x in self._get_column_name_list()]
        else:
            col_header = [''] * columns.nlevels

        if self.header:
            return col_header + adjoined
        else:
            return adjoined

    def _get_column_name_list(self):
        names = []
        columns = self.frame.columns
        if isinstance(columns, MultiIndex):
            names.extend('' if name is None else name
                         for name in columns.names)
        else:
            names.append('' if columns.name is None else columns.name)
        return names

def _format_fixed_width(values, formatter):
    formatted = [formatter(x) for x in values]
    max_len = max(len(x) for x in formatted)
    return [formatter(x, col_width=max_len) for x in values]

def single_column_table(column):
    table = '<table><tbody>'
    for i in column:
        table += ('<tr><td>%s</td></tr>' % str(i))
    table += '</tbody></table>'
    return table

def single_row_table(row):  # pragma: no cover
    table = '<table><tbody><tr>'
    for i in row:
        table += ('<td>%s</td>' % str(i))
    table += '</tr></tbody></table>'
    return table

def _has_names(index):
    if isinstance(index, MultiIndex):
        return any([x is not None for x in index.names])
    else:
        return index.name is not None
