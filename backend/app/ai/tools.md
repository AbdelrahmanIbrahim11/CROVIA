# AI Tools Module (`/backend/app/ai/tools.py`)

This module defines the tools the AI agent uses to investigate crowds. 
**Core Philosophy:** Tools gather evidence and spend API budget. They do *not* decide if a crowd is dangerous—that is left to a deterministic, auditable rule.

---

### 1. `arm_chokepoints` (The Tripwire)
*   **Input**: The system engine and a specific zone ID.
*   **Process**: It acts as an early warning system. It pulls static city data (like the physical limits of the zone) and checks how fast it is currently filling. It then puts the parent district into "WATCHING" mode to elevate surveillance.
*   **Returns**: The bottleneck width // the district with the smallest width, theoretical capacity, and current fill rate. (Cost: Free).

### 2. `verify_and_filter` (The Data Gatherer)
*   **Input**: The system engine, a zone ID, and a budget (`max_calls`).
*   **Process**: It estimates the crowd size. It selects a random sample ("panel") of devices and pays the telecom network to check if they are inside the zone. It logs this timestamped headcount into the engine's history, which is essential for tracking flow rates over time.
*   **Returns**: The estimated total number of people in the zone and the number of devices checked. (Cost: Moderate).

### 3. `retrieve_locations_batch` (The Heavy Sensor)
*   **Input**: The system engine, a zone ID, and a `batch_size`.
*   **Process**: It secures precise location fixes. To save money, it pulls a large pool of candidates and pre-filters them to see if they are reachable (which is free) before paying for expensive location data. It halts as soon as it meets the batch size limit.
*   **Returns**: The number of reachable devices, the number of successful fixes, and the **median** accuracy of those fixes. The median is used so a single terrible reading (like a 2km cell-tower ping) doesn't ruin the accuracy score of an otherwise precise batch. (Cost: High).

### 4. `judge` (The Messenger)
*   **Input**: The system engine and a zone ID.
*   **Process**: It defers the final decision. It gathers the latest metrics (headcount, fill rate, and how long the zone has been dangerously filling). It requires *two consecutive* dangerous readings before it starts the danger clock, preventing false alarms. It hands this evidence to the `detect.danger.assess()` module.
*   **Returns**: A definitive, mathematical verdict on whether the zone is currently dangerous, along with the reasoning. (Cost: Free).

