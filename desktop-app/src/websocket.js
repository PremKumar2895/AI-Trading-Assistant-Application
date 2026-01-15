const WebSocket = require('ws');

let ws;
let onSignalCallback = null;

function connectWebSocket() {
    ws = new WebSocket('ws://127.0.0.1:8000/ws');

    ws.on('open', () => {
        console.log('Connected to Python Engine');
    });

    ws.on('message', (data) => {
        try {
            const jsonData = JSON.parse(data);
            if (onSignalCallback) {
                onSignalCallback(jsonData);
            }
        } catch (e) {
            console.error('Error parsing WS message:', e);
        }
    });

    ws.on('error', (err) => {
        console.error('WebSocket error:', err);
    });

    ws.on('close', () => {
        console.log('Disconnected from Python Engine. Reconnecting in 3s...');
        setTimeout(connectWebSocket, 3000);
    });
}

function sendFrame(imageBuffer) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(imageBuffer);
    }
}

function onSignalReceived(callback) {
    onSignalCallback = callback;
}

module.exports = {
    connectWebSocket,
    sendFrame,
    onSignalReceived
};
