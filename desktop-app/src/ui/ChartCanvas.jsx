import React, { useRef, useEffect } from 'react';

/**
 * Annotated prediction chart drawn on a crisp <canvas>.
 * Renders candles, EMA(9/21/50), support/resistance, and a forward projection
 * arrow in the signal's direction. No chart library — keeps the bundle tiny.
 */
const COLORS = {
    up: '#00E676', down: '#FF5252', ema9: '#42A5F5', ema21: '#AB47BC',
    ema50: '#FFA726', sup: '#00E676', res: '#FF5252', grid: 'rgba(255,255,255,0.06)',
    axis: 'rgba(255,255,255,0.35)', proj: '#FFD54F',
};

function ChartCanvas({ data }) {
    const ref = useRef(null);

    useEffect(() => {
        const canvas = ref.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const cssW = canvas.clientWidth || 352;
        const cssH = canvas.clientHeight || 150;
        const dpr = window.devicePixelRatio || 1;
        canvas.width = cssW * dpr;
        canvas.height = cssH * dpr;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, cssW, cssH);

        if (!data || !data.candles || data.candles.length < 2) {
            ctx.fillStyle = 'rgba(255,255,255,0.3)';
            ctx.font = '11px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('Waiting for chart data…', cssW / 2, cssH / 2);
            return;
        }

        const candles = data.candles;
        const proj = data.projection || [];
        const padL = 6, padR = 44, padT = 8, padB = 8;
        const plotW = cssW - padL - padR;
        const plotH = cssH - padT - padB;
        const slots = candles.length + proj.length + 1;
        const cw = plotW / slots;

        // price range across everything visible
        let lo = Infinity, hi = -Infinity;
        const consider = (v) => { if (v != null && isFinite(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); } };
        candles.forEach((c) => { consider(c.h); consider(c.l); });
        [...data.ema9, ...data.ema21, ...data.ema50, ...proj].forEach(consider);
        consider(data.support); consider(data.resistance);
        if (!isFinite(lo) || !isFinite(hi) || hi === lo) { hi = lo + 1; }
        const pad = (hi - lo) * 0.08;
        lo -= pad; hi += pad;

        const x = (i) => padL + i * cw + cw / 2;
        const y = (p) => padT + (1 - (p - lo) / (hi - lo)) * plotH;

        // horizontal grid
        ctx.strokeStyle = COLORS.grid; ctx.lineWidth = 1;
        for (let g = 0; g <= 4; g++) {
            const gy = padT + (plotH * g) / 4;
            ctx.beginPath(); ctx.moveTo(padL, gy); ctx.lineTo(cssW - padR, gy); ctx.stroke();
        }

        // support / resistance
        const hline = (price, color, label) => {
            if (price == null || !isFinite(price)) return;
            const ly = y(price);
            ctx.strokeStyle = color; ctx.lineWidth = 1; ctx.setLineDash([4, 3]);
            ctx.beginPath(); ctx.moveTo(padL, ly); ctx.lineTo(cssW - padR, ly); ctx.stroke();
            ctx.setLineDash([]);
            ctx.fillStyle = color; ctx.font = '9px sans-serif'; ctx.textAlign = 'left';
            ctx.fillText(`${label} ${price}`, cssW - padR + 2, ly + 3);
        };
        hline(data.resistance, COLORS.res, 'R');
        hline(data.support, COLORS.sup, 'S');

        // candles
        candles.forEach((c, i) => {
            const up = c.c >= c.o;
            const col = up ? COLORS.up : COLORS.down;
            const cx = x(i);
            ctx.strokeStyle = col; ctx.lineWidth = 1;
            ctx.beginPath(); ctx.moveTo(cx, y(c.h)); ctx.lineTo(cx, y(c.l)); ctx.stroke();
            const bw = Math.max(1.5, cw * 0.6);
            const yo = y(c.o), yc = y(c.c);
            ctx.fillStyle = col;
            ctx.fillRect(cx - bw / 2, Math.min(yo, yc), bw, Math.max(1, Math.abs(yc - yo)));
        });

        // EMA polylines
        const poly = (arr, color) => {
            ctx.strokeStyle = color; ctx.lineWidth = 1.2; ctx.beginPath();
            let started = false;
            arr.forEach((v, i) => {
                if (v == null || !isFinite(v)) return;
                const px = x(i), py = y(v);
                if (!started) { ctx.moveTo(px, py); started = true; } else ctx.lineTo(px, py);
            });
            ctx.stroke();
        };
        poly(data.ema9, COLORS.ema9);
        poly(data.ema21, COLORS.ema21);
        poly(data.ema50, COLORS.ema50);

        // projection arrow (prediction)
        if (proj.length) {
            const startI = candles.length - 1;
            const startX = x(startI), startY = y(candles[candles.length - 1].c);
            ctx.strokeStyle = COLORS.proj; ctx.lineWidth = 1.8; ctx.setLineDash([5, 3]);
            ctx.beginPath(); ctx.moveTo(startX, startY);
            let lastX = startX, lastY = startY;
            proj.forEach((v, k) => {
                const px = x(candles.length + k), py = y(v);
                ctx.lineTo(px, py); lastX = px; lastY = py;
            });
            ctx.stroke(); ctx.setLineDash([]);
            // arrowhead
            const prevX = x(candles.length + proj.length - 2);
            const prevY = y(proj[proj.length - 2] ?? candles[candles.length - 1].c);
            const ang = Math.atan2(lastY - prevY, lastX - prevX);
            ctx.fillStyle = COLORS.proj;
            ctx.beginPath();
            ctx.moveTo(lastX, lastY);
            ctx.lineTo(lastX - 7 * Math.cos(ang - 0.4), lastY - 7 * Math.sin(ang - 0.4));
            ctx.lineTo(lastX - 7 * Math.cos(ang + 0.4), lastY - 7 * Math.sin(ang + 0.4));
            ctx.closePath(); ctx.fill();
        }
    }, [data]);

    return (
        <div className="chart-wrap">
            <canvas ref={ref} className="pred-chart" />
            <div className="chart-legend">
                <span style={{ color: COLORS.ema9 }}>EMA9</span>
                <span style={{ color: COLORS.ema21 }}>EMA21</span>
                <span style={{ color: COLORS.ema50 }}>EMA50</span>
                <span style={{ color: COLORS.proj }}>prediction →</span>
            </div>
        </div>
    );
}

export default ChartCanvas;
