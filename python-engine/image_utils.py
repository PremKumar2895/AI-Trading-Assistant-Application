import cv2
import numpy as np

def preprocess_image(image_bytes):
    """
    Decodes and preprocesses the image for candle detection.
    Steps: Grayscale -> Gaussian Blur -> Canny Edge -> Binary Threshold/Morph
    """
    # 1. Convert bytes to numpy array
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
        raise ValueError("Failed to decode image")

    # 2. Grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 3. Gaussian Blur (reduce noise)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # 4. Canny Edge Detection
    # Thresholds might need tuning based on chart style (dark/light mode)
    edges = cv2.Canny(blurred, 50, 150)

    # 5. Morphological operations (Optional - closes gaps in edges)
    kernel = np.ones((3, 3), np.uint8)
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)

    # 6. Invert Grayscale (for OCR on dark themes)
    inverted_gray = cv2.bitwise_not(gray)

    return img, closed, gray, inverted_gray

def mask_overlay(image, x, y, w, h):
    """
    Draws a black rectangle over the specified region to hide the overlay from CV/OCR.
    """
    try:
        # Ensure integer coordinates
        x, y, w, h = int(x), int(y), int(w), int(h)
        # Draw filled black rectangle
        # (check dimensions to avoid error, though cv2 usually handles clipping)
        cv2.rectangle(image, (x, y), (x + w, y + h), (0, 0, 0), -1)
    except Exception as e:
        print(f"Masking error: {e}")
    return image
