from findatapy.timeseries import Calculations
from findatapy.util import LoggerManager
from findatapy.market import MarketDataRequest
import pandas

#######################################################################################################################

class FXCLSVolume(object):
    def __init__(self, market_data_generator=None):
        self.logger = LoggerManager().getLogger(__name__)

        self.cache = {}

        self.calculations = Calculations()
        self.market_data_generator = market_data_generator

        return

        # all the tenors on our forwards
        # forwards_tenor = ["ON", "1W", "2W", "3W", "1M", "2M", "3M", "6M", "9M", "1Y", "2Y", "3Y", "5Y"]

    def get_fx_volume(self, start, end, currency_pairs, cut="LOC", source="quandl",
                       cache_algo="internet_load_return"):
        """ get_forward_points = get forward points for specified cross, tenor and part of surface

        :param start: start date
        :param end: end date
        :param cross: asset to be calculated
        :param tenor: tenor to calculate
        :param cut: closing time of data
        :param source: source of data eg. bloomberg

        :return: forward points
        """

        market_data_generator = self.market_data_generator

        if isinstance(currency_pairs, str): currency_pairs = [currency_pairs]

        tickers = []

        market_data_request = MarketDataRequest(
            start_date=start, finish_date=end,
            data_source=source,
            category='fx-spot-volume',
            freq='daily',
            cut=cut,
            tickers=currency_pairs,
            fields = ['0h','1h','2h','3h','4h','5h','6h','7h','8h','9h','10h','11h','12h','13h','14h','15h','16h','17h','18h','19h','20h',
                      '21h','22h','23h'],
            cache_algo=cache_algo,
            environment='backtest'
        )

        data_frame = market_data_generator.fetch_market_data(market_data_request)
        data_frame.index.name = 'Date'
        data_frame.index = pandas.DatetimeIndex(data_frame.index)

        df_list = []

        for t in currency_pairs:

            df = None
            for i in range(0, 24):
                txt = str(i)

                df1 = pandas.DataFrame(data_frame[t + "." + txt + 'h'].copy())

                df1.columns = [t + '.volume']
                df1.index = df1.index + pandas.DateOffset(hours=i)

                if df is None:
                    df = df1
                else:
                    df = df.append(df1)

            df = df.sort_index()
            df_list.append(df)

        data_frame_new = Calculations().pandas_outer_join(df_list)
        import pytz

        data_frame_new = data_frame_new.tz_localize(pytz.utc)
        return data_frame_new