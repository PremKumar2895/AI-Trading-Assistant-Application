import cv2
import numpy as np
import os

# Path to the uploaded image artifact
img_path = r"C:\Users\premk\.gemini\antigravity\brain\02e0e77f-0c55-4014-8ca4-74c169fa715d\uploaded_image_1768484804864.png"

def debug_detection():
    if not os.path.exists(img_path):
        print(f"Error: Image not found at {img_path}")
        return

    # Load as if it were coming from the app (which uses cv2.imdecode usually, but imread is similar)
    original_img = cv2.imread(img_path)
    
    # Preprocess (simplify based on assumed logic, or import if possible. Let's replicate simple edge detection)
    gray = cv2.cvtColor(original_img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    
    # Find contours
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    print(f"Found {len(contours)} contours")
    
    bounding_boxes = [cv2.boundingRect(c) for c in contours]
    cnt_bbox_zip = zip(contours, bounding_boxes)
    sorted_cnts = sorted(cnt_bbox_zip, key=lambda b: b[1][0])

    for i, (cnt, bbox) in enumerate(sorted_cnts):
        x, y, w, h = bbox
        
        # Filter (same as candle_detector.py)
        if w * h < 50: continue
        if float(w)/h > 1.2: continue
        
        # ROI
        roi = original_img[y:y+h, x:x+w]
        
        # Color Logic using HSV
        hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        
        lower_red1 = np.array([0, 50, 50])
        upper_red1 = np.array([10, 255, 255])
        lower_red2 = np.array([170, 50, 50])
        upper_red2 = np.array([180, 255, 255])
        lower_green = np.array([35, 50, 50])
        upper_green = np.array([95, 255, 255])
        
        mask_red1 = cv2.inRange(hsv_roi, lower_red1, upper_red1)
        mask_red2 = cv2.inRange(hsv_roi, lower_red2, upper_red2)
        mask_green = cv2.inRange(hsv_roi, lower_green, upper_green)
        
        red_pixels = cv2.countNonZero(mask_red1) + cv2.countNonZero(mask_red2)
        green_pixels = cv2.countNonZero(mask_green)
        total_pixels = w * h
        
        candle_type = "skipped (noise)"
        if green_pixels > total_pixels * 0.2:
            candle_type = "bullish"
        elif red_pixels > total_pixels * 0.2:
            candle_type = "bearish"
            
        if candle_type == "bullish" and red_pixels > green_pixels: candle_type = "bearish"
        elif candle_type == "bearish" and green_pixels > red_pixels: candle_type = "bullish"

        print(f"Candle {i}: Pos=({x},{y}) Size={w}x{h} G={green_pixels} R={red_pixels} Type={candle_type}")

if __name__ == "__main__":
    debug_detection()
