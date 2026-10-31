#!/usr/bin/env python3
"""Ducking test across two UCA222 boxes: tone from card 3, record and play on card 2.

Swap the hw: numbers to test the other box. Usage: uca222_ducking.py SCRATCH_FOLDER
"""
import subprocess,time,wave,numpy as np,sys
S=sys.argv[1]; R=48000; SEG=3.0
def wr(p,a,ch):
    f=wave.open(p,'wb');f.setnchannels(ch);f.setsampwidth(2);f.setframerate(R)
    f.writeframes((a*32767).astype(np.int16).tobytes());f.close()
names=['silent','L','silent','R','silent','both','silent']
T=len(names)*SEG; n=int(SEG*R); t=np.arange(n)/R
tone=10**(-6/20)*np.sin(2*np.pi*5000*t)
own=[]
for s in names:
    a=np.zeros((n,2))
    if s in('L','both'):a[:,0]=tone
    if s in('R','both'):a[:,1]=tone
    own.append(a)
wr(f'{S}/own.wav',np.vstack(own),2)
tt=np.arange(int((T+3)*R))/R
far=np.zeros((tt.size,2)); far[:,0]=10**(-20/20)*np.sin(2*np.pi*1000*tt)
wr(f'{S}/far.wav',far,2)
p3=subprocess.Popen(['aplay','-q','-D','hw:3,0',f'{S}/far.wav'])
time.sleep(.5)
rec=subprocess.Popen(['arecord','-q','-D','hw:2,0','-f','S16_LE','-r','48000','-c','2','-d',str(int(T+2)),f'{S}/rec.wav'])
time.sleep(.5)
p2=subprocess.run(['aplay','-q','-D','hw:2,0',f'{S}/own.wav'])
rec.wait(); p3.wait()
print('aplay own rc',p2.returncode,'rec rc',rec.returncode,'far rc',p3.returncode)
f=wave.open(f'{S}/rec.wav');x=np.frombuffer(f.readframes(f.getnframes()),dtype=np.int16).reshape(-1,2).astype(float)/32768
def lvl(y,hz):
    w=np.hanning(len(y));c=np.sum(y*w*np.exp(-2j*np.pi*hz*np.arange(len(y))/R))
    return 20*np.log10(max(2*abs(c)/w.sum(),1e-7))
s0=.5
print('seg      | L in 1k  5k | R in 1k  5k | L in 1k min/max over 100 ms blocks')
for i,s in enumerate(names):
    a=int((s0+i*SEG+.4)*R);b=int((s0+(i+1)*SEG-.4)*R)
    A=x[a:b,0];B=x[a:b,1]
    k=4800;bl=[lvl(x[j:j+k,0],1000) for j in range(int((s0+i*SEG)*R),int((s0+(i+1)*SEG))*R-k,k)]
    print(f'{s:8s} | {lvl(A,1000):7.2f} {lvl(A,5000):7.2f} | {lvl(B,1000):7.2f} {lvl(B,5000):7.2f} | {min(bl):.2f} / {max(bl):.2f}')
print('peak L',20*np.log10(abs(x[:,0]).max()),'peak R',20*np.log10(max(abs(x[:,1]).max(),1e-7)))
