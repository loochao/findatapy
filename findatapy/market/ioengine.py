__author__ = 'saeedamen' # Saeed Amen

#
# Copyright 2016 Cuemacro
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
# License. You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#
# See the License for the specific language governing permissions and limitations under the License.
#

import pandas
import codecs
import datetime
from dateutil.parser import parse
import shutil

try:
    import bcolz
except: pass

from openpyxl import load_workbook
import os.path

from findatapy.util.dataconstants import DataConstants
from findatapy.util.loggermanager import LoggerManager

# NOTE: BCOLZ support is alpha!
_replace_chars = ['_a_',
                  '_d_',
                  '_h_',
                  '_o_',
                  '_c_',
                  '_s_',
                  '_p_',
                  '_e_',
                  '_'
                  ]

_invalid_chars = ['&',
                  '.',
                  '-',
                  '(',
                  ')',
                  '/',
                  '%',
                  '=',
                  ' ']

class IOEngine(object):
    """Write and reads time series data to disk in various formats, CSV and HDF5 format. (planning to add other interfaces too).
    Also supports BColz (but not currently stable).

    """

    def __init__(self):
        self.logger = LoggerManager().getLogger(__name__)

    ### functions to handle Excel on disk
    def write_time_series_to_excel(self, fname, sheet, data_frame, create_new=False):
        """Writes Pandas data frame to disk in Excel format

        Parameters
        ----------
        fname : str
            Excel filename to be written to
        sheet : str
            sheet in excel
        data_frame : DataFrame
            data frame to be written
        create_new : boolean
            to create a new Excel file
        """

        if(create_new):
            writer = pandas.ExcelWriter(fname, engine='xlsxwriter')
        else:
            if os.path.isfile(fname):
                book = load_workbook(fname)
                writer = pandas.ExcelWriter(fname, engine='xlsxwriter')
                writer.book = book
                writer.sheets = dict((ws.title, ws) for ws in book.worksheets)
            else:
                writer = pandas.ExcelWriter(fname, engine='xlsxwriter')

        data_frame.to_excel(writer, sheet_name=sheet, engine='xlsxwriter')

        writer.save()
        writer.close()

    def write_time_series_to_excel_writer(self, writer, sheet, data_frame):
        """Writes Pandas data frame to disk in Excel format for a writer

        Parameters
        ----------
        writer : ExcelWriter
            File handle to use for writing Excel file to disk
        sheet : str
            sheet in excel
        data_frame : DataFrame
            data frame to be written
        """
        data_frame.to_excel(writer, sheet, engine='xlsxwriter')

    def read_excel_data_frame(self, f_name, excel_sheet, freq, cutoff = None, dateparse = None,
                            postfix = '.close', intraday_tz = 'UTC'):
        """Reads Excel from disk into DataFrame

        Parameters
        ----------
        f_name : str
            Excel file path to read
        freq : str
            Frequency of data to read (intraday/daily etc)
        cutoff : DateTime (optional)
            end date to read up to
        dateparse : str (optional)
            date parser to use
        postfix : str (optional)
            postfix to add to each columns
        intraday_tz : str
            timezone of file if uses intraday data

        Returns
        -------
        DataFrame
        """

        return self.read_csv_data_frame(f_name, freq, cutoff = cutoff, dateparse = dateparse,
                            postfix = postfix, intraday_tz = intraday_tz, excel_sheet = excel_sheet)

    def remove_time_series_cache_on_disk(self, fname, engine = 'hdf5_fixed', db_server = '127.0.0.1'):

        if 'hdf5' in engine:
            engine = 'hdf5'

        if (engine == 'bcolz'):
            # convert invalid characters to substitutes (which Bcolz can't deal with)
            pass
        elif (engine == 'arctic'):
            from arctic import Arctic
            import pymongo

            socketTimeoutMS = 10 * 1000
            fname = os.path.basename(fname).replace('.', '_')

            self.logger.info('Load MongoDB library: ' + fname)

            c = pymongo.MongoClient(db_server, connect=False)
            store = Arctic(c, socketTimeoutMS=socketTimeoutMS, serverSelectionTimeoutMS=socketTimeoutMS)
            store.delete_library(fname)

            c.close()

            self.logger.info("Deleted MongoDB library: " + fname)

        elif (engine == 'hdf5'):
            h5_filename = self.get_h5_filename(fname)

            # delete the old copy
            try:
                os.remove(h5_filename)
            except:
                pass


    ### functions to handle HDF5 on disk
    def write_time_series_cache_to_disk(self, fname, data_frame,
                                        engine = 'hdf5_fixed', append_data = False, db_server = '127.0.0.1',
                                        filter_out_matching = None):
        """Writes Pandas data frame to disk as HDF5 format or bcolz format or in Arctic

        Parmeters
        ---------
        fname : str
            path of file
        data_frame : DataFrame
            data frame to be written to disk
        """

        # default HDF5 format
        hdf5_format = 'fixed'

        if 'hdf5' in engine:
            hdf5_format = engine.split('_')[1]
            engine = 'hdf5'

        if (engine == 'bcolz'):
            # convert invalid characters to substitutes (which Bcolz can't deal with)
            data_frame.columns = self.find_replace_chars(data_frame.columns, _invalid_chars, _replace_chars)
            data_frame.columns = ['A_' + x for x in data_frame.columns]

            data_frame['DTS_'] = pandas.to_datetime(data_frame.index, unit='ns')

            bcolzpath = self.get_bcolz_filename(fname)
            shutil.rmtree(bcolzpath, ignore_errors=True)
            zlens = bcolz.ctable.fromdataframe(data_frame, rootdir=bcolzpath)
        elif (engine == 'arctic'):
            from arctic import Arctic
            import pymongo

            socketTimeoutMS = 30 * 1000
            fname = os.path.basename(fname).replace('.', '_')

            self.logger.info('Load MongoDB library: ' + fname)

            c = pymongo.MongoClient(db_server, connect=False)
            store = Arctic(c, socketTimeoutMS=socketTimeoutMS, serverSelectionTimeoutMS=socketTimeoutMS)

            database = None

            try:
                database = store[fname]
            except:
                pass

            if database is None:
                store.initialize_library(fname, audit=False)
                self.logger.info("Created MongoDB library: " + fname)
            else:
                self.logger.info("Got MongoDB library: " + fname)

            # Access the library
            library = store[fname]

            if ('intraday' in fname):
                data_frame = data_frame.astype('float32')

            if filter_out_matching is not None:
                cols = data_frame.columns

                new_cols = []

                for col in cols:
                    if filter_out_matching not in col:
                        new_cols.append(col)

                data_frame = data_frame[new_cols]

            # can duplicate values if we have existing dates
            if append_data:
                library.append(fname, data_frame)
            else:
                library.write(fname, data_frame)

            c.close()

            self.logger.info("Written MongoDB library: " + fname)

        elif (engine == 'hdf5'):
            h5_filename = self.get_h5_filename(fname)

            # append data only works for HDF5 stored as tables (but this is much slower than fixed format)
            # removes duplicated entries at the end
            if append_data:
                store = pandas.HDFStore(h5_filename, format=hdf5_format, complib="blosc", complevel=9)

                if ('intraday' in fname):
                    data_frame = data_frame.astype('float32')

                # get last row which matches and remove everything after that (because append
                # function doesn't check for duplicated rows
                nrows = len(store['data'].index)
                last_point = data_frame.index[-1]

                i = nrows - 1

                while(i > 0):
                    read_index = store.select('data', start=i, stop=nrows).index[0]

                    if (read_index <= last_point): break

                    i = i - 1

                # remove rows at the end, which are duplicates of the incoming time series
                store.remove(key='data', start=i, stop=nrows)
                store.put(key='data', value=data_frame, format=hdf5_format, append=True)
                store.close()
            else:
                h5_filename_temp = self.get_h5_filename(fname + ".temp")

                # delete the old copy
                try:
                    os.remove(h5_filename_temp)
                except: pass

                store = pandas.HDFStore(h5_filename_temp, format=hdf5_format, complib="blosc", complevel=9)

                if ('intraday' in fname):
                    data_frame = data_frame.astype('float32')

                store.put(key='data', value=data_frame, format=hdf5_format)
                store.close()

                # delete the old copy
                try:
                    os.remove(h5_filename)
                except: pass

                # once written to disk rename
                os.rename(h5_filename_temp, h5_filename)

    def get_h5_filename(self, fname):
        """Strips h5 off filename returning first portion of filename

        Parameters
        ----------
        fname : str
            h5 filename to strip

        Returns
        -------
        str
        """
        if fname[-3:] == '.h5':
            return fname

        return fname + ".h5"

    def get_bcolz_filename(self, fname):
        """Strips bcolz off filename returning first portion of filename

        Parameters
        ----------
        fname : str
            bcolz filename to strip

        Returns
        -------
        str
        """
        if fname[-6:] == '.bcolz':
            return fname

        return fname + ".bcolz"

    def write_r_compatible_hdf_dataframe(self, data_frame, fname, fields = None):
        """Write a DataFrame to disk in as an R compatible HDF5 file

        Parameters
        ----------
        data_frame : DataFrame
            data frame to be written
        fname : str
            file path to be written
        fields : list(str)
            columns to be written
        """
        fname_r = self.get_h5_filename(fname)

        self.logger.info("About to dump R binary HDF5 - " + fname_r)
        data_frame32 = data_frame.astype('float32')

        if fields is None:
            fields = data_frame32.columns.values

        # decompose date/time into individual fields (easier to pick up in R)
        data_frame32['Year'] = data_frame.index.year
        data_frame32['Month'] = data_frame.index.month
        data_frame32['Day'] = data_frame.index.day
        data_frame32['Hour'] = data_frame.index.hour
        data_frame32['Minute'] = data_frame.index.minute
        data_frame32['Second'] = data_frame.index.second
        data_frame32['Millisecond'] = data_frame.index.microsecond / 1000

        data_frame32 = data_frame32[
            ['Year', 'Month', 'Day', 'Hour', 'Minute', 'Second', 'Millisecond'] + fields]

        cols = data_frame32.columns

        store_export = pandas.HDFStore(fname_r)
        store_export.put('df_for_r', data_frame32, data_columns=cols)
        store_export.close()

    def read_time_series_cache_from_disk(self, fname, engine = 'hdf5', start_date = None, finish_date = None, db_server = '127.0.0.1'):
        """Reads time series cache from disk in either HDF5 or bcolz

        Parameters
        ----------
        fname : str
            file to be read from

        Returns
        -------
        DataFrame
        """

        if (engine == 'bcolz'):
            try:
                name = self.get_bcolz_filename(fname)
                zlens = bcolz.open(rootdir=name)
                data_frame = zlens.todataframe()

                data_frame.index = pandas.DatetimeIndex(data_frame['DTS_'])
                data_frame.index.name = 'Date'
                del data_frame['DTS_']

                # convert invalid characters (which Bcolz can't deal with) to more readable characters for pandas
                data_frame.columns = self.find_replace_chars(data_frame.columns, _replace_chars, _invalid_chars)
                data_frame.columns = [x[2:] for x in data_frame.columns]

                return data_frame
            except:
                return None
        elif(engine == 'arctic'):
            socketTimeoutMS = 2 * 1000

            import pymongo
            from arctic import Arctic

            fname = os.path.basename(fname).replace('.', '_')

            self.logger.info('Load MongoDB library: ' + fname)

            c = pymongo.MongoClient(db_server, connect=False)

            store = Arctic(c, socketTimeoutMS=socketTimeoutMS, serverSelectionTimeoutMS=socketTimeoutMS)

            # Access the library
            library = store[fname]

            if start_date is None and finish_date is None:
                item = library.read(fname)
            else:
                from arctic.date import DateRange
                item = library.read(fname, date_range=DateRange(start_date, finish_date))

            c.close()

            self.logger.info('Read ' + fname)

            return item.data
        elif os.path.isfile(self.get_h5_filename(fname)):
            store = pandas.HDFStore(self.get_h5_filename(fname))
            data_frame = store.select("data")

            if ('intraday' in fname):
                data_frame = data_frame.astype('float32')

            store.close()

            return data_frame

        return None

    ### functions for CSV reading and writing
    def write_time_series_to_csv(self, csv_path, data_frame):
        data_frame.to_csv(csv_path)

    def read_csv_data_frame(self, f_name, freq, cutoff = None, dateparse = None,
                            postfix = '.close', intraday_tz = 'UTC', excel_sheet = None):
        """Reads CSV/Excel from disk into DataFrame

        Parameters
        ----------
        f_name : str
            CSV/Excel file path to read
        freq : str
            Frequency of data to read (intraday/daily etc)
        cutoff : DateTime (optional)
            end date to read up to
        dateparse : str (optional)
            date parser to use
        postfix : str (optional)
            postfix to add to each columns
        intraday_tz : str (optional)
            timezone of file if uses intraday data
        excel_sheet : str (optional)
            Excel sheet to be read

        Returns
        -------
        DataFrame
        """

        if(freq == 'intraday'):

            if dateparse is None:
                dateparse = lambda x: datetime.datetime(*map(int, [x[6:10], x[3:5], x[0:2],
                                                   x[11:13], x[14:16], x[17:19]]))
            elif dateparse is 'dukascopy':
                dateparse = lambda x: datetime.datetime(*map(int, [x[0:4], x[5:7], x[8:10],
                                                   x[11:13], x[14:16], x[17:19]]))
            elif dateparse is 'c':
                # use C library for parsing dates, several hundred times quicker
                # requires compilation of library to install
                import ciso8601
                dateparse = lambda x: ciso8601.parse_datetime(x)

            if excel_sheet is None:
                data_frame = pandas.read_csv(f_name, index_col = 0, parse_dates = True, date_parser = dateparse)
            else:
                data_frame = pandas.read_excel(f_name, excel_sheet, index_col = 0, na_values=['NA'])

            data_frame = data_frame.astype('float32')
            data_frame.index.names = ['Date']

            old_cols = data_frame.columns
            new_cols = []

            # add '.close' to each column name
            for col in old_cols:
                new_cols.append(col + postfix)

            data_frame.columns = new_cols
        else:
            # daily data
            if 'events' in f_name:

                data_frame = pandas.read_csv(f_name)

                # very slow conversion
                data_frame = data_frame.convert_objects(convert_dates = 'coerce')

            else:
                if excel_sheet is None:
                    try:
                        data_frame = pandas.read_csv(f_name, index_col=0, parse_dates =["DATE"], date_parser = dateparse)
                    except:
                        data_frame = pandas.read_csv(f_name, index_col=0, parse_dates =["Date"], date_parser = dateparse)
                else:
                    data_frame = pandas.read_excel(f_name, excel_sheet, index_col = 0, na_values=['NA'])

        # convert Date to Python datetime
        # datetime data_frame['Date1'] = data_frame.index

        # slower method: lambda x: pandas.datetime.strptime(x, '%d/%m/%Y %H:%M:%S')
        # data_frame['Date1'].apply(lambda x: datetime.datetime(int(x[6:10]), int(x[3:5]), int(x[0:2]),
        #                                        int(x[12:13]), int(x[15:16]), int(x[18:19])))

        # data_frame.index = data_frame['Date1']
        # data_frame.drop('Date1')

        # slower method: data_frame.index = pandas.to_datetime(data_frame.index)

        if(freq == 'intraday'):
            # assume time series are already in UTC and assign this (can specify other time zones)
            data_frame = data_frame.tz_localize(intraday_tz)

        # end cutoff date
        if cutoff is not None:
            if (isinstance(cutoff, str)):
                cutoff = parse(cutoff)

            data_frame = data_frame.loc[data_frame.index < cutoff]

        return data_frame

    def find_replace_chars(self, array, to_find, replace_with):

        for i in range(0, len(to_find)):
            array = [x.replace(to_find[i], replace_with[i]) for x in array]

        return array

    def convert_csv_data_frame(self, f_name, category, freq, cutoff=None, dateparse=None):
        """Converts CSV file to HDF5 file

        Parameters
        ----------
        f_name : str
            File name to be read
        category : str
            data category of file (used in HDF5 filename)
        freq : str
            intraday/daily frequency (used in HDF5 filename)
        cutoff : DateTime (optional)
            filter dates up to here
        dateparse : str
            date parser to use
        """

        self.logger.info("About to read... " + f_name)

        data_frame = self.read_csv_data_frame(f_name, freq, cutoff=cutoff, dateparse=dateparse)

        category_f_name = self.create_cache_file_name(category)

        self.write_time_series_cache_to_disk(
            category_f_name, data_frame)

    def clean_csv_file(self, f_name):
        """Cleans up CSV file (removing empty characters) before writing back to disk

        Parameters
        ----------
        f_name : str
            CSV file to be cleaned
        """

        with codecs.open (f_name, 'rb', 'utf-8') as myfile:
            data = myfile.read()

            # clean file first if dirty
            if data.count( '\x00' ):
                self.logger.info('Cleaning CSV...')

                with codecs.open(f_name + '.tmp', 'w', 'utf-8') as of:
                    of.write(data.replace('\x00', ''))

                shutil.move(f_name + '.tmp', f_name)

    def create_cache_file_name(self, filename):
        return DataConstants().folder_time_series_data + "/" + filename
