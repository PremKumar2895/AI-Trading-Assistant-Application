from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from image_utils import preprocess_image
from candle_detector import detect_candles, refine_candle_data
from signal_engine import SignalEngine
import uvicorn
import json

app = FastAPI()
signal_engine = SignalEngine()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("Client connected")
    try:
        while True:
            # 1. Receive Image Bytes
            data = await websocket.receive_bytes()
            
            # 2. Process Image
            try:
                original, processed, _ = preprocess_image(data)
                
                # 3. Detect Candles
                candles = detect_candles(original, processed)
                valid_candles = refine_candle_data(candles)
                
                # 4. Evaluate Signal
                result = signal_engine.evaluate(valid_candles)
                
                # 5. Send Result
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
    uvicorn.run(app, host="0.0.0.0", port=8000)
