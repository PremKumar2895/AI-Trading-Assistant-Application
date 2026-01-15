import React, { useState, useEffect } from 'react';
import './App.css';
const { ipcRenderer } = window.require('electron');

function App() {
    const [signal, setSignal] = useState('WAIT');
    const [confidence, setConfidence] = useState('');
    const [reason, setReason] = useState('Waiting to start...');
    const [isScanning, setIsScanning] = useState(false);

    useEffect(() => {
        ipcRenderer.on('signal-update', (event, data) => {
            setSignal(data.signal);
            setConfidence(data.confidence);
            setReason(data.reason);
        });

        return () => {
            ipcRenderer.removeAllListeners('signal-update');
        };
    }, []);

    const toggleScan = () => {
        if (isScanning) {
            ipcRenderer.send('stop-scanning');
            setIsScanning(false);
            setSignal('WAIT');
            setReason('Paused');
        } else {
            // For MVP, passing a dummy region or implementation detail
            // In a real app, we'd have a UI to select region.
            // Here we assume Python crops or we just send full screen.
            ipcRenderer.send('start-scanning', { x: 0, y: 0, w: 1920, h: 1080 });
            setIsScanning(true);
            setReason('Scanning...');
        }
    };

    const getSignalColor = () => {
        switch (signal) {
            case 'BUY': return '#4CAF50'; // Green
            case 'SELL': return '#F44336'; // Red
            default: return '#9E9E9E'; // Grey
        }
    };

    return (
        <div style={{
            backgroundColor: '#1e1e1e',
            color: 'white',
            height: '100vh',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            border: `4px solid ${getSignalColor()}`,
            borderRadius: '10px',
            fontFamily: 'Segoe UI, sans-serif'
        }}>
            <div style={{ fontSize: '48px', fontWeight: 'bold', color: getSignalColor() }}>
                {signal}
            </div>

            {confidence && confidence !== 'LOW' && (
                <div style={{ fontSize: '18px', marginBottom: '10px', color: '#ccc' }}>
                    Confidence: {confidence}
                </div>
            )}

            <div style={{ fontSize: '14px', textAlign: 'center', padding: '0 20px', color: '#888' }}>
                {reason}
            </div>

            <button
                onClick={toggleScan}
                style={{
                    marginTop: '30px',
                    padding: '10px 20px',
                    fontSize: '16px',
                    backgroundColor: isScanning ? '#d32f2f' : '#2196F3',
                    color: 'white',
                    border: 'none',
                    borderRadius: '5px',
                    cursor: 'pointer',
                    WebkitAppRegion: 'no-drag'
                }}
            >
                {isScanning ? 'STOP' : 'START'}
            </button>

            <div style={{ marginTop: '20px', fontSize: '10px', color: '#555' }}>
                Phase-1 AI Assistant
            </div>
        </div>
    );
}

export default App;
