from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from image_utils import preprocess_image, mask_overlay
from candle_detector import detect_candles, refine_candle_data
from signal_engine import SignalEngine
from window_manager import WindowManager
import uvicorn
import json

app = FastAPI()
signal_engine = SignalEngine()
window_manager = WindowManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("Client connected")
    
    # Simple state for this connection
    force_scan = False
    overlay_bounds = None # {x, y, w, h}
    
    try:
        while True:
            # 1. Check if we have a text message (command) or bytes (image)
            # This is tricky with `receive_bytes`.
            # A cleaner way is to use `receive()` and check type.
            message = await websocket.receive()
            
            if "text" in message:
                try:
                    cmd = json.loads(message["text"])
                    if "action" in cmd:
                        if cmd["action"] == "set_force_scan":
                            force_scan = cmd["value"]
                            print(f"Force Scan set to: {force_scan}")
                        elif cmd["action"] == "update_overlay_bounds":
                             # Expects: {x, y, w, h} (Screen coordinates)
                             overlay_bounds = cmd["bounds"]
                             # print(f"Overlay bounds updated: {overlay_bounds}") 
                except:
                    pass
                continue
            
            if "bytes" not in message:
                continue
                
            data = message["bytes"]
            
            try:
                # 3. Process Image
                # preprocess_image returns: (original_color, canny_edges, grayscale, inverted_gray)
                original, processed, gray_image, inverted = preprocess_image(data)

                # MASK OVERLAY (Prevent Self-OCR)
                if overlay_bounds:
                    x, y, w, h = overlay_bounds['x'], overlay_bounds['y'], overlay_bounds['width'], overlay_bounds['height']
                    mask_overlay(original, x, y, w, h)
                    mask_overlay(processed, x, y, w, h)
                    mask_overlay(gray_image, x, y, w, h)
                    mask_overlay(inverted, x, y, w, h)
                
                # 2. Check Active Window Context
                active_window_title = window_manager.get_active_window_info()
                is_trading = window_manager.is_trading_platform(active_window_title)
                
                # Pass 'inverted' (black text on white) image to OCR for best results on dark charts
                context = window_manager.extract_context(active_window_title, image=inverted)
                
                # OVERRIDE: If force_scan is True, ignore window check
                if not is_trading and not force_scan:
                    # Send INFO signal
                    debug_msg = f"No platform found. (Active: '{active_window_title}')"
                    await websocket.send_json({
                        "signal": "INFO",
                        "confidence": "HIGH",
                        "reason": debug_msg,
                        "trend": "NEUTRAL",
                        "context": context
                    })
                    continue
                
                # 4. Detect Candles
                candles = detect_candles(original, processed)
                valid_candles = refine_candle_data(candles)
                
                # 5. Evaluate Signal with Context
                result = signal_engine.evaluate(valid_candles, context)
                
                # 6. Send Result
                await websocket.send_json(result)
                
            except Exception as e:
                print(f"Error processing frame: {e}")
                await websocket.send_json({
                    "signal": "ERROR",
                    "reason": str(e)
                })

    except WebSocketDisconnect:
        print("Client disconnected")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
