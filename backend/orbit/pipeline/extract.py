"""Magnitude, level and direction extraction for a single report."""

import re

from .lexicon import CAPS, DOWN, NUM_BPS, NUM_PCT, NUM_PCTPT, UP, VISA_EASE, VISA_TIGHT


def extract_magnitude(text, det):
    t = text.lower()
    unit = det['unit']
    var = det['var']
    if det.get('index'):
        return float(abs(det['default'])), False
    cap = CAPS.get(var, 60)

    def ok(v):
        return 0 < v <= cap

    if var == 'rupee':
        m = re.search(r'(\d{1,3})\s*paise', t)
        if m:
            return round(float(m.group(1)) / 90, 2), True
        m = re.search(r'rupee[^.%]{0,40}?(\d+(?:\.\d+)?)\s*%', t)
        if m and float(m.group(1)) <= 15:
            return float(m.group(1)), True
        return float(det['default']), False
    if var == 'fuel_price':
        lpg = re.search(r'(lpg|cylinder)', t) is not None
        m = re.search(
            r'(?:costlier|cheaper|hike[d]?|cut|increase[d]?|reduce[d]?|rise|fell|rose|up|down|by|of)\s*(?:by\s*)?₹\s?(\d+(?:\.\d+)?)',
            t,
        ) or re.search(r'₹\s?(\d+(?:\.\d+)?)\s*(?:per litre|per liter|a litre|/litre|/l\b|per cylinder|a cylinder)', t)
        if m:
            v = float(m.group(1))
            if lpg and v <= 400:
                return round(v / 850 * 100, 1), True
            if not lpg and v <= 30:
                return round(v / 100 * 100, 1), True
        m = re.search(r'(petrol|diesel|lpg|cng|png|atf|jet fuel)[^.]{0,60}?(\d+(?:\.\d+)?)\s*%', t)
        if m and float(m.group(2)) <= 30:
            return float(m.group(2)), True
        return float(det['default']), False
    windows = [t[max(0, m.start() - 90) : m.end() + 110] for m in re.finditer(det['subject'], t)]
    for w in windows:
        if unit == 'bps':
            m = [float(x) for x in re.findall(NUM_BPS, w) if ok(float(x))]
            if m:
                return m[0], True
            for x in re.findall(r'(\d(?:\.\d+)?)\s*%', w):
                if 0 < float(x) <= 1:
                    return float(x) * 100, True
        elif unit == '%':
            vals = [float(x) for x in re.findall(NUM_PCT, w) if ok(float(x))]
            if vals:
                return vals[0], True
        else:
            vals = [float(x) for x in re.findall(NUM_PCTPT, w) if ok(float(x))]
            if vals:
                return vals[0], True
    return float(abs(det['default'])), False


def extract_level(text, var):
    t = text.lower()
    if var == 'crude':
        m = re.search(r'\$\s?(\d{2,3})(?:\.\d+)?(?:\s*(?:per|a)\s*barrel)?', t)
        if m:
            return '$' + m.group(1) + ' a barrel'
    if var == 'rupee':
        m = re.search(r'\b(8\d|9\d|10\d)(\.\d{1,2})?\b(?=[^%]*(dollar|usd|record|close|closed|open|level|mark))', t)
        if m:
            return m.group(1) + (m.group(2) or '') + ' per dollar'
    if var == 'fuel_price' and not re.search(r'(lpg|cylinder|cng|png)', t):
        m = re.search(r'₹\s?(\d{2,3}(?:\.\d+)?)\s*(?:per litre|per liter|a litre|/litre)', t)
        if m:
            return '₹' + m.group(1) + ' a litre'
    return None


def direction(text, det):
    t = text.lower()
    var = det['var']
    if var == 'visa':
        if re.search(VISA_EASE, t):
            return -1
        if re.search(VISA_TIGHT, t):
            return 1
    best = None
    for m in re.finditer(det['subject'], t):
        window = t[max(0, m.start() - 80) : m.end() + 120]
        up = len(re.findall(r'\b' + UP + r'\b', window))
        down = len(re.findall(r'\b' + DOWN + r'\b', window))
        if up != down:
            best = 1 if up > down else -1
            break
    if best is None:
        up = len(re.findall(r'\b' + UP + r'\b', t))
        down = len(re.findall(r'\b' + DOWN + r'\b', t))
        best = 1 if up > down else -1 if down > up else 0
    return best
