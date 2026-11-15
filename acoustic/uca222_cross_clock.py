#!/usr/bin/env python3
"""Clock difference between two UCA222 boxes, cross-wired, with 1 kHz tones.

Box 1 is hw:2, box 2 is hw:3. Usage: uca222_cross_clock.py SCRATCH_FOLDER
"""
import subprocess,time,wave,numpy as np,sys
S=sys.argv[1]; R=48000; SECS=300
def wr(p,ch_idx):
    per=(0.1*32767*np.sin(2*np.pi*np.arange(48)/48)).astype(np.int16)
    fr=np.zeros((48,2),dtype=np.int16); fr[:,ch_idx]=per
    f=wave.open(p,'wb');f.setnchannels(2);f.setsampwidth(2);f.setframerate(R)
    b=fr.tobytes()
    for _ in range(int((SECS+15)*1000)//1000*1000): f.writeframes(b)
    f.close()
wr(f'{S}/box1out.wav',1); wr(f'{S}/box2out.wav',0)
ps=[subprocess.Popen(['aplay','-D','hw:2,0',f'{S}/box1out.wav'],stderr=subprocess.PIPE,text=True),
    subprocess.Popen(['aplay','-D','hw:3,0',f'{S}/box2out.wav'],stderr=subprocess.PIPE,text=True)]
time.sleep(1)
rs=[subprocess.Popen(['arecord','-D','hw:2,0','-f','S16_LE','-r','48000','-c','2','-d',str(SECS),f'{S}/box1in.wav'],stderr=subprocess.PIPE,text=True),
    subprocess.Popen(['arecord','-D','hw:3,0','-f','S16_LE','-r','48000','-c','2','-d',str(SECS),f'{S}/box2in.wav'],stderr=subprocess.PIPE,text=True)]
for r in rs: print('arecord rc',r.wait(),[l for l in r.stderr.read().splitlines() if 'Recording' not in l][:5])
for p in ps: p.terminate()
def ana(path,c,name):
    f=wave.open(path);x=np.frombuffer(f.readframes(f.getnframes()),dtype=np.int16).reshape(-1,2).astype(float)
    print(name,'secs',len(x)/R,'peak other ch LSB',abs(x[:,1-c]).max())
    y=x[:,c]
    n=len(y)//R; t=np.arange(R)/R; w=np.hanning(R); lo=w*np.exp(-2j*np.pi*1000*t)
    ph=np.array([np.sum(y[i*R:(i+1)*R]*lo) for i in range(n)])
    amp=20*np.log10(2*abs(ph)/w.sum()/32768)
    p=np.unwrap(np.angle(ph));tt=np.arange(n)
    good=tt>=2
    a,b=np.polyfit(tt[good],p[good],1)
    ppm=a/(2*np.pi*1000)*1e6
    res=p-np.polyval([a,b],tt)
    us=res[good]/(2*np.pi*1000)*1e6
    jump=np.abs(np.diff(p[good])-a).max()/(2*np.pi*1000)*1e6
    q=len(tt[good])//2
    a1=np.polyfit(tt[good][:q],p[good][:q],1)[0]/(2*np.pi*1000)*1e6
    a2=np.polyfit(tt[good][q:],p[good][q:],1)[0]/(2*np.pi*1000)*1e6
    print(f'  amp {amp[good].min():.2f}..{amp[good].max():.2f} dBFS; sender vs receiver clock {ppm:+.3f} ppm (1st half {a1:+.3f}, 2nd {a2:+.3f}); residual {us.std():.2f} us rms, worst {abs(us).max():.2f} us; biggest 1 s step {jump:.3f} us')
ana(f'{S}/box1in.wav',0,'box 1 L in (from box 2 L out)')
ana(f'{S}/box2in.wav',1,'box 2 R in (from box 1 R out)')
