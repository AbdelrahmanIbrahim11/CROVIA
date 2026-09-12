# Danger Assessment Rules (`/backend/app/detect/danger.py`)

This file holds the deterministic, auditable rules engine for declaring an emergency. It deliberately uses **zero AI**. In a disaster, the system must be able to point to a strict, mathematical rule to explain exactly why an alarm fired (or why it didn't).

---

## 1. The Core Philosophy: "Inferred vs Measured"
The greatest challenge with telecom API tracking is positioning error. If a phone's GPS error is 150-400 meters, you cannot accurately calculate the exact density of a crowd standing on a narrow 10-meter wide bridge. 
*   **The Flawed Approach**: If you simply use the raw coordinates, the crowd looks like it is spread out over a massive 400-meter circle, resulting in a perfectly safe density (e.g., 0.3 people/m²).
*   **The Brilliant Inference**: `danger.py` abandons raw coordinates. It takes three things that *are* knowable (Total people in the general zone, how fast they are arriving, and the physical width of the bridge from `city.py`). If 10,000 people enter a zone and cannot pass through the narrow bridge, the math **infers** that they are crushed against the bridge at maximum jam density.

---

## 2. The Three Triggers
The `assess()` function evaluates the incoming `Evidence` against three strict tests. None of these will fire if the crowd is actively draining.

### A. FILLING (The Early Warning)
*   **Condition**: The rate of new arrivals is greater than 60% of the narrowest street's physical capacity.
*   **Why it matters**: This is the only trigger that can warn an operator *before* the crowd is actually trapped. If 500 people per minute are entering a street that can only pass 300 per minute, a crush is mathematically guaranteed.

### B. NOT CLEARING (The Trap)
*   **Condition**: People inside the zone are not coming out. This is triggered if the outflow ratio collapses (less than 30% of the people who entered have left) or if the dwell time spikes (people are taking 1.8x longer than normal to walk the corridor).
*   **Why it matters**: A massive crowd is completely safe if it is moving fluidly. This trigger fires the moment the crowd gets "stuck".

### C. DENSITY (The Hard Limit)
*   **Condition**: The general corridor density exceeds the Fruin threshold for safety (adjusted for the risk multiplier of the specific street). 
*   **Why it matters**: The absolute mathematical failsafe. If there are simply too many human bodies crammed into the available square meters, it fires.

---

## 3. The Guardrails (K-Anonymity & Minimums)
To prevent false alarms and protect privacy, the verdict requires minimum thresholds:
*   `MIN_PEOPLE = 1200`: A crowd smaller than 1,200 people physically cannot generate a dangerous crush force, no matter how slowly they move.
*   `K_ANONYMITY = 5`: The system refuses to publish a verdict if the sample size is fewer than 5 actual devices. Doing so would risk identifying an individual user.

