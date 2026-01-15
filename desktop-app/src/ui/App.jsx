import React, { useState, useEffect } from 'react';
import './App.css';
const { ipcRenderer } = window.require('electron');

// Simple Toast Component
const Toast = ({ message, type }) => {
    if (!message) return null;
    return (
        <div className="toast-container">
            <div className={`toast ${type}`}>
                <span>{message}</span>
            </div>
        </div>
    );
};

function App() {
    // State
    const [signal, setSignal] = useState('WAIT');
    const [confidence, setConfidence] = useState('');
    const [reason, setReason] = useState('Initialize...');
    const [context, setContext] = useState({ symbol: '---', timeframe: '--' });
    const [tradeSetup, setTradeSetup] = useState(null);

    const [isScanning, setIsScanning] = useState(false);
    const [toast, setToast] = useState({ message: null, type: 'info' });
    const [status, setStatus] = useState('paused'); // paused, scanning, error
    const [forceScan, setForceScan] = useState(false);

    const showToast = (msg, type = 'info', duration = 3000) => {
        setToast({ message: msg, type });
        setTimeout(() => setToast({ message: null, type: 'info' }), duration);
    };

    useEffect(() => {
        const handleSignalUpdate = (event, data) => {
            // Check for INFO (special non-trading signal)
            if (data.signal === 'INFO') {
                setSignal('PAUSED');
                setReason(data.reason);
                if (data.context) setContext(data.context);
                return;
            }

            if (data.signal === 'ERROR') {
                setStatus('error');
                showToast(data.reason, 'error');
                return;
            }

            // Normal Signal
            setSignal(data.signal);
            setConfidence(data.confidence);
            setReason(data.reason);
            setStatus('scanning');

            if (data.context) setContext(data.context);
            if (data.trade_setup) setTradeSetup(data.trade_setup);
            else setTradeSetup(null);
        };

        ipcRenderer.on('signal-update', handleSignalUpdate);

        return () => {
            ipcRenderer.removeListener('signal-update', handleSignalUpdate);
        };
    }, []);

    const toggleScan = () => {
        if (isScanning) {
            ipcRenderer.send('stop-scanning');
            setIsScanning(false);
            setSignal('WAIT');
            setReason('Paused');
            setStatus('paused');
            showToast('Scanning Stopped', 'info');
        } else {
            // Start
            ipcRenderer.send('start-scanning', { x: 0, y: 0, w: 1920, h: 1080 });
            // Sync force scan state
            ipcRenderer.send('send-command', { action: 'set_force_scan', value: forceScan });

            setIsScanning(true);
            setReason('Connecting to engine...');
            setStatus('scanning');
            showToast('Scanning Started', 'info');
        }
    };

    const toggleForceScan = (val) => {
        setForceScan(val);
        if (isScanning) {
            ipcRenderer.send('send-command', { action: 'set_force_scan', value: val });
            showToast(val ? 'Force Scan Enabled' : 'Force Scan Disabled', 'info', 1500);
        }
    };

    // Derived styles
    const containerClass = `app-container ${signal.toLowerCase()}`;

    const renderSignal = () => {
        if (signal === 'INFO') return 'INFO';
        if (signal === 'WAIT') return 'ANALYZING';
        return signal; // BUY / SELL
    };

    return (
        <div className={containerClass}>
            {/* Header */}
            <div className="header">
                <div className="logo-area">
                    <span>AI Assistant Pro</span>
                </div>
                <div className={`status-badge ${status}`}>
                    {status}
                </div>
            </div>

            {/* Main Content */}
            <div className="main-content">

                {/* 1. Context Bar */}
                {isScanning && (
                    <div className="context-bar">
                        <div className="context-item">
                            <span className="label">ASSET</span>
                            <span className="value">{context.symbol || '---'}</span>
                        </div>
                        <div className="context-item">
                            <span className="label">TF</span>
                            <span className="value">{context.timeframe || '--'}</span>
                        </div>
                        <div className="context-item">
                            <span className="label">HEALTH</span>
                            <span className={`value ${tradeSetup?.volatility?.includes('High') ? 'warn' : 'good'}`}>
                                {tradeSetup?.volatility ? tradeSetup.volatility.split(' ')[0] : '---'}
                            </span>
                        </div>
                    </div>
                )}

                {/* 2. Main Signal */}
                <div className="signal-display">
                    <div className={`signal-text ${signal.toLowerCase()}`}>
                        {renderSignal()}
                    </div>
                    {signal !== 'WAIT' && signal !== 'INFO' && (
                        <div className="confidence-pill">{confidence} CONFIDENCE</div>
                    )}
                </div>

                {/* 3. Trade Setup Grid */}
                {isScanning && tradeSetup && signal !== 'WAIT' && signal !== 'INFO' && (
                    <div className="trade-grid">
                        <div className="trade-box entry">
                            <span className="box-label">ENTRY</span>
                            <span className="box-value">{tradeSetup.entry}</span>
                        </div>
                        <div className="trade-box sl">
                            <span className="box-label">STOP LOSS</span>
                            <span className="box-value">{tradeSetup.sl}</span>
                        </div>
                        <div className="trade-box tp">
                            <span className="box-label">TARGET</span>
                            <span className="box-value">{tradeSetup.tp}</span>
                        </div>
                    </div>
                )}

                {/* 4. Analysis / Commentary */}
                <div className="reason-text">
                    {tradeSetup?.commentary || reason}
                </div>
            </div>

            {/* Toast Notification Layer */}
            <Toast message={toast.message} type={toast.type} />

            {/* Footer */}
            <div className="footer">
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '10px' }}>

                    <button
                        className={`control-btn ${isScanning ? 'stop' : 'start'}`}
                        onClick={toggleScan}
                    >
                        {isScanning ? 'STOP AI' : 'ACTIVATE AI'}
                    </button>

                    <label className="force-scan-toggle">
                        <input
                            type="checkbox"
                            checked={forceScan}
                            onChange={(e) => toggleForceScan(e.target.checked)}
                        />
                        <span>Force Scan (Override)</span>
                    </label>
                </div>
            </div>
        </div>
    );
}

export default App;
