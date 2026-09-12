# Budget & Accounting Module (`/backend/app/core/budget.py`)

This module is responsible for strict financial control. Because telecom API calls cost money, the system must track every penny spent and act as an intelligent bank when multiple dangerous crowds are competing for a limited budget.

---

## Core Components

### 1. The Pricing Tiers (`TIER_WEIGHT`)
*   **Purpose**: Not all API calls cost the same. This static dictionary assigns relative weights to different network actions. For example, pinging a device to see if it's reachable is cheap (`0.5`), but requesting an exact GPS coordinate is expensive (`3.0`).

### 2. The Accountant (`Ledger` Class)
*   **Input**: The type of API call made (tier) and the district that made it.
*   **Process**: It acts as a passive, independent logbook. It does not make decisions; it simply aggregates three separate running totals:
    1.  How many calls of each type were made.
    2.  How many total calls each district made.
    3.  How many network errors (e.g., 500 Server Error) occurred.
*   **Returns**: A clean, summarized dictionary (`summary()`) used for system dashboards and engine snapshots.

### 3. The Invoice (`Request` Class)
*   **Input**: A zone's live statistics (current crowd size, danger severity, and how many seconds until the situation becomes critical).
*   **Process**: When multiple crowds form simultaneously, the system cannot afford to investigate all of them. Zones submit a `Request` (acting like an invoice or a bid) to ask for funding. The class calculates a strict priority score where **Urgency beats Size**. A small crowd that will become critical in 3 minutes will mathematically outbid a massive crowd that has 20 minutes of safety remaining.
*   **Returns**: A mathematical priority score used to win budget allocation.

### 4. The Bank (`Budget` Class)
*   **Input**: A list of `Request` invoices and a rolling hourly limit (e.g., 6000 calls/hour).
*   **Process**: It manages the system's actual purse strings.
    *   **Rolling Window**: It continuously prunes calls made more than 3600 seconds ago to maintain a rolling hourly limit.
    *   **Reserves**: It holds back a percentage of the budget if a scheduled event (like a stadium match) is approaching, ensuring the system isn't financially bankrupt when the stadium doors open.
    *   **Allocation**: It acts as the final judge for the `Request` bids. It refuses to spread money evenly (which would result in weak, unusable data for everyone) and instead fully funds the highest-priority requests until the bank is empty.
*   **Returns**: A dictionary detailing exactly how many API calls were granted to each zone.

