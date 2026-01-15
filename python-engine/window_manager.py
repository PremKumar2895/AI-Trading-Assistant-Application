import pygetwindow as gw
import re
import pytesseract
from PIL import Image

class WindowManager:
    def __init__(self):
        self.trading_platforms = [
            "TradingView",
            "MetaTrader", 
            "Binance",
            "Coinbase",
            "Kraken",
            "Thinkorswim",
            "E*TRADE",
            "Webull",
            "Binomo",
            "IQ Option",
            "Olymp Trade"
        ]
        self.ocr_available = True
        
        # PRO FEATURES: Auto-detect Tesseract in local folder (for Portable/Distributed App)
        # This allows you to bundle Tesseract with your app so users don't need to install it.
        import os
        import sys
        
        # Check standard local paths
        local_tesseract = os.path.join(os.getcwd(), "tesseract", "tesseract.exe")
        # Common Windows installation path
        system_tesseract = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        
        if os.path.exists(local_tesseract):
            print(f"Using Bundled Tesseract: {local_tesseract}")
            pytesseract.pytesseract.tesseract_cmd = local_tesseract
        elif os.path.exists(system_tesseract):
            print(f"Using System Tesseract: {system_tesseract}")
            pytesseract.pytesseract.tesseract_cmd = system_tesseract
        else:
            # Fallback to system PATH (Development mode)
            # If user hasn't installed it, ocr_available will flip to False later on error.
            pass

    def get_active_window_info(self):
        try:
            active_window = gw.getActiveWindow()
            if not active_window:
                return None
            
            title = active_window.title
            
            # If the active window is likely OUR app or an overlay, 
            # we should look for the most relevant background window.
            # "electron" or "ai assistant" might be our app name.
            if self._is_our_app(title):
                return self._find_background_trading_window()
                
            return title
        except Exception:
            return None

    def _is_our_app(self, title):
        if not title: return False
        t = title.lower()
        
        # Explicitly exclude File Explorer or other non-app windows that might contain the folder name
        if "file explorer" in t or "walkthrough" in t or "cmd" in t or "code" in t:
            return False
            
        # Common terms for our electron app
        # strict check for "AI Trading Assistant" is best, 
        # but "electron" is needed if in dev mode
        if "ai trading assistant" in t:
             return True
             
        if "electron" in t and "app" in t:
             return True

        return False

    def _find_background_trading_window(self):
        """
        Scans all visible windows to find one that matches our whitelist.
        Returns the title of the first match.
        """
        try:
            windows = gw.getAllTitles()
            for w_title in windows:
                if not w_title: continue
                if self.is_trading_platform(w_title):
                    return w_title
            return None
        except:
            return None

    def is_trading_platform(self, window_title):
        if not window_title:
            return False
            
        t = window_title.lower()
        # Exclude development/system windows that might have "trading" in the path/name
        blacklist = ["file explorer", "code", "cmd", "powershell", "terminal", "walkthrough", "task manager"]
        if any(b in t for b in blacklist):
            return False
        
        # Check if any known platform name is in the title (case-insensitive)
        title_lower = window_title.lower()
        for platform in self.trading_platforms:
            if platform.lower() in title_lower:
                return True
        
        # Fallback: check for common chart keywords if user uses browser
        # "Binomo" logic: Binomo browser title often includes "Binomo"
        # Also added "chart", "trade", "quote" generic terms
        keywords = ["chart", "trade", "trading", "quote", "market", "exchange", "crypto", "forex"]
        if any(k in title_lower for k in keywords):
             return True
             
        return False

    def extract_context(self, window_title, image=None):
        """
        Extracts Symbol and Timeframe from window title OR Image OCR.
        Prioritizes Window Title (fast). Falls back to full-screen OCR (slow but robust).
        """
        context = {
            "symbol": "UNKNOWN",
            "timeframe": "UNKNOWN", 
            "platform": "Unknown"
        }
        
        # 1. Window Title Analysis (Fastest)
        if window_title:
             # Platform check
             for platform in self.trading_platforms:
                 if platform.lower() in window_title.lower():
                     context['platform'] = platform
                     break
             
             # Symbol Regex
             symbol_match = re.search(r'\b[A-Z]{3,6}(?:/[A-Z]{3,6})?\b', window_title)
             if symbol_match: context["symbol"] = symbol_match.group(0)
             
             # Timeframe Regex
             tf_match = re.search(r'\b(\d+[mhdwM])\b', window_title)
             if tf_match: context["timeframe"] = tf_match.group(1)

        # 2. OCR Analysis (Robust Fallback)
        # Only run if we are missing info and have an image AND OCR is available
        if self.ocr_available and image is not None and (context["symbol"] == "UNKNOWN" or context["timeframe"] == "UNKNOWN"):
            try:
                # Need to convert raw bytes/image to something pytesseract likes
                # Assuming 'image' passed here is the PREPROCESSED binary/gray image
                
                # CROP: Remove Top 15% of image to avoid reading Browser Tabs / URL Bar
                # usage: image[y:y+h, x:x+w]
                ocr_image = image
                try:
                    h, w = image.shape[:2]
                    # Crop top 15% to remove browser UI (search bar, tabs)
                    # This prevents "Crypto IDX" from being read from an inactive tab
                    crop_top = int(h * 0.15) 
                    ocr_image = image[crop_top:, :]
                except:
                    pass

                # We need simple text extraction
                # config: --psm 11 (Sparse text) or 3 (Default)
                text = pytesseract.image_to_string(ocr_image, config='--psm 11')
                
                # Clean up newlines
                text = text.replace('\n', ' ')
                
                # Regex Search in OCR Text
                
                # BINOMO SPECIFIC: "Crypto IDX", "Altcoin IDX"
                # Priority: Check for explicit pairs first (EUR/USD) as they are often standard
                # But "Crypto IDX" is unique string.
                # If we cropped correctly, we should trust what we find.
                
                detected_symbol = "UNKNOWN"
                
                # 1. Look for Standard Pairs (e.g. EUR/USD)
                sym_ocr = re.search(r'\b[A-Z]{3,4}/[A-Z]{3,4}\b', text)
                if sym_ocr: 
                    detected_symbol = sym_ocr.group(0)

                # 2. Look for Binomo Specials (Only if standard pair not found or just found)
                # Actually, check all and see what's valid.
                if "Crypto IDX" in text: detected_symbol = "Crypto IDX"
                elif "Altcoin IDX" in text: detected_symbol = "Altcoin IDX"
                
                # If we found something, assign it.
                if detected_symbol != "UNKNOWN":
                    context["symbol"] = detected_symbol
                elif context["symbol"] == "UNKNOWN" and sym_ocr:
                     context["symbol"] = sym_ocr.group(0)

                # Price Extraction (Look for patterns like 123.45 near right side)
                # Simple heurustic: find largest number with 2-5 decimal places
                # or look for "Payout" percentage to ignore it.
                price_match = re.search(r'\b\d+\.\d{2,5}\b', text)
                if price_match:
                     context["current_price"] = price_match.group(0)

                # Timeframe
                if context["timeframe"] == "UNKNOWN":
                     # Look for "1m", "5m", "15s"
                     tf_ocr = re.search(r'\b(\d+)\s?([mM]in|[hH]our|[sS]ec|[mMhH])\b', text)
                     if tf_ocr:
                         context["timeframe"] = f"{tf_ocr.group(1)}{tf_ocr.group(2)[0].lower()}"
                         
            except pytesseract.TesseractNotFoundError:
                # Disable OCR for future calls to avoid log spam
                print("OCR Error: Tesseract not installed. Disabling OCR features.")
                self.ocr_available = False
                
            except Exception as e:
                # Catch generic errors but don't spam if it's just noise
                pass

        return context
