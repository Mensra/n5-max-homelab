#!/usr/bin/env python3
# decode_capture.py FILE.pcap CUBE_IP  -> one line per iPad-to-cube message (UDP broadcast 11005 or TCP 9999 to the cube), seconds from the first. Reads classic pcap (router-capture output).
import struct,sys
CUBE=bytes(int(x) for x in (sys.argv[2] if len(sys.argv)>2 else '0.0.0.0').split('.'))   # the cube's IPv4 address, as the second argument
d=open(sys.argv[1],'rb').read();m=struct.unpack('<I',d[:4])[0];e='<' if m in(0xa1b2c3d4,0xa1b23c4d) else '>'
o=24;t0=None
while o+16<=len(d):
    s,us,cl,ol=struct.unpack(e+'IIII',d[o:o+16]);p=d[o+16:o+16+cl];o+=16+cl
    if len(p)<42 or p[12:14]!=b'\x08\x00': continue
    ihl=(p[14]&15)*4;pr=p[23];u=p[14+ihl:];pl=None
    if pr==17:
        sp,dp,ln=struct.unpack('>HHH',u[:6])
        if dp==11005: pl=u[8:ln]
    elif pr==6 and p[30:34]==CUBE:
        dp=struct.unpack('>H',u[2:4])[0];off=(u[12]>>4)*4
        if dp==9999 and len(u)>off: pl=u[off:]
    if pl:
        t=s+us/1e6;t0=t0 or t;print("%6.1f %3dB %s"%(t-t0,len(pl),pl.hex()))
