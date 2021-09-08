import time
from binance import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException, BinanceRequestException
import config
import datetime
import pandas as pd
import math
import btalib
import smtplib


def send_text(message: str):
    smtp_server = "smtp.gmail.com:587"

    recipient = config.phone_number + "@tmomail.net"
    email_body = "From:\r\nTo:\r\nSubject: Crypto Bot Alert\r\n"+message
    server = smtplib.SMTP(smtp_server)
    server.starttls()
    server.login(config.email_address, config.email_password)
    server.sendmail(config.email_address, recipient, email_body)
    server.quit()


def round_down(number: float, decimals: int = 6):
    factor = 10 ** decimals
    return math.floor(number * factor) / factor


class indicatorsBot():
    technicals = pd.DataFrame()

    def __init__(self, client):
        col_names = ['date', 'close', 'MA', 'RSI']
        self.technicals = pd.DataFrame(columns=col_names)
        self.client = client
        self.available_cash = round_down(float(client.get_asset_balance('USD')["free"]), 6)
        self.available_coin = 0.0
        self.buy_order_sent = False   # if we sent an order
        self.latest_order_id = -1
        self.bought_in = False        # if buy order has filled
        self.bought_price = -1.0
        # technicals
        self.MA_timeframe = 24        # Moving Average timeframe
        self.RSI_timeframe = 14       # RSI timeframe
        self.rsi_lower_limit = 39.5   # rsi buy signal
        self.rsi_upper_limit = 70.0   # rsi sell signal (not used)
        self.ma_lower_limit = 0.0075  # MA buy signal (below curr MA by %)
        self.stop_loss = 0.05         # not used
        self.take_profit = 0.01

    def buy(self, coin: str, price: float):  # price in terms of coin's value
        if self.available_cash < 10.0:
            print("Not enough cash to buy, aborting")
            return
        if self.bought_in or self.buy_order_sent:
            print("Already bought in, aborting")
            return
        # convert all of our cash to coin
        quantity = round_down(self.available_cash/price, 6)  # check rounding precision later
        print("Buying "+str(quantity)+" "+coin+" for "+str(price)+"...")
        try:
            buy_order_limit = self.client.create_order(
                symbol=coin,
                side='BUY',
                type='LIMIT',
                timeInForce='GTC',
                quantity=quantity,
                price=price)
        except BinanceAPIException as e:
            print(e)
            return -1
        except BinanceOrderException as e:
            print(e)
            return -1

        print("Order out.")
        msg = "Buying "+str(quantity)+" "+coin+" for $"+str(price)+" USD"
        send_text(msg)

        self.buy_order_sent = True
        self.latest_order_id = buy_order_limit['orderId']
        self.bought_price = price
        return 0

    def sell(self, coin: str, price: float):
        if self.available_coin <= 0.0:
            print("Not enough coin to sell, aborting")
            return
        if not self.bought_in:
            print("buy order not completed, aborting")
            return
        # convert all of our coin to cash
        quantity = self.available_coin
        print("Selling "+str(quantity)+" "+coin+" for "+str(price)+"...")
        try:
            sell_order_limit = self.client.create_order(
                symbol=coin,
                side='SELL',
                type='LIMIT',
                timeInForce='GTC',
                quantity=quantity,
                price=price)
        except BinanceAPIException as e:
            print(e)
            return -1
        except BinanceOrderException as e:
            print(e)
            return -1

        print("Order out.")
        msg = "Selling " + str(quantity) + " "+coin+" for $" + str(price) + " USD"
        send_text(msg)

        self.bought_in = False
        self.latest_order_id = sell_order_limit['orderId']
        self.bought_price = -1.0
        return 0

    def cancel_recent_order(self, order_num: int):
        print("Cancelling order...")
        send_text("Order not filled, cancelling order")
        try:
            self.client.cancel_order(symbol=config.ticker+'USD', orderId=order_num)
        except BinanceAPIException as e:
            print(e)
            return -1
        except BinanceRequestException as e:
            print(e)
            return -1
        print("Order cancelled.")
        return 0

    def update_technicals(self, ticker: str):
        curr_price = self.client.get_symbol_ticker(symbol=ticker)["price"]
        curr_time = datetime.datetime.now()
        moving_average = btalib.ema(self.technicals, period=self.MA_timeframe).df.iloc[-1]['ema']
        rsi = btalib.rsi(self.technicals, period=self.RSI_timeframe).df.iloc[-1]['rsi']
        print("Updating "+config.ticker+" technicals: MA="+str(moving_average)+" RSI="+str(rsi))
        self.technicals.loc[curr_time] = [curr_price, moving_average, rsi]

    def check_buy_conditions(self):
        curr_price = float(self.technicals.iloc[-1]['close'])
        moving_average = float(self.technicals.iloc[-1]['MA'])
        rsi = float(self.technicals.iloc[-1]['RSI'])
        # threshold = moving_average - (moving_average * self.buyBelowMA)
        if not math.isnan(moving_average) and not math.isnan(rsi):
            if curr_price < moving_average - (moving_average * self.ma_lower_limit) and rsi <= self.rsi_lower_limit \
                    and not self.bought_in:
                print("Buy signal for "+config.ticker+"USD(MA: "+str(moving_average)+", RSI: "+str(rsi)+")")
                return True
        return False

    def check_sell_conditions(self):
        curr_price = float(self.technicals.iloc[-1]['close'])
        moving_average = float(self.technicals.iloc[-1]['MA'])
        rsi = float(self.technicals.iloc[-1]['RSI'])
        if not math.isnan(moving_average) and not math.isnan(rsi):
            if curr_price > self.bought_price + (self.bought_price * self.take_profit) and self.bought_in:
                print("Sell signal for "+config.ticker+"USD (MA: "+str(moving_average)+", RSI: "+str(rsi)+")")
                return True
        return False

    def start_trade_loop(self):
        # get historical prices so we can compute first few technicals
        extraTime = datetime.datetime.now().minute % 10  # so historical data is aligned to 10 min intervals
        klines = self.client.get_historical_klines(config.ticker+'USD', '1m', '8 hours and '+str(extraTime)+' minutes ago EST')
        close_prices = []
        close_times = []
        earliest_time = datetime.datetime.now() - datetime.timedelta(hours=8) - datetime.timedelta(minutes=extraTime)
        # strip the 10m intervals
        for n, line in enumerate(klines):
            if n % 10 == 0:
                close_prices.append(float(line[4]))
                close_times.append(str(earliest_time + datetime.timedelta(minutes=n)))
        self.technicals['date'] = close_times
        self.technicals['close'] = close_prices
        self.technicals.set_index('date', inplace=True)

        print("Starting bot")
        send_text("Starting bot")
        last_heartbeat = datetime.datetime.now()
        while 1:
            currTime = datetime.datetime.now()

            if (currTime - last_heartbeat).total_seconds() > (60 * 60 * 12):  # check if alive every 12 hours
                send_text("Bot is still alive")
                last_heartbeat = currTime
            # check indicators every 10 minutes
            if currTime.minute % 10 == 0:
                self.available_cash = float(self.client.get_asset_balance(asset='USD')['free'])
                self.available_coin = round_down(float(self.client.get_asset_balance(asset=config.ticker)['free']), 6)
                open_orders = self.client.get_open_orders(symbol=config.ticker+'USD')
                self.update_technicals(config.ticker+'USD')

                # update order status
                if self.buy_order_sent and not open_orders:  # open_orders = [], orders were filled
                    self.bought_in = True
                    self.buy_order_sent = False
                # cancel order if not filled
                elif self.buy_order_sent and open_orders:  # and time > 1 hour ???
                    cancel_order = self.cancel_recent_order(self.latest_order_id)
                    if cancel_order == 0:
                        self.bought_in = False
                        self.available_coin = 0
                        self.buy_order_sent = False

                curr_price = float(self.client.get_symbol_ticker(symbol=config.ticker+'USD')["price"])
                if self.check_buy_conditions():
                    print("Buy signal")
                    self.buy(config.ticker+'USD', curr_price)
                if self.check_sell_conditions():
                    self.sell(config.ticker+'USD', curr_price)
                time.sleep(60)
            else:
                time.sleep(28)

    def test(self):
        self.update_technicals(config.ticker)


def main():
    client = Client(config.binance_us_apikey, config.binance_us_secretkey, tld='us')
    bot = indicatorsBot(client)
    #bot.test()
    bot.start_trade_loop()


if __name__ == '__main__':
    main()
