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

    return img, closed, gray
