from itertools import product

from datamodel import Listing, Observation, Order, OrderDepth, ProsperityEncoder, Symbol, Trade, TradingState
from typing import *
import jsonpickle
import numpy as np
import json

from typing import List, Dict, Tuple,Any
import string
import jsonpickle
import numpy as np
import math
import json
from typing import Dict, List, Tuple, Any
from json import JSONEncoder
import jsonpickle
import statistics

logger = None

class Logger:
    def __init__(self) -> None:
        self.logs = []  # list buffer (fast)
        self.max_log_length = 3750

    def print(self, *objects: Any, sep: str = " ", end: str = "\n") -> None:
        self.logs.append(sep.join(str(o) for o in objects) + end)

    def flush(self, state: TradingState, orders: Dict[Symbol, List[Order]],
              conversions: int, trader_data: str) -> None:

        # Step 1: base size calculation
        base = [
            self.compress_state(state, ""),
            self.compress_orders(orders),
            conversions, "", ""
        ]
        base_json = self.to_json(base)
        base_length = len(base_json)

        # Step 2: remaining space
        max_item_length = (self.max_log_length - base_length) // 3

        # Step 3: convert logs list → string ONCE
        logs_str = "".join(self.logs)

        # Step 4: final output
        print(self.to_json([
            self.compress_state(state, self.truncate(state.traderData, max_item_length)),
            self.compress_orders(orders),
            conversions,
            self.truncate(trader_data, max_item_length),
            self.truncate(logs_str, max_item_length),
        ]))

        # Step 5: reset buffer correctly
        self.logs = []

    def truncate(self, value: str, max_length: int) -> str:
        return value if len(value) <= max_length else value[:max_length - 3] + "..." #till here

    def compress_state(self, state: TradingState, trader_data: str) -> list[Any]:
        listings = state.listings
        order_depths = state.order_depths
        own_trades = state.own_trades
        market_trades = state.market_trades
        observations = state.observations

        return [
            state.timestamp,
            trader_data,

        # listings (keep minimal)
            [[l.symbol, l.product] for l in listings.values()],

        # order book (unchanged - important)
            {s: [od.buy_orders, od.sell_orders] for s, od in order_depths.items()},

        # own trades (optional trim)
            [
                [t.symbol, t.price, t.quantity]
                for trades in own_trades.values() for t in trades
            ],

        # market trades (trimmed)
            [
                [t.symbol, t.price, t.quantity]
                for trades in market_trades.values() for t in trades
            ],

            state.position,

        # observations (trimmed hard)
            [
                observations.plainValueObservations
            ]
        ]
    

    def compress_orders(self, orders):
        result = []
        append = result.append

        for orders_list in orders.values():
            for o in orders_list:
                append([o.symbol, o.price, o.quantity])

        return result

    def to_json(self, value: Any) -> str:
        return json.dumps(value, cls=ProsperityEncoder, separators=(",", ":"))

logger = Logger()

class Product:
    TOMATOES = "TOMATOES"
    EMERALDS = "EMERALDS"

PARAMS = {
    Product.TOMATOES: {
        "take_width": 1,   # spread is 13, so take only clear mispricing
        "clear_width": 1,
        "edge": 6.5,
        "adverse_volume": 10,
        "prevent_adverse": False,
        "position_limit": 30,
        "orderflow_weight": 0.0,
        "impact_threshold": 0.02,
        "spread_alpha": 0.2,
        "inventory_accel": 0.15
    },
    Product.EMERALDS: {
        "take_width": 2,
        "clear_width": 1,
        "adverse_volume": 8,
        "prevent_adverse": False,
        "position_limit": 20,
        "edge": 2,
        "edge_scale": 0.4,
        "microprice_weight": 0.0,
        "join_edge": 8,
        "min_edge": 1.0
    }

}

from typing import Optional, Tuple

class Trader:
    def __init__(self, params=None):
        if params is None:
            params = PARAMS

        self.params = params

        # Position limits (linked to params)
        self.LIMIT = {
            Product.TOMATOES: params[Product.TOMATOES]["position_limit"],
            Product.EMERALDS: params[Product.EMERALDS]["position_limit"]
        }

        # Price history (for future signals)
        self.price_history = {
            Product.TOMATOES: [],
            Product.EMERALDS: []
        }

    def get_midprice(self, order_depth: OrderDepth) -> Optional[Tuple[float, float]]:
        if not order_depth or not order_depth.buy_orders or not order_depth.sell_orders:
            return None

        best_bid = max(order_depth.buy_orders.keys())
        best_ask = min(order_depth.sell_orders.keys())

        bid_volume = order_depth.buy_orders[best_bid]
        ask_volume = abs(order_depth.sell_orders[best_ask])

        mid = (best_bid + best_ask) / 2

        # Safety check
        if bid_volume + ask_volume == 0:
            return mid, mid

        # Microprice (directional fair value)
        microprice = (
            best_bid * ask_volume + best_ask * bid_volume
        ) / (bid_volume + ask_volume)

        return mid, microprice

    def get_fair_price(self, product: str, order_depth: OrderDepth) -> Optional[float]:
        result = self.get_midprice(order_depth)
        if result is None:
            return None

        mid, microprice = result
        params = self.params[product]

        fair = mid

        # Microprice adjustment (only if defined)
        if "microprice_weight" in params:
            fair += params["microprice_weight"] * (microprice - mid)

        return fair
    def take_best_orders(
            self,
            product: str,
            fair_value: float,
            take_width: float,
            orders: List[Order],
            order_depth: OrderDepth,
            position: int,
            buy_order_volume: int,
            sell_order_volume: int,
            prevent_adverse: bool = False,
            adverse_volume: int = 0
    ) -> Tuple[int, int, int]:

            position_limit = self.LIMIT[product]

    # =========================
    # INVENTORY SKEW (IMPORTANT)
    # =========================
            params = self.params[product]
            

    # =========================
    # SELL SIDE (WE BUY)
    # =========================
            if order_depth.sell_orders:
                best_ask = min(order_depth.sell_orders.keys())
                best_ask_amount = -order_depth.sell_orders[best_ask]

        # adverse selection filter
                if prevent_adverse and best_ask_amount > adverse_volume:
                    pass
                else:
                    if best_ask <= fair_value - take_width:
                        quantity = min(best_ask_amount, position_limit - position)

                        if quantity > 0:
                            orders.append(Order(product, best_ask, quantity))
                            buy_order_volume += quantity
                            position += quantity

                    # update book
                            order_depth.sell_orders[best_ask] += quantity
                            if order_depth.sell_orders[best_ask] == 0:
                                del order_depth.sell_orders[best_ask]

    # =========================
    # BUY SIDE (WE SELL)
    # =========================
            if order_depth.buy_orders:
                best_bid = max(order_depth.buy_orders.keys())
                best_bid_amount = order_depth.buy_orders[best_bid]

        # adverse selection filter
                if prevent_adverse and best_bid_amount > adverse_volume:
                    pass
                else:
                    if best_bid >= fair_value + take_width:
                        quantity = min(best_bid_amount, position_limit + position)

                        if quantity > 0:
                            orders.append(Order(product, best_bid, -quantity))
                            sell_order_volume += quantity
                            position -= quantity

                    # update book
                            order_depth.buy_orders[best_bid] -= quantity
                            if order_depth.buy_orders[best_bid] == 0:
                                del order_depth.buy_orders[best_bid]

            return buy_order_volume, sell_order_volume, position
    def market_make(
            self,
            product:str,
            orders: List[Order],
            bid: float,
            ask: float,
            position: int,
            buy_order_volume: int,
            sell_order_volume: int
    ) -> Tuple[int, int]:
        limit= self.LIMIT[product]
        skew_factor = 0.1
        inventory_shift = position * skew_factor

        final_bid = math.floor(bid - inventory_shift)
        final_ask = math.ceil(ask - inventory_shift)

        buy_quantity = limit - (position + buy_order_volume)
        if buy_quantity > 0:
            orders.append(Order(product, final_bid, buy_quantity))
            buy_order_volume += buy_quantity

        sell_quantity = limit + (position - sell_order_volume)
        if sell_quantity > 0:
            orders.append(Order(product, final_ask, -sell_quantity))
            sell_order_volume += sell_quantity

        return buy_order_volume, sell_order_volume
    def clear_position_order(
            self,
            product: str,
            fair_value: float,
            width: float,
            orders: List[Order],
            order_depth: OrderDepth,
            position: int,
            buy_order_volume: int,
            sell_order_volume: int,
    ) -> (int, int):
        position_after_take= position + buy_order_volume - sell_order_volume

        if position_after_take ==0:
            return buy_order_volume, sell_order_volume
        
        limit= self.params[product]["position_limit"]
        skew = position_after_take / limit
        adj_width = width * (1 - 0.3 * abs(skew))   # VERY LIGHT adjustment

        fair_for_bid = round(fair_value - adj_width)
        fair_for_ask = round(fair_value + adj_width)

        buy_quantity = limit - (position + buy_order_volume)
        sell_quantity = limit + (position - sell_order_volume)

    # --- SPEED IMPROVEMENT: best prices only ---
        best_bid = max(order_depth.buy_orders) if order_depth.buy_orders else None
        best_ask = min(order_depth.sell_orders) if order_depth.sell_orders else None

        # =========================================
    # 🟥 LONG → SELL
    # =========================================
        if position_after_take > 0 and best_bid is not None:

        # --- EMERALDS: add edge filter (minimal deviation) ---
            """if product == "EMERALDS":
                edge = self.params[product]["edge"]
                min_edge = self.params[product]["min_edge"]

                required_edge = max(min_edge, edge * 0.8)

                if best_bid - fair_value < required_edge:
                    return buy_order_volume, sell_order_volume"""

            if best_bid >= fair_for_ask:

                volume = order_depth.buy_orders[best_bid]

                sent_quantity = min(
                    sell_quantity,
                    position_after_take,
                    volume
                )

                if sent_quantity > 0:
                    orders.append(Order(product, best_bid, -abs(sent_quantity)))
                    sell_order_volume += abs(sent_quantity)

    # =========================================
    # 🟩 SHORT → BUY
    # =========================================
        if position_after_take < 0 and best_ask is not None:

            """if product == "EMERALDS":
                edge = self.params[product]["edge"]
                min_edge = self.params[product]["min_edge"]

                required_edge = max(min_edge, edge * 0.8)

                if fair_value - best_ask < required_edge:
                    return buy_order_volume, sell_order_volume"""

            if best_ask <= fair_for_bid:

                volume = abs(order_depth.sell_orders[best_ask])

                sent_quantity = min(
                    buy_quantity,
                    abs(position_after_take),
                    volume
                )

                if sent_quantity > 0:
                    orders.append(Order(product, best_ask, abs(sent_quantity)))
                    buy_order_volume += abs(sent_quantity)

        return buy_order_volume, sell_order_volume
    
    def tomatoes_fair_value(self, order_depth: OrderDepth, traderObject) -> float:

        if len(order_depth.sell_orders) != 0 and len(order_depth.buy_orders) != 0:

            best_ask = min(order_depth.sell_orders.keys())
            best_bid = max(order_depth.buy_orders.keys())

        # -----------------------------
        # SAME AS WINNER: FILTER
        # -----------------------------
            filtered_ask = [
                price for price in order_depth.sell_orders.keys()
                if abs(order_depth.sell_orders[price]) >= self.params["TOMATOES"]["adverse_volume"]
            ]

            filtered_bid = [
                price for price in order_depth.buy_orders.keys()
                if abs(order_depth.buy_orders[price]) >= self.params["TOMATOES"]["adverse_volume"]
            ]

            mm_ask = min(filtered_ask) if len(filtered_ask) > 0 else None
            mm_bid = max(filtered_bid) if len(filtered_bid) > 0 else None

        # -----------------------------
        # SAME AS WINNER: FALLBACK LOGIC
        # -----------------------------
            if mm_ask is None or mm_bid is None:
                if traderObject.get("tomatoes_last_price", None) is None:
                    mmmid_price = (best_ask + best_bid) / 2
                else:
                    mmmid_price = traderObject["tomatoes_last_price"]
            else:
                mmmid_price = (mm_ask + mm_bid) / 2

        # -----------------------------
        # 🔥 REPLACED PART: ORDERFLOW (instead of reversion)
        # -----------------------------
            best_bid_vol = abs(order_depth.buy_orders[best_bid])
            best_ask_vol = abs(order_depth.sell_orders[best_ask])

            imbalance = (best_bid_vol - best_ask_vol) / (best_bid_vol + best_ask_vol + 1)

            fair = mmmid_price + self.params["TOMATOES"]["orderflow_weight"] * imbalance

        # -----------------------------
        # SAME AS WINNER: STORE LAST PRICE
        # -----------------------------
            traderObject["tomatoes_last_price"] = mmmid_price

            return fair

        return None
    
    def emeralds_fair_value(self, order_depth: OrderDepth, traderObject) -> float:

        if not order_depth.sell_orders or not order_depth.buy_orders:
            return None
        true_mean = 10000.0
        best_ask = min(order_depth.sell_orders.keys())
        best_bid = max(order_depth.buy_orders.keys())
        mid = (best_ask + best_bid) / 2

        return true_mean
    def sma(self, order_depth: OrderDepth, traderObject, position: int):   #<------ changed this in code for 
        orders: List[Order] = []
        product = Product.EMERALDS
        position_limit = self.LIMIT[product]

        if not order_depth.sell_orders or not order_depth.buy_orders:
            return []

        best_ask = min(order_depth.sell_orders.keys())
        best_bid = max(order_depth.buy_orders.keys())
        mid_price = (best_ask + best_bid) / 2

        params = self.params[product]

        take_width = params["take_width"]

# fixed SMA settings (no extra params needed)
        av_len = 50
        trigger_z = 1.5
        max_quantity = 10

        # =========================
# 📊 PRICE HISTORY
# =========================
        if "emerald_prices" not in traderObject:
            traderObject["emerald_prices"] = []

        prices = traderObject["emerald_prices"]
        prices.append(mid_price)

        if len(prices) > av_len:
            prices.pop(0)

# need enough data
        if len(prices) < 10:
            return []

# =========================
# 📉 MEAN + VOLATILITY
# =========================
        mean_price = sum(prices) / len(prices)
        variance = sum((p - mean_price) ** 2 for p in prices) / len(prices)
        volatility = variance ** 0.5

        if volatility == 0:
            return []

# =========================
# 📦 BASE SIZE
# =========================
        bid_volume = abs(order_depth.buy_orders[best_bid])
        ask_volume = abs(order_depth.sell_orders[best_ask])
        avg_volume = (bid_volume + ask_volume) / 2

        base_quantity = min(int(avg_volume), max_quantity)

        # =========================
# 🔥 SIGNAL (Z-SCORE)
# =========================
        zscore = (mid_price - mean_price) / volatility

# scale position size with signal strength
        scale = min(abs(zscore), 3)
        quantity = int(base_quantity * scale)

# =========================
# 🔒 SAFE ORDER
# =========================
        def safe_order(price, qty):
            new_position = position + sum(o.quantity for o in orders) + qty

            if new_position > position_limit:
                qty = position_limit - (position + sum(o.quantity for o in orders))
            elif new_position < -position_limit:
                qty = -position_limit - (position + sum(o.quantity for o in orders))

            if qty != 0:
                orders.append(Order(product, int(price), int(qty)))

# =========================
# 🔥 ALPHA EXECUTION
# =========================
        if abs(zscore) > trigger_z:

            if zscore > 0 and position > -position_limit:
                safe_order(best_bid , -quantity)    # selling BELOW best bid — worst possible price <----------------

            elif zscore < 0 and position < position_limit:
                safe_order(best_ask , quantity)   # buying ABOVE best ask — worst possible price  <----------------
            return orders 

# ❌ no signal → do nothing
        return []
    def take_orders(
        self,
        product: str,
        order_depth: OrderDepth,
        fair_value: float,
        take_width: float,
        position: int,
        prevent_adverse: bool = False,
        adverse_volume: int = 0,
    ) -> (List[Order], int, int):

        orders: List[Order] = []
        buy_order_volume = 0
        sell_order_volume = 0

        if not order_depth.sell_orders or not order_depth.buy_orders:
            return orders, buy_order_volume, sell_order_volume

        """best_ask = min(order_depth.sell_orders.keys())
        best_bid = max(order_depth.buy_orders.keys())

        ask_vol = abs(order_depth.sell_orders[best_ask])
        bid_vol = abs(order_depth.buy_orders[best_bid])

    # =========================
    # 🔹 MICROSTRUCTURE LAYER (YOUR EDGE)
    # =========================
        denom = bid_vol + ask_vol + 1
        microprice = (best_bid * ask_vol + best_ask * bid_vol) / denom

        imbalance = (bid_vol - ask_vol) / (bid_vol + ask_vol + 1)

    # Adjust fair value slightly (VERY SMALL SHIFT)
        adjusted_fair = fair_value    #wrong as taking order i shoudl avoid and not what i should take. now done

    # =========================
    # 🔹 SMART TAKE WIDTH (ADAPTIVE)
    # ========================
        spread = best_ask - best_bid

    # widen in bad conditions
        adaptive_width = take_width  #too conservative now done
"""
    # =========================
    # 🔥 CALL WINNER CORE
    # ========================
        buy_order_volume, sell_order_volume, position = self.take_best_orders(
            product,
            fair_value,          # 👈 modified fair value
            take_width,         # 👈 smarter width
            orders,
            order_depth,
            position,
            buy_order_volume,
            sell_order_volume,
            prevent_adverse,
            adverse_volume,
        )

        return orders, buy_order_volume, sell_order_volume
    
    def clear_orders(
        self,
        product: str,
        order_depth: OrderDepth,
        fair_value: float,
        clear_width: float,
        position: int,
        buy_order_volume: int,
        sell_order_volume: int,
    ) -> (List[Order], int, int):

    # =========================
    # 🟢 EMERALDS = RESIN STYLE
    # =========================
        if product == Product.EMERALDS:

            orders = []

            position_after_take = position + buy_order_volume - sell_order_volume

            buy_quantity = self.params[product]["position_limit"] - (position + buy_order_volume)
            sell_quantity = self.params[product]["position_limit"] + (position - sell_order_volume)

            edge = self.params[product]["edge"]

        # =========================
        # 🔴 NET LONG → SELL
        # =========================
            if position_after_take > 0:

                bids_to_hit = {
                    price: vol for price, vol in order_depth.buy_orders.items()
                    if price >= fair_value - clear_width
                }

                if bids_to_hit:
                    best_clear_bid = max(bids_to_hit.keys())

                    # 🔥 Your enhancement (edge-aware clearing)
                    if best_clear_bid >= fair_value - edge:
                        available_volume = abs(bids_to_hit[best_clear_bid])
                        qty_to_clear = min(abs(position_after_take), available_volume)
                        sent_quantity = min(sell_quantity, qty_to_clear)

                        if sent_quantity > 0:
                            orders.append(Order(product, best_clear_bid, -sent_quantity))
                            sell_order_volume += sent_quantity

        # =========================
        # 🔵 NET SHORT → BUY
        # =========================
            if position_after_take < 0:

                asks_to_hit = {
                    price: vol for price, vol in order_depth.sell_orders.items()
                    if price <= fair_value + clear_width   # ✅ symmetry fix
                }

                if asks_to_hit:
                    best_clear_ask = min(asks_to_hit.keys())
                    if best_clear_ask <= fair_value + edge:

                        available_volume = abs(asks_to_hit[best_clear_ask])
                        qty_to_clear = min(abs(position_after_take), available_volume)
                        sent_quantity = min(buy_quantity, qty_to_clear)

                        if sent_quantity > 0:
                            orders.append(Order(product, best_clear_ask, sent_quantity))
                            buy_order_volume += sent_quantity

            return orders, buy_order_volume, sell_order_volume

    # =========================
    # 🟡 TOMATOES = KELP STYLE
    # =========================
        else:
            orders: List[Order] = []

            buy_order_volume, sell_order_volume = self.clear_position_order(
                product,
                fair_value,
                int(clear_width),  #clear orders almost never find a matching price. 
                orders,
                order_depth,
                position,
                buy_order_volume,
                sell_order_volume,
            )

            return orders, buy_order_volume, sell_order_volume

    def make_orders(
        self,
        product,
        order_depth: OrderDepth,
        fair_value: float,
        position: int,
        buy_order_volume: int,
        sell_order_volume: int,
        disregard_edge: float,
        join_edge: float,
        default_edge: float,
        manage_position: bool = False,
        soft_position_limit: int = 0,
        traderObject: dict = None,
    ) -> (List[Order], int, int):

    # =========================
    # 🍅 TOMATOES → Stable Market Making
    # =========================
        if product == Product.TOMATOES:
            orders = []
            position_limit = self.params[product]["position_limit"]
            take_width = self.params[product].get("edge", self.params[product]["take_width"])

        # best ask above fair
            asks_above = [
                price for price in order_depth.sell_orders.keys()
                if price > fair_value + take_width
            ]
            best_ask_above_fair = min(asks_above) if asks_above else (fair_value + take_width)

        # best bid below fair
            bids_below = [
                price for price in order_depth.buy_orders.keys()
                if price < fair_value - take_width
            ]
            best_bid_below_fair = max(bids_below) if bids_below else (fair_value - take_width)

        # push logic
            if best_ask_above_fair <= fair_value + take_width + 1:
                if position <= position_limit:
                    best_ask_above_fair = fair_value + take_width + 2

            if best_bid_below_fair >= fair_value - take_width - 1:
                if position >= -position_limit:
                    best_bid_below_fair = fair_value - take_width - 2

            bid_price = best_bid_below_fair + 1
            ask_price = best_ask_above_fair - 1

            buy_order_volume, sell_order_volume = self.market_make(
                product,
                orders,
                bid_price,
                ask_price,
                position,
                buy_order_volume,
                sell_order_volume,
            )

            return orders, buy_order_volume, sell_order_volume


    # =========================
    # 💎 EMERALDS → Edge-based Market Making
    # =========================
        if product == Product.EMERALDS:
            orders = []
            position_limit = self.params[product]["position_limit"]

            edge = self.params[product]["edge"]
            min_edge = self.params[product]["min_edge"]

            effective_edge = max(min_edge, edge)

            asks_above = [
                price for price in order_depth.sell_orders.keys()
                if price > fair_value + effective_edge
            ]
            best_ask_above_fair = min(asks_above) if asks_above else (fair_value + effective_edge)

            bids_below = [
                price for price in order_depth.buy_orders.keys()
                if price < fair_value - effective_edge
            ]
            best_bid_below_fair = max(bids_below) if bids_below else (fair_value - effective_edge)

        # push logic
            if best_ask_above_fair <= fair_value + effective_edge + 1:
                if position <= position_limit:
                    best_ask_above_fair = fair_value + effective_edge + 2

            if best_bid_below_fair >= fair_value - effective_edge - 1:
                if position >= -position_limit:
                    best_bid_below_fair = fair_value - effective_edge - 2
            bid_price = best_bid_below_fair + 1
            ask_price = best_ask_above_fair - 1

            buy_order_volume, sell_order_volume = self.market_make(
                product,
                orders,
                bid_price,
                ask_price,
                position,
                buy_order_volume,
                sell_order_volume,
            )

            return orders, buy_order_volume, sell_order_volume


    # =========================
    # 🔁 GENERAL ADAPTIVE LOGIC (fallback / shared)
    # =========================
        else:
            orders: List[Order] = []

            if product == Product.TOMATOES:
                disregard_edge = self.params[product]["take_width"]
                join_edge = 1
                default_edge = self.params[product]["take_width"]

            elif product == Product.EMERALDS:
                disregard_edge = self.params[product]["min_edge"]
                join_edge = self.params[product]["join_edge"]
                default_edge = self.params[product]["edge"]

            asks_above_fair = [
                price for price in order_depth.sell_orders.keys()
                if price > fair_value + disregard_edge
            ]

            bids_below_fair = [
                price for price in order_depth.buy_orders.keys()
                if price < fair_value - disregard_edge
            ]

            best_ask_above_fair = min(asks_above_fair) if asks_above_fair else None
            best_bid_below_fair = max(bids_below_fair) if bids_below_fair else None

            ask = round(fair_value + default_edge)
            if best_ask_above_fair is not None:
                if abs(best_ask_above_fair - fair_value) <= join_edge:
                    ask = best_ask_above_fair
                else:
                    ask = best_ask_above_fair - 1

            bid = round(fair_value - default_edge)
            if best_bid_below_fair is not None:
                if abs(fair_value - best_bid_below_fair) <= join_edge:
                    bid = best_bid_below_fair
                else:
                    bid = best_bid_below_fair + 1
        # inventory skew
            if manage_position:
                soft_limit = self.params[product]["position_limit"] * 0.7

                if position > soft_limit:
                    ask -= 1
                elif position < -soft_limit:
                    bid += 1

            buy_order_volume, sell_order_volume = self.market_make(
                product,
                orders,
                bid,
                ask,
                position,
                buy_order_volume,
                sell_order_volume,
            )

            return orders, buy_order_volume, sell_order_volume
        
    def run(self, state: TradingState):

        traderObject = {}
        if state.traderData:
            traderObject = jsonpickle.decode(state.traderData)

        result =  {}

    # =========================
    # 🍅 TOMATOES (RESIN STYLE)
    # =========================
        if Product.TOMATOES in self.params and Product.TOMATOES in state.order_depths:

            position = state.position.get(Product.TOMATOES, 0)
            order_depth = state.order_depths[Product.TOMATOES]

        # 🔹 Fair value
            fair_value = self.tomatoes_fair_value(order_depth, traderObject)
            if fair_value is None:
                result[Product.TOMATOES] = []
            else:

            # 1️⃣ TAKE
                take_orders, buy_vol, sell_vol = self.take_orders(
                    Product.TOMATOES,
                    order_depth,
                    fair_value,
                    self.params[Product.TOMATOES]["take_width"],
                    position,
                    self.params[Product.TOMATOES]["prevent_adverse"],
                    self.params[Product.TOMATOES]["adverse_volume"],
                )

            # 2️⃣ CLEAR
                clear_orders, buy_vol, sell_vol = self.clear_orders(
                    Product.TOMATOES,
                    order_depth,
                    fair_value,
                    self.params[Product.TOMATOES]["clear_width"],
                    position,
                    buy_vol,
                    sell_vol,
                )
            # 3️⃣ MAKE
                make_orders, _, _ = self.make_orders(
                    Product.TOMATOES,
                    order_depth,
                    fair_value,
                    position,
                    buy_vol,
                    sell_vol,
                    disregard_edge=self.params[Product.TOMATOES]["take_width"],
                    join_edge=1,
                    default_edge=self.params[Product.TOMATOES]["take_width"],
                    traderObject=traderObject,
                )

                result[Product.TOMATOES] = take_orders + clear_orders + make_orders
        if Product.EMERALDS in self.params and Product.EMERALDS in state.order_depths:
 
            position = state.position.get(Product.EMERALDS, 0)
            order_depth = state.order_depths[Product.EMERALDS]
 
            fair_value = self.emeralds_fair_value(order_depth, traderObject)
            if fair_value is None:
                result[Product.EMERALDS] = []
            else:
                take_orders, buy_vol, sell_vol = self.take_orders(
                    Product.EMERALDS,
                    order_depth,
                    fair_value,
                    self.params[Product.EMERALDS]["take_width"],
                    position,
                    self.params[Product.EMERALDS]["prevent_adverse"],
                    self.params[Product.EMERALDS]["adverse_volume"],
                )
 
                clear_orders, buy_vol, sell_vol = self.clear_orders(
                    Product.EMERALDS,
                    order_depth,
                    fair_value,
                    self.params[Product.EMERALDS]["clear_width"],
                    position,
                    buy_vol,
                    sell_vol,
                )
 
                make_orders, _, _ = self.make_orders(
                    Product.EMERALDS,
                    order_depth,
                    fair_value,
                    position,
                    buy_vol,
                    sell_vol,
                    disregard_edge=self.params[Product.EMERALDS]["min_edge"],
                    join_edge=self.params[Product.EMERALDS]["join_edge"],
                    default_edge=self.params[Product.EMERALDS]["edge"],
                    traderObject=traderObject,
                )
 
                result[Product.EMERALDS] = take_orders + clear_orders + make_orders     

    # =========================
    # 📦 FINALIZE
    # =========================
        traderData = jsonpickle.encode(traderObject)
        conversions = 1

        logger.flush(state, result, conversions, traderData)
        return result, conversions, traderData
    


#"""if Product.EMERALDS in self.params and Product.EMERALDS in state.order_depths:

 #           position = state.position.get(Product.EMERALDS, 0)
  #          order_depth = state.order_depths[Product.EMERALDS]

        # 🔹 Fair value
   #         fair_value = self.emeralds_fair_value(order_depth, traderObject)
    #        if fair_value is None:
     #           result[Product.EMERALDS] = []
      #      else:
#
 #           # 1️⃣ TAKE
  #              take_orders, buy_vol, sell_vol = self.take_orders(
   #                 Product.EMERALDS,
    #                order_depth,
     #               fair_value,
      #              self.params[Product.EMERALDS]["take_width"],
       #####
            ## 2️⃣ CLEAR
             ##      Product.EMERALDS,
               #     order_depth,
                ##   self.params[Product.EMERALDS]["clear_width"],
       #             position,
        #            buy_vol,
         #           sell_vol,
          #      )
           # # 3️⃣ MAKE
            ##       Product.EMERALDS,
              #      order_depth,
   ####              sell_vol,
       #             disregard_edge=self.params[Product.EMERALDS]["min_edge"],
        #            join_edge=self.params[Product.EMERALDS]["join_edge"],
         #           default_edge=self.params[Product.EMERALDS]["edge"],
          #          traderObject=traderObject,
           ##     )
#
 #               result[Product.EMERALDS] = take_orders + clear_orders + make_orders"""