# -*- coding: utf-8 -*-
"""
Created on Sat Jun  6 18:38:34 2026

@author: SILE11024610
"""

import numpy as np
import matplotlib.pyplot as plt

# Paramètres
dt = 1
t_max = 1000
S1 = 170     # seuil cuve 1
S2 = 60     # seuil cuve 2

# --- CUVE 1 ---
def a1(Q, t):
    return Q + 0.42*0.965 * dt # FIlling of Tk1

def b1(Q, t):
    return Q - 2.0947 * dt #Emptying of Tk1

# --- CUVE 2 ---
def c2(Q, t):  # remplissage
    return Q + 2.5*0.88 * dt #Filling of Tk2

def d2(Q, t):  # vidange
    return Q + ((2.5*0.88)-22) * dt #Emptying of Tk2

# Initialisation
times = np.arange(0, t_max, dt)

Q1 = np.zeros_like(times, dtype=float)
Q2 = np.zeros_like(times, dtype=float)

mode1 = "a"
mode2 = "off"   # au départ, cuve 2 inactive

# Simulation
for i in range(1, len(times)):
    t = times[i]

    # ===== CUVE 1 =====
    if mode1 == "a":
        Q1[i] = a1(Q1[i-1], t)
        if Q1[i] >= S1:
            mode1 = "b"
            mode2 = "c"   # démarrage cuve 2 en remplissage

    elif mode1 == "b":
        Q1[i] = max(0, b1(Q1[i-1], t))
        if Q1[i] <= 0:
            mode1 = "a"
            mode2= "off"

    # ===== CUVE 2 =====
    if mode2 == "c":  # remplissage
        Q2[i] = c2(Q2[i-1], t)
        if Q2[i] >= S2:
            mode2 = "d"

    elif mode2 == "d":  # vidange
        Q2[i] = max(0, d2(Q2[i-1], t))
        if Q2[i] <= 0:
            mode2 = "c"  # repart en remplissage

    else:
        Q2[i] = Q2[i-1]

# --- GRAPHIQUES ---
fig, axs = plt.subplots(2, 1, sharex=True, figsize=(10, 8))

# Cuve 1
axs[0].plot(times, Q1, label="qty in Tk1")
axs[0].axhline(S1, color='r', linestyle='--', label="Seuil S1")
axs[0].set_ylabel("Quantity")
axs[0].set_title("Tk1_crude monomer storage")
axs[0].legend()
axs[0].grid()

# Cuve 2
axs[1].plot(times, Q2, color='orange', label="qty in Tk2")
axs[1].axhline(S2, color='g', linestyle='--', label="Seuil S2")
axs[1].set_xlabel("Temps")
axs[1].set_ylabel("Quantity")
axs[1].set_title("Tk2_distilled monomer storage")
axs[1].legend()
axs[1].grid()

plt.show()
print(np.max(Q2))
nb_cycles = np.sum((Q2[1:] <= 1e-6) & (Q2[:-1] > 1e-6))
print(nb_cycles)
print(np.max(Q1))