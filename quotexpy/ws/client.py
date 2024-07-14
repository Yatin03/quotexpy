"""Module for Quotex websocket."""

import os
import json
import random
import logging
import time
import asyncio

import websocket
from quotexpy import global_value
from quotexpy.http.user_agents import agents
from quotexpy.utils import is_valid_json

user_agent_list = agents.split("\n")
logger = logging.getLogger(__name__)


class WebsocketClient(object):
    """Class for work with Quotex API websocket."""

    def __init__(self, api):
        """
        :param api: The instance of :class:`QuotexAPI
            <quotexpy.api.QuotexAPI>`.
        :trace_ws: Enables and disable `enableTrace` in WebSocket Client.
        """
        self.api = api
        self.headers = {
            "User-Agent": (
                self.api.user_agent
                if self.api.user_agent
                else user_agent_list[random.randint(0, len(user_agent_list) - 1)]
            ),
        }

        websocket.enableTrace(self.api.trace_ws)
        self.wss = websocket.WebSocketApp(
            self.api.wss_url,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open,
            on_ping=self.on_ping,
            on_pong=self.on_pong,
            header=self.headers,
            cookie=self.api.cookies,
        )

        self.logger = logging.getLogger(__name__)

    def on_message(self, wss, wm):
        """Method to process websocket messages."""
        global_value.ssl_Mutual_exclusion = True
        current_time = time.localtime()
        if isinstance(wm, bytes):
            wm = wm[1:].decode()
        self.logger.info(wm)
        if current_time.tm_sec in [0, 20, 40]:
            self.wss.send('42["tick"]')
        try:
            if "authorization/reject" in wm:
                if os.path.isfile(".session.json"):
                    os.remove(".session.json")
                global_value.SSID = None
                global_value.check_rejected_connection = 1
            elif "s_authorization" in wm:
                global_value.check_accepted_connection = 1
            elif "instruments/list" in wm:
                global_value.started_listen_instruments = True
            try:
                if is_valid_json(wm):
                    message = json.loads(wm)
                    self.api.wss_message = message
                if isinstance(self.api.wss_message, dict):
                    if self.api.wss_message.get("signals"):
                        time_in = self.api.wss_message.get("time")
                        for i in self.api.wss_message["signals"]:
                            try:
                                self.api.signal_data[i[0]] = {}
                                self.api.signal_data[i[0]][i[2]] = {}
                                self.api.signal_data[i[0]][i[2]]["dir"] = i[1][0]["signal"]
                                self.api.signal_data[i[0]][i[2]]["duration"] = i[1][0]["timeFrame"]
                            except:
                                self.api.signal_data[i[0]] = {}
                                self.api.signal_data[i[0]][time_in] = {}
                                self.api.signal_data[i[0]][time_in]["dir"] = i[1][0][1]
                                self.api.signal_data[i[0]][time_in]["duration"] = i[1][0][0]
                    elif self.api.wss_message.get("liveBalance") or self.api.wss_message.get("demoBalance"):
                        self.api.account_balance = self.api.wss_message
                    elif self.api.wss_message.get("index"):
                        self.api.candles.candles_data = self.api.wss_message
                    elif self.api.wss_message.get("id"):
                        self.api.trade_successful = self.api.wss_message
                        self.api.trade_id = self.api.wss_message["id"]
                        self.api.timesync.server_timestamp = self.api.wss_message["closeTimestamp"]
                    elif self.api.wss_message.get("ticket"):
                        self.api.sold_options_respond = self.api.wss_message
                    elif self.api.wss_message.get("isDemo") and self.api.wss_message.get("balance"):
                        self.api.training_balance_edit_request = self.api.wss_message
                    elif self.api.wss_message.get("error"):
                        global_value.websocket_error_reason = self.api.wss_message.get("error")
                        global_value.check_websocket_if_error = True
                        if global_value.websocket_error_reason == "not_money":
                            self.api.account_balance = {"liveBalance": 0}
            except Exception as err:
                self.logger.error(err)
            if self.api.wss_message and not isinstance(self.api.wss_message, int):
                if "call" in wm or "put" in wm:
                    self.api.instruments = self.api.wss_message
                if isinstance(self.api.wss_message, list):
                    for item in self.api.wss_message:
                        if "amount" in item and "profit" in item:
                            params = {}
                            last = self.api.wss_message[0]
                            self.api.profit_in_operation = last["profit"]
                            params["win"] = True if last["profit"] > 0 else False
                            params["game_state"] = 1
                            self.api.listinfodata.set(last["id"], params["win"], params["game_state"])
                            break
                if str(self.api.wss_message) == "41":
                    self.logger.info("disconnection event triggered by the platform, running automatic reconnection")
                    global_value.check_websocket_if_connect = 0
                    asyncio.run(self.api.reconnect())
                if "51-" in str(self.api.wss_message):
                    self.api._temp_status = str(self.api.wss_message)
                elif self.api._temp_status == """451-["settings/list",{"_placeholder":true,"num":0}]""":
                    self.api.settings_list = self.api.wss_message
                    self.api._temp_status = ""
                elif self.api._temp_status == """451-["history/list/v2",{"_placeholder":true,"num":0}]""":
                    self.api.candles.candles_data = self.api.wss_message["candles"]
                    self.api.candle_v2_data[self.api.wss_message["asset"]] = self.api.wss_message["candles"]
                    self.api.candle_v2_data[self.api.wss_message["asset"]]["candles"] = [
                        {"time": candle[0], "open": candle[1], "close": candle[2], "high": candle[3], "low": candle[4]}
                        for candle in self.api.wss_message["candles"]
                    ]
                elif len(self.api.wss_message[0]) == 4:
                    result = {"time": self.api.wss_message[0][1], "price": self.api.wss_message[0][2]}
                    self.api.realtime_price[self.api.wss_message[0][0]].append(result)
                elif len(self.api.wss_message[0]) == 2:
                    result = {
                        "sentiment": {
                            "sell": 100 - int(self.api.wss_message[0][1]),
                            "buy": int(self.api.wss_message[0][1]),
                        }
                    }
                    self.api.realtime_sentiment[self.api.wss_message[0][0]] = result
        except Exception as err:
            self.logger.error(err)
        global_value.ssl_Mutual_exclusion = False

    def on_error(self, wss, error):
        """Method to process websocket errors."""
        logger.error(error)
        global_value.websocket_error_reason = str(error)
        global_value.check_websocket_if_error = True

    def on_open(self, wss):
        """Method to process websocket open."""
        logger.info("websocket client connected")
        global_value.check_websocket_if_connect = 1
        self.wss.send('42["tick"]')
        self.wss.send('42["indicator/list"]')
        self.wss.send('42["drawing/load"]')
        self.wss.send('42["pending/list"]')
        self.wss.send('42["chart_notification/get"]')

    def on_close(self, wss, close_status_code, close_msg):
        """Method to process websocket close."""
        logger.info("websocket connection closed")
        global_value.check_websocket_if_connect = 0

    def on_ping(self, wss, ping_msg):
        pass

    def on_pong(self, wss, pong_msg):
        self.wss.send("2")
