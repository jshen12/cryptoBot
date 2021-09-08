# cryptoBot

An automated cryptocurrency trading bot 

## What it is

cryptoBot is an automated bot that buys and sells cryptocurrencies based on technical indicators. It places a BUY order if the current price is below the moving average and RSI is below a certain threshold. It places a SELL order if the price crosses above a take profit threshold. Note that this bot does not place a stop loss, use this code at your own risk.

## Running the Bot

### Create a Binance account

You will need a [Binance account](https://accounts.binance.us/en/register) to run this bot. Then generate a new API key from your account. Keep track of this key as you won't be able to access it later.

### Installing dependencies

Run `pip install -r requirements.txt` in the terminal.

### Edit configuration

Edit `config.py` with your binance api keys, as well as your email and phone number.  These will be used so that the bot can send updates by text. You can also change the currency traded here.

### Run

```shell
python indicatorsBot.py
```

