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

        # Aspect ratio check - Candles are generally tall/thin or square-ish, not super wide
        aspect_ratio = float(w) / h
        if aspect_ratio > 5.0: # Ignore very wide things (like trend lines maybe)
            continue
            
        # Extract Region of Interest (ROI) from original color image to determine color
        roi = original_img[y:y+h, x:x+w]
        
        # Determine Color (Bullish vs Bearish)
        # We assume standard Green/Red or White/Black. 
        # Simple heuristic: excessive Green or White is Bullish. Red or Black is Bearish.
        # This is a simplification; users might need to tune specific HSV ranges.
        # For now, let's use a mean color check.
        
        avg_color_per_row = np.average(roi, axis=0)
        avg_color = np.average(avg_color_per_row, axis=0) # BGR
        
        # BGR: Green is [0, 255, 0], Red is [0, 0, 255]
        blue, green, red = avg_color
        
        candle_type = "wait"
        if green > red and green > blue:
            candle_type = "bullish"
        elif red > green and red > blue:
            candle_type = "bearish"
        else:
             # Basic fallback for distinct colors, assuming bright = bullish, dark = bearish if simple BW
            if np.mean(avg_color) > 127: 
                candle_type = "bullish"
            else:
                candle_type = "bearish"

        # Approximate OHLC relative to the candle's bounding box
        # This is strictly visual "body" detection.
        # We can try to separate wicks from body if needed, but for Phase 1, 
        # using the bounding box as the "total range" and estimating body size is safer vs full CV decomposition.
        
        # NOTE: A more advanced CV approach would be to detect the solid block vs the line.
        # Let's try a simple center-column scan to find the solid body vs the wick.
        
        # Center column scan
        center_x = w // 2
        col_slice = roi[:, center_x] # slice of the center vertical line
        # Check non-background pixels in this slice if we had a mask, but we have the raw ROI.
        
        # Simplified for Phase 1: 
        # Total Height = High - Low
        # Body Height = Approx (needs refinement, but let's assume body is the "thick" part)
        
        candles.append({
            "x": x,
            "total_height": h,
            "body_width": w,
            "type": candle_type,
            "color_avg": (int(blue), int(green), int(red))
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
