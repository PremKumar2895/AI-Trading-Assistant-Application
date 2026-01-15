import cv2
import numpy as np

def detect_candles(original_img, processed_img):
    """
    Detects candles from the processed edge image.
    Returns a list of dictionaries containing relative OHLC and properties.
    """
    contours, _ = cv2.findContours(processed_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    candles = []
    height, width = processed_img.shape

    # Filter out noise contours (too small)
    min_area = 50 
    
    # Sort contours from left to right to preserve time order
    bounding_boxes = [cv2.boundingRect(c) for c in contours]
    
    # Zip contours with their bounding boxes and sort by X coordinate
    cnt_bbox_zip = zip(contours, bounding_boxes)
    sorted_cnts = sorted(cnt_bbox_zip, key=lambda b: b[1][0])

    for cnt, bbox in sorted_cnts:
        x, y, w, h = bbox
        
        if w * h < min_area:
            continue

        # Aspect Ratio Filter
        # Candles (with wicks) are usually tall (h > w)
        # Ratio w/h should be < 1.2 (roughly square or taller)
        # Wide rectangles (w > 1.2h) are usually buttons or labels.
        aspect_ratio = float(w) / h
        if aspect_ratio > 1.2: 
            continue
            
        # Extract ROI
        roi = original_img[y:y+h, x:x+w]
        
        # Color Logic using HSV
        hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        
        # Define masks
        # Red: Hue 0-10 and 170-180
        lower_red1 = np.array([0, 50, 50])
        upper_red1 = np.array([10, 255, 255])
        lower_red2 = np.array([170, 50, 50])
        upper_red2 = np.array([180, 255, 255])
        
        # Green: Hue 35-85 (Covers slight yellow-green to teal-green)
        lower_green = np.array([35, 50, 50])
        upper_green = np.array([95, 255, 255])
        
        mask_red1 = cv2.inRange(hsv_roi, lower_red1, upper_red1)
        mask_red2 = cv2.inRange(hsv_roi, lower_red2, upper_red2)
        mask_green = cv2.inRange(hsv_roi, lower_green, upper_green)
        
        red_pixels = cv2.countNonZero(mask_red1) + cv2.countNonZero(mask_red2)
        green_pixels = cv2.countNonZero(mask_green)
        total_pixels = w * h
        
        # Determine Type
        candle_type = "wait"
        
        # Threshold: meaningful amount of color
        if green_pixels > total_pixels * 0.2:
            candle_type = "bullish"
        elif red_pixels > total_pixels * 0.2:
            candle_type = "bearish"
        else:
            # If neither, it might be a grey doji or noise
            # Skip noise
            continue
            
        # Conflict resolution (if both present, take winner)
        if candle_type == "bullish" and red_pixels > green_pixels:
            candle_type = "bearish"
        elif candle_type == "bearish" and green_pixels > red_pixels:
             candle_type = "bullish"

        candles.append({
            "x": x,
            "y": y,
            "total_height": h,
            "body_width": w,
            "type": candle_type,
            # Debug color (just for show)
            "color_stats": {"g": green_pixels, "r": red_pixels}
        })

    return candles

def refine_candle_data(candles):
    """
    Post-processing to normalize data and maybe calculate wick ratios if better data available.
    For Phase 1 MVP, we stick to the bounding box heuristics.
    """
    # Filter only relevant candles (e.g., similar width) to remove noise
    if not candles:
        return []
        
    # Heuristic: valid candles usually have similar widths
    widths = [c['body_width'] for c in candles]
    median_width = np.median(widths)
    
    valid_candles = []
    for c in candles:
        # Allow some variance
        if 0.5 * median_width <= c['body_width'] <= 2.0 * median_width:
             valid_candles.append(c)
             
    return valid_candles
