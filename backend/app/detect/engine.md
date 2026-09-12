# Detection Engine (`/backend/app/detect/engine.py`)

## Overview: The Grand Orchestrator
While the AI suggests actions, the `Engine` is the deterministic hub of the system. It physically holds the telecom API client, listens to network webhooks, tracks the live state of the city, and manages the budget. 

---

## Core State Management

### 1. `__init__` (The Assembler)
*   It brings all the isolated backend modules together: the `City` map, the `DeviceRegistry`, the `Budget` bank, and the `CamaraClient`. 
*   It initializes memory-capped logs (`trace` and `alerts`). By strictly capping how many logs are held in memory (e.g., `MAX_TRACE = 500`), it ensures the server never suffers an Out-Of-Memory (OOM) crash during long runtimes.

### 2. Parent/Child States (`DistrictState` & `ZoneState`)
The engine tracks danger using a bidirectional relationship between broad districts and precise zones.
*   **Top-Down**: Because generic telecom congestion alerts lack precise GPS, they are logged at the `DistrictState` level. If a district gets highly congested, it acts as an early warning, prompting the engine to start investigating all the smaller `ZoneState`s inside it.
*   **Bottom-Up**: If a specific Zone (like a stadium gate) crosses the threshold into danger, it triggers an `ALERT`. This bubbles up, forcing the entire parent District into the `ALERT` state as well.

---

## Precision and Cadence

### 3. The `CADENCE` Settings
The engine dynamically alters how often it polls a zone based on the zone's danger level, solving two massive engineering problems:
*   **Budget Exhaustion**: If the engine polled every zone every 30 seconds at maximum capacity, it would bankrupt the API budget in minutes. Therefore, `IDLE` zones are only checked every 5 minutes, while active `ALERT` zones are polled every 60 seconds.
*   **Statistical Coarseness**: When polling a tiny sample of devices, 1 device might statistically represent thousands of people. Small samples are too "coarse" for tracking an active crowd, but massive samples cost too much money. The `CADENCE` settings were chosen mathematically via simulation ("Balanced") because they catch 100% of crushes with 0 false alarms, without over-spending.

### 4. Crowd Speed (`rate_per_min`)
*   To figure out how fast a crowd is growing, the engine does not simply subtract the newest headcount from the oldest. That method is highly susceptible to random statistical noise.
*   Instead, `ZoneState` looks at the last 7 minutes of headcounts and applies **Least-Squares Linear Regression** to draw a line of best fit. 
*   It calculates the slope of this line to determine a highly accurate, noise-resistant flow rate (people per minute).

---

## The Triggers & Evidence

### 5. Scheduled Events (The Earliest Trigger)
*   A calendar invite for the engine (e.g., a football match). It is the **earliest and cheapest trigger** in the system. 
*   Without spending a single API call, the engine mathematically compares the expected arrival rate against the street's physical capacity. If `inflow > capacity`, it generates a prediction warning before the crowd even begins to form.

### 6. Webhook Listeners (The Receptionists)
*(Routed via `/backend/app/api/webhooks.py`)*
*   **`on_congestion` vs `on_congestion_device`**: Both log telecom network congestion. The first receives a generic subscription ID and must look it up in the registry. The second receives the hashed device ID directly via a custom webhook URL routing, skipping the lookup.
*   **`on_geofence`**: Strictly uses broad `"district"` level geofences. It avoids using tight "zone" geofences because cell-tower positioning error (150m-400m) would cause massive amounts of false entering/exiting alerts as phones bounce between towers.
*   **`on_subscription_end`**: Crucial for visibility. It unbinds a device from a tracking subscription so the engine knows the phone dropped offline. This prevents the engine from falsely assuming a crowd dispersed just because the network went silent.

### 7. The Main Sensor (`count_zone`)
*   **Process**: It grabs a **fresh, random sample** of the `Panel`. It pings the CAMARA Location Verification API for each person in the sample.
*   **The UNKNOWN Fix**: If the telecom network returns `UNKNOWN` (meaning it couldn't locate the phone), the code explicitly discards that phone from the math. If it counted them as "not in the zone", the system would drastically under-count the true size of the crowd.
*   **Returns**: It runs the registry math `(inside / checked * city_population)` to return an unbiased estimate of the total crowd size.

---

## The Execution Loop (`tick()`)
The `tick()` function runs continuously to drive the system. It processes all evidence and spends the budget through these steps:

1.  **Network Fault Suppression**: It checks the congestion level of all districts. If *every single district* in the city spikes at the exact same time, the engine recognizes a telecom routing fault, not a massive 4-district crowd crush. It suppresses all action to save the budget.
2.  **The Request Builder**: It evaluates which zones are "interesting" (e.g., they have a scheduled event, their district is congested, or their growth rate is > 0). It builds a `Request` invoice for each interesting zone.
3.  **Budget Allocation**: It hands the invoices to the `Budget` class. The Budget uses its mathematical urgency formula to grant API calls only to the most critical zones.
4.  **Verification**: Using the granted budget, the engine runs `count_zone` to get a fresh headcount.
5.  **Danger Assessment**: It passes all the fresh evidence to the deterministic `danger.py` rules engine, which mathematically determines if the zone is officially dangerous.

---

## Architecture Resiliency

### The Survival Hooks (`_notify`)
If the engine declares an `ALERT`, it must save it to the PostgreSQL database for the frontend dashboard to see. However, the live detection engine refuses to depend on a database. 
*   **The Safety Net**: The database-write function is passed into the engine as a `hook`. The `_notify` function wraps this hook in a strict `try/except` block.
*   **Result**: If the database crashes, the hook fails, but the engine simply logs *"could not record the alarm"*, shrugs it off, and instantly moves on to detect the next crowd. The system is uncrashable.

