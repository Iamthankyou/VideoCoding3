
# bdrate.py
# Bjøntegaard Delta-Rate / Delta-PSNR utilities
# Ref: ITU-T Rec. VCEG-M33 (adapted for Python)
import math

def _polyfit(x, y, order=3):
    """Cubic polynomial fit via least squares; returns coefficients (descending power)."""
    import numpy as np
    return np.polyfit(x, y, order)

def _polyval(c, x):
    import numpy as np
    return np.polyval(c, x)

def bd_rate(ref_bitrate, ref_psnr, test_bitrate, test_psnr):
    """
    Compute Bjøntegaard Delta-Rate (%)
    Inputs are sequences of 4 points for the anchor (ref) and test:
        bitrate in kbps (positive), psnr in dB (Y-PSNR recommended).
    Returns: percentage bitrate saving of 'test' vs 'ref' (negative is better).
    """
    import numpy as np
    # Convert to logs for rate
    lR1 = np.log(ref_bitrate)
    lR2 = np.log(test_bitrate)
    P1  = np.array(ref_psnr)
    P2  = np.array(test_psnr)

    # Fit cubic polynomial: log(R) = f(PSNR)
    c1 = _polyfit(P1, lR1, 3)
    c2 = _polyfit(P2, lR2, 3)

    # Integration interval on PSNR axis
    p_min = max(min(P1), min(P2))
    p_max = min(max(P1), max(P2))
    if p_max <= p_min:
        raise ValueError("PSNR ranges do not overlap; cannot compute BD-Rate.")

    # Integrate exp(f(psnr)) over [p_min, p_max]
    # Integral of log(rate) polynomials, then exponentiate the average of log-rates
    # Analytical integral of polynomial is straightforward with numpy.polyint
    import numpy as np
    polyint1 = np.polyint(c1)
    polyint2 = np.polyint(c2)

    int1 = np.polyval(polyint1, p_max) - np.polyval(polyint1, p_min)
    int2 = np.polyval(polyint2, p_max) - np.polyval(polyint2, p_min)

    avg_exp1 = (int1 / (p_max - p_min))
    avg_exp2 = (int2 / (p_max - p_min))

    # Convert back from log domain to linear domain: average rate
    avg_rate1 = np.exp(avg_exp1)
    avg_rate2 = np.exp(avg_exp2)

    # Percentage difference
    bd = (avg_rate2 / avg_rate1 - 1.0) * 100.0
    return float(bd)

def bd_psnr(ref_bitrate, ref_psnr, test_bitrate, test_psnr):
    """
    Compute Bjøntegaard Delta-PSNR (dB)
    Fit PSNR=f(log(Rate)) and integrate over common log-rate interval.
    """
    import numpy as np
    lR1 = np.log(ref_bitrate)
    lR2 = np.log(test_bitrate)
    P1  = np.array(ref_psnr)
    P2  = np.array(test_psnr)

    # Fit PSNR = f(log(R))
    c1 = _polyfit(lR1, P1, 3)
    c2 = _polyfit(lR2, P2, 3)

    r_min = max(min(lR1), min(lR2))
    r_max = min(max(lR1), max(lR2))
    if r_max <= r_min:
        raise ValueError("Rate ranges do not overlap; cannot compute BD-PSNR.")

    import numpy as np
    polyint1 = np.polyint(c1)
    polyint2 = np.polyint(c2)

    int1 = np.polyval(polyint1, r_max) - np.polyval(polyint1, r_min)
    int2 = np.polyval(polyint2, r_max) - np.polyval(polyint2, r_min)

    avg1 = int1 / (r_max - r_min)
    avg2 = int2 / (r_max - r_min)

    return float(avg2 - avg1)
