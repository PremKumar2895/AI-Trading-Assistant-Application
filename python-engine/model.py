"""
Trade direction model + probability calibration.

Predicts P(up) from the feature vector. Primary backend = sklearn
GradientBoosting + IsotonicRegression calibration; pure-numpy logistic regression
fallback if sklearn is unavailable, so training/inference never hard-fail.

The model is intentionally conservative about its own worth: training records an
out-of-sample EV-backtest verdict (`eligible`). The decision engine only lets the
model *elevate* a signal when `eligible` is True (it beat the payout on unseen data).
"""
import os
import pickle

import numpy as np

from features import FEATURE_NAMES

ARTIFACT = os.path.join(os.path.dirname(__file__), "model_store", "trade_model.pkl")

try:
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.isotonic import IsotonicRegression
    _HAVE_SKLEARN = True
except ImportError:  # pragma: no cover
    _HAVE_SKLEARN = False


class _LogisticFallback:
    """Standardised logistic regression (numpy) — used only if sklearn is missing."""

    def __init__(self, lr=0.1, epochs=400, l2=1e-3):
        self.lr, self.epochs, self.l2 = lr, epochs, l2

    def fit(self, X, y):
        self.mu = X.mean(0)
        self.sd = X.std(0) + 1e-9
        Xs = (X - self.mu) / self.sd
        n, d = Xs.shape
        self.w = np.zeros(d)
        self.b = 0.0
        for _ in range(self.epochs):
            z = Xs @ self.w + self.b
            p = 1 / (1 + np.exp(-z))
            g = p - y
            self.w -= self.lr * (Xs.T @ g / n + self.l2 * self.w)
            self.b -= self.lr * g.mean()
        return self

    def predict_proba(self, X):
        Xs = (X - self.mu) / self.sd
        p = 1 / (1 + np.exp(-(Xs @ self.w + self.b)))
        return np.column_stack([1 - p, p])


class TradeModel:
    def __init__(self):
        self.clf = None
        self.iso = None
        self.feature_names = list(FEATURE_NAMES)
        self.metrics = {}
        self.eligible = False

    # ---- training ----
    def fit(self, X, y):
        if _HAVE_SKLEARN:
            self.clf = GradientBoostingClassifier(
                n_estimators=200, max_depth=3, learning_rate=0.05, subsample=0.8
            )
        else:
            self.clf = _LogisticFallback()
        self.clf.fit(X, y)
        return self

    def calibrate(self, X_val, y_val):
        raw = self._raw_proba(X_val)
        if _HAVE_SKLEARN:
            self.iso = IsotonicRegression(out_of_bounds="clip")
            self.iso.fit(raw, y_val)
        return self

    # ---- inference ----
    def _raw_proba(self, X):
        return self.clf.predict_proba(np.asarray(X, dtype=float))[:, 1]

    def proba_up(self, X):
        raw = self._raw_proba(X)
        if self.iso is not None:
            return self.iso.predict(raw)
        return raw

    # ---- persistence ----
    def save(self, path=ARTIFACT):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            pickle.dump(
                {
                    "clf": self.clf, "iso": self.iso,
                    "feature_names": self.feature_names,
                    "metrics": self.metrics, "eligible": self.eligible,
                    "have_sklearn": _HAVE_SKLEARN,
                },
                fh,
            )
        return path

    @classmethod
    def load(cls, path=ARTIFACT):
        if not os.path.exists(path):
            return None
        try:
            with open(path, "rb") as fh:
                d = pickle.load(fh)
            m = cls()
            m.clf = d["clf"]
            m.iso = d["iso"]
            m.feature_names = d["feature_names"]
            m.metrics = d.get("metrics", {})
            m.eligible = d.get("eligible", False)
            return m
        except Exception as e:  # pragma: no cover
            print(f"Model load error: {e}")
            return None
