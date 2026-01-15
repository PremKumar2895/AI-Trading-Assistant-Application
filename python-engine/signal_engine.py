from collections import deque
import numpy as np

class SignalEngine:
    def __init__(self):
        pass

    def evaluate(self, candles, context=None):
        """
        Input: List of detected candle dicts from left to right.
        Input: Context dict (Symbol, Timeframe, Platform)
        Output: Signal JSON
        """
        if not candles:
             return {
                "signal": "WAIT",
                "confidence": "LOW",
                "reason": "Scanning chart...",
                "trend": "NEUTRAL"
            }

        if len(candles) < 3:
            return {
                "signal": "WAIT",
                "confidence": "LOW",
                "reason": f"Not enough data ({len(candles)} candles found)",
                "trend": "NEUTRAL"
            }

        # Focus on recent history (up to last 10 for trend, last 3 for signal)
        recent = candles[-10:] 
        
        # 1. Calculate Trend (Bullish/Bearish based on localized price action)
        # using 'x' as proxy for time and 'y' (via heuristics) or just color dominance
        bullish_count = sum(1 for c in recent if c['type'] == 'bullish')
        bearish_count = sum(1 for c in recent if c['type'] == 'bearish')
        
        total = len(recent)
        trend_score = (bullish_count - bearish_count) / total # Range -1 to 1
        
        trend = "NEUTRAL"
        if trend_score > 0.3: trend = "BULLISH"
        if trend_score < -0.3: trend = "BEARISH"

        # 2. Analyze Immediate Price Action (Last 3 candles)
        last_3 = candles[-3:]
        c1, c2, c3 = last_3[0], last_3[1], last_3[2]
        
        # Candle Sizes (Momentum)
        avg_body = np.mean([c['total_height'] for c in candles])
        
        # Check patterns
        signal = "WAIT"
        confidence = "LOW"
        reason = f"Trend is {trend}"

        # Pattern: Three White Soldiers (Bullish) / Three Black Crows (Bearish)
        if all(c['type'] == 'bullish' for c in last_3):
            # Check if getting bigger (increasing momentum)
            if c3['total_height'] > c2['total_height'] > c1['total_height']:
                 signal = "BUY"
                 confidence = "HIGH"
                 reason = "Strong Bullish Momentum (3 Consecutive)"
            else:
                 signal = "BUY"
                 confidence = "MEDIUM"
                 reason = "Bullish Continuation"

        elif all(c['type'] == 'bearish' for c in last_3):
            if c3['total_height'] > c2['total_height'] > c1['total_height']:
                 signal = "SELL"
                 confidence = "HIGH"
                 reason = "Strong Bearish Momentum (3 Consecutive)"
            else:
                 signal = "SELL"
                 confidence = "MEDIUM"
                 reason = "Bearish Continuation"
        
        # Pattern: Engulfing (Simplified)
        # If current candle is opposite to previous and much larger
        elif c2['type'] == 'bearish' and c3['type'] == 'bullish':
            if c3['total_height'] > 1.5 * c2['total_height']:
                signal = "BUY"
                confidence = "HIGH"
                reason = "Bullish Engulfing Pattern"
                
        elif c2['type'] == 'bullish' and c3['type'] == 'bearish':
             if c3['total_height'] > 1.5 * c2['total_height']:
                signal = "SELL"
                confidence = "HIGH"
                reason = "Bearish Engulfing Pattern"

        # Pattern: Doji Reversal
        # Any very small candle after a run
        if c3['total_height'] < 0.3 * avg_body:
            # Doji detected
            if trend == "BULLISH":
                # Potential top?
                reason = "Doji Warning (Possible Reversal?)"
                confidence = "LOW"
            elif trend == "BEARISH":
                reason = "Doji Warning (Possible Reversal?)"
                confidence = "LOW"
        
        # Fallback: REMOVED to prevent false positives on noise.
        # We only want to signal on clear patterns.
        # if signal == "WAIT" and abs(trend_score) > 0.6: ...

        # Pattern calculation done above... (rest of method)

        # 3. Advanced Trade Analysis (Entry, SL, TP, Market Health)
        trade_setup = self.calculate_trade_setup(candles, signal, trend, context)

        return {
            "signal": signal,
            "confidence": confidence,
            "reason": reason,
            "trend": trend,
            "debug_info": {
                "trend_score": trend_score,
                "current_height": c3['total_height']
            },
            "context": context,
            "trade_setup": trade_setup
        }

    def calculate_trade_setup(self, candles, signal, trend, context=None):
        """
        Calculates Entry, Stop Loss, Take Profit, and Market Health statistics.
        Uses pixel units to determine relative Stop Loss levels.
        """
        if not candles: return None
        
        # Check for Real Price
        real_price = None
        if context and "current_price" in context:
            real_price = context["current_price"]
            
        # ... logic continues ...
        
        # 1. Market Health
        heights = [c['total_height'] for c in candles]
        avg_height = np.mean(heights)
        std_dev = np.std(heights)
        
        volatility = "Normal"
        if std_dev > avg_height * 0.5: volatility = "High (Volatile)"
        elif std_dev < avg_height * 0.1: volatility = "Low (Consolidation)"
            
        trend_strength = "Weak"
        recent_types = [c['type'] for c in candles[-5:]]
        if trend == "BULLISH":
            if recent_types.count('bullish') >= 4: trend_strength = "Strong"
            elif recent_types.count('bullish') == 3: trend_strength = "Medium"
        elif trend == "BEARISH":
             if recent_types.count('bearish') >= 4: trend_strength = "Strong"
             elif recent_types.count('bearish') == 3: trend_strength = "Medium"

        # 2. Trade Levels (Visual Proxies)
        # Check if we have a REAL price from OCR
        entry_text = "Market Price"
        if real_price:
            entry_text = f"Market: {real_price}"

        sl_text = "---"
        tp_text = "---"
        
        if signal == "BUY":
            sl_text = "Below Recent Low"
            tp_text = "Target: 1.5x Risk"
            if real_price:
                 # Simple simulation of SL/TP levels if we had pips. 
                 # For now just keep text description but cleaner.
                 sl_text = "Recent Swing Low"
        elif signal == "SELL":
            sl_text = "Above Recent High"
            tp_text = "Target: 1.5x Risk"
            
        # Timeframe Guidance
        tf_guidance = ""
        if volatility == "High (Volatile)":
            tf_guidance = " High Volatility detected: Suggest switching to 5m timeframe."
        elif volatility == "Low (Consolidation)":
            tf_guidance = " Low Volatility: 1m timeframe suitable for scalping."
        else:
            tf_guidance = " Market conditions stable."

        commentary = f"Market is {volatility}. {trend_strength} {trend} momentum.{tf_guidance}"
        if signal == "WAIT":
             commentary = f"Market is {volatility}.{tf_guidance} Waiting for clear setup."

        return {
            "entry": entry_text,
            "sl": sl_text,
            "tp": tp_text,
            "volatility": volatility,
            "trend_strength": trend_strength,
            "commentary": commentary
        }
