from datamodel import OrderDepth, TradingState, Order
from typing import List
import numpy as np


class Trader:

    # ============================
    # 📊 MICROPRICE (TRUE FAIR VALUE)
    # ============================
    def microprice(self, best_bid, best_ask, buy_orders, sell_orders):
        bid_vol = sum(buy_orders.values())
        ask_vol = sum(sell_orders.values())
        return (best_bid * ask_vol + best_ask * bid_vol) / (bid_vol + ask_vol + 1e-6)

    # ============================
    # 🔥 ORDER FLOW
    # ============================
    def order_flow(self, state, product):
        trades = state.market_trades.get(product, [])
        buy, sell = 0, 0

        for t in trades:
            if t.buyer:
                buy += t.quantity
            if t.seller:
                sell += t.quantity

        return np.tanh((buy - sell) / 20)

    # ============================
    # 📚 ORDER BOOK IMBALANCE
    # ============================
    def order_book_imbalance(self, buy_orders, sell_orders):
        bid_vol = sum(buy_orders.values())
        ask_vol = sum(sell_orders.values())
        return (bid_vol - ask_vol) / (bid_vol + ask_vol + 1e-6)

    # ============================
    # 🚀 MAIN
    # ============================
    def run(self, state: TradingState):

        result = {}

        for product in state.order_depths:

            order_depth = state.order_depths[product]
            orders: List[Order] = []

            if not order_depth.buy_orders or not order_depth.sell_orders:
                result[product] = []
                continue

            buy_orders = dict(sorted(order_depth.buy_orders.items(), reverse=True))
            sell_orders = dict(sorted(order_depth.sell_orders.items()))

            best_bid = max(buy_orders.keys())
            best_ask = min(sell_orders.keys())

            mid = (best_bid + best_ask) / 2
            spread = best_ask - best_bid

            if spread <= 1:
                result[product] = []
                continue

            position = state.position.get(product, 0)
            limit = 20

            # ============================
            # 🧠 SIGNALS
            # ============================
            fair = self.microprice(best_bid, best_ask, buy_orders, sell_orders)
            flow = self.order_flow(state, product)
            imbalance = self.order_book_imbalance(buy_orders, sell_orders)

            confidence = abs(flow) + abs(imbalance)

            # ============================
            # 🎯 1. SNIPING (CORE ALPHA)
            # ============================
            for price, volume in sell_orders.items():
                edge = fair - price

                if edge > 2 and flow > 0.2 and imbalance > 0.1:
                    size = min(-volume, limit - position, int(4 + 10 * confidence))
                    orders.append(Order(product, price, size))

            for price, volume in buy_orders.items():
                edge = price - fair

                if edge > 2 and flow < -0.2 and imbalance < -0.1:
                    size = min(volume, position + limit, int(4 + 10 * confidence))
                    orders.append(Order(product, price, -size))

            # ============================
            # 🚀 2. MOMENTUM (BIG MONEY)
            # ============================
            if flow > 0.8 and imbalance > 0.5:
                size = min(15, limit - position)
                orders.append(Order(product, best_ask, size))

            elif flow < -0.8 and imbalance < -0.5:
                size = min(15, position + limit)
                orders.append(Order(product, best_bid, -size))

            # ============================
            # 💥 3. REVERSAL (EDGE CASE)
            # ============================
            if flow > 0.5 and imbalance < -0.3:
                size = min(10, position + limit)
                orders.append(Order(product, best_bid, -size))

            elif flow < -0.5 and imbalance > 0.3:
                size = min(10, limit - position)
                orders.append(Order(product, best_ask, size))

            # ============================
            # 🧱 4. MARKET MAKING (BASE INCOME)
            # ============================
            if spread > 4:
                mm_size = 6  # wide spread = more profit
            else:
                mm_size = 2

            bid_price = best_bid + 1
            ask_price = best_ask - 1

            # inventory control
            if position > 10:
                ask_price -= 1
            elif position < -10:
                bid_price += 1

            orders.append(Order(product, bid_price, mm_size))
            orders.append(Order(product, ask_price, -mm_size))

            result[product] = orders

        return result, 0, ""