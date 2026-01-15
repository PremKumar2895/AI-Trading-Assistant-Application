from collections import deque
import numpy as np

class SignalEngine:
    def __init__(self):
        pass

    def evaluate(self, candles):
        """
        Input: List of detected candle dicts from left to right.
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
        
        # Fallback: Just follow the strong trend if no specific pattern
        if signal == "WAIT" and abs(trend_score) > 0.6:
            if trend == "BULLISH":
                signal = "BUY"
                confidence = "LOW"
                reason = "Following Strong Trend"
            elif trend == "BEARISH":
                signal = "SELL" 
                confidence = "LOW"
                reason = "Following Strong Trend"

        return {
            "signal": signal,
            "confidence": confidence,
            "reason": reason,
            "trend": trend,
            "debug_info": {
                "trend_score": trend_score,
                "current_height": c3['total_height']
            }
        }
