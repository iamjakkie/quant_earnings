import requests
import pandas as pd
import asyncio
import aiohttp
import websockets
from decimal import Decimal

from balance.exchanges.kucoin.helpers.kucoin_authenticator import KucoinAuthenticator
from base_model.exchange_helpers.connector import Connector, BalanceUnit

class KucoinConnector(Connector):
    def __init__(self, auth: KucoinAuthenticator):
        self.headers = auth.authenticate()
        self.currencies = []

    async def get_balance(self):
        url = 'https://api.kucoin.com/api/v1/accounts'
        async with aiohttp.ClientSession() as client:
            resp = await client.get(url, headers=self.headers)
            resp_json = await resp.json()
        if resp.status != 200:
            # TODO proper error handling
            raise "error"
        rows = resp_json['data']
        ts = pd.Timestamp.utcnow().replace(second=0, microsecond=0)
        self.balance_list = set()
        units = []
        for row in rows:
            if row['type'] == 'trade':
                unit = BalanceUnit(ts, row['currency'], row['balance'])
                self.balance_list.add(unit.currency)
                self.currencies.append(unit.currency)
                units.append(unit)

        return units

    async def get_tickers(self):
        url = 'https://api.kucoin.com/api/v1/prices'
        query_param = f"currencies={','.join(currency for currency  in self.currencies if currency != 'USDT')}"
        async with aiohttp.ClientSession() as client:
            resp = await client.get(url + "?" + query_param)
            resp_json = await resp.json()
        return resp_json['data']



    def get_balance_units(self):
        return super().get_balance_units()

    def get_currencies(self):
        print(type({unit.currency for unit in self.balance_list}))
        return {unit.currency for unit in self.balance_list}

    async def subscribe_ws(self):
        self._ws = await websockets.connect(WS_URL)
        params = {
            "time": int(time.time()),
            "channel": "spot.tickers",
            "event": "subscribe",
            "payload": [currency+"_USDT" for currency in self.balance_list if currency not in SKIP_CURRENCIES]
        }
        # params['auth'] = self._auth.gen_sign(params['channel'], params['event'], params['time'])
        print(params)
        await self._ws.send(json.dumps(params))
        
        while True:
            try:
                res = await asyncio.wait_for(self._ws.recv(), 30.)
                try:
                    msg = json.loads(res)

                    # API errors
                    if msg.get('error', None) is not None:
                        error = msg.get('error', {}).get('message', msg['error'])
                        print(error)
                    
                    # subscribe/unsubscribe
                    event = msg.get('event')
                    if event == 'subscribe':
                        status = msg.get('result', {}).get('status')
                        if status == 'success':
                            print('Subscribed successfully')
                        yield None
                    elif event == 'unsubscribe':
                        status = msg.get('result', {}).get('status')
                        if status == 'success':
                            print('Unsubscribed successfully')
                        yield None
                    else:
                        yield msg
                except ValueError:
                    continue
            except asyncio.TimeoutError:
                await asyncio.wait_for(self._ws.ping(), 10.)
            finally:
                pass

    def get_value(self):
        pass

        