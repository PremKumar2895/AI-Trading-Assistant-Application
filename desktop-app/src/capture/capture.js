const { desktopCapturer } = require('electron');

let captureInterval = null;
let currentRegion = null; // {x, y, w, h}
const INTERVAL_MS = 600; // ~1.5 FPS

function setCaptureRegion(region) {
    currentRegion = region;
}

function startCaptureLoop(onFrameCallback) {
    if (captureInterval) return;

    captureInterval = setInterval(async () => {
        try {
            // Get sources - usually 'screen' type. 
            // We just grab the primary display for now.
            const sources = await desktopCapturer.getSources({
                types: ['screen'],
                thumbnailSize: { width: 1920, height: 1080 } // Request reasonable size
            });

            if (sources.length > 0) {
                const source = sources[0]; // Primary screen
                const image = source.thumbnail;

                // If we ever need cropping, Electron's NativeImage has crop(rect)
                // rect = {x, y, width, height}
                // However, the coordinates must be relative to the image.

                let finalImage = image;

                // Simple check if we have a valid region to crop
                if (currentRegion) {
                    // Note: This assumes the region coordinates match the screen coordinates 
                    // and the screenshot captured is the full screen 0,0.
                    // This often requires more math with multiple monitors, but for MVP:
                    try {
                        const cropRect = {
                            x: Math.floor(currentRegion.x),
                            y: Math.floor(currentRegion.y),
                            width: Math.floor(currentRegion.w),
                            height: Math.floor(currentRegion.h)
                        };
                        // Ensure bounds are valid
                        if (cropRect.width > 0 && cropRect.height > 0) {
                            finalImage = image.crop(cropRect);
                        }
                    } catch (cropErr) {
                        console.error("Crop error:", cropErr);
                    }
                }

                // Convert to JPEG buffer
                const imgBuffer = finalImage.toJPEG(80);
                onFrameCallback(imgBuffer);
            }

        } catch (err) {
            console.error("Capture failed:", err);
        }
    }, INTERVAL_MS);
}

function stopCaptureLoop() {
    if (captureInterval) {
        clearInterval(captureInterval);
        captureInterval = null;
    }
}

module.exports = {
    startCaptureLoop,
    stopCaptureLoop,
    setCaptureRegion
};
