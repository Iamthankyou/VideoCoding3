import numpy as np
def _polyfit(x,y,o=3): return np.polyfit(x,y,o)
def bd_rate(R1,P1,R2,P2):
    lR1=np.log(np.array(R1)); lR2=np.log(np.array(R2)); P1=np.array(P1); P2=np.array(P2)
    c1=_polyfit(P1,lR1,3); c2=_polyfit(P2,lR2,3)
    pmin=max(min(P1),min(P2)); pmax=min(max(P1),max(P2))
    if pmax<=pmin: raise ValueError("PSNR ranges do not overlap.")
    pi1=np.polyint(c1); pi2=np.polyint(c2)
    a1=np.polyval(pi1,pmax)-np.polyval(pi1,pmin)
    a2=np.polyval(pi2,pmax)-np.polyval(pi2,pmin)
    avg1=a1/(pmax-pmin); avg2=a2/(pmax-pmin)
    return float((np.exp(avg2)/np.exp(avg1)-1.0)*100.0)
