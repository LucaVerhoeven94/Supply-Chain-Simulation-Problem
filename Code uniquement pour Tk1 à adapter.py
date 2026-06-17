# -*- coding: utf-8 -*-
"""
Created on Tue Jun 16 21:53:07 2026

@author: SILE11024610
"""

import numpy as np
import matplotlib.pyplot as plt
#Parameters
f_pbr = 0.42  # Reactor feed flowrate, MT/h
y_pbr = 0.965 # Isomerization yield, dimensionless
Tk1 = 0. # Initial amount of product stored in Tk1
t = 0. # Initial campaign duration, h
tf =1200 #h
dt = 1 #time step, h
f_dist = 2.5 # Distilation feed flowrate, MT/h
max_cap = 156.1 # Storage tank 1 max capacity, MT
min_target = 412 # minimal crude production targted to reach 250MT , MT

#Functions definition
def filling(Tk1, t):
    return Tk1 + f_pbr*y_pbr*dt

def dist_start (Tk1,t):
    return Tk1 + (f_pbr*y_pbr*dt) - (f_dist*dt)

def crude_produced (t):
    return f_pbr*y_pbr*t
    
#Initialisation
tvals = [0.]
Tk1_content = [0.]
Qty_produced = [0.]
mode = "filling"

while t<tf:
    t+=dt
    crude_amount = crude_produced(t)
    if mode=="filling":
        Tk1 = filling(Tk1, t)
        if  Tk1 >= max_cap:
            mode = "dist_start"
    elif mode == "dist_start":
        Tk1 = dist_start(Tk1, t)
        if Tk1 <= 0:
            mode = "filling"
            
    tvals.append(t)
    Tk1_content.append(Tk1)
    Qty_produced.append(crude_amount)
    
    if Qty_produced[-1] > min_target:
        print ('Desired crude amount reached after', t ,'hours')
        break
plt.plot(tvals,Tk1_content)
plt.xlabel('Hours')
plt.ylabel('Qty in Tk1')
plt.show()
    