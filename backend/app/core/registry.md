# Device Registry Module (`/backend/app/core/registry.py`)

This module manages who the system is watching, where they are, and strictly protects user privacy by decoupling real phone numbers from system logic. 

## Core Philosophy: In-Memory Survival
The entire registry operates **100% in RAM** rather than relying on a database. 
*   **Why?** During a massive crowd emergency, a database crash or network timeout would instantly blind the safety system. By operating strictly in memory, the detection engine guarantees lightning-fast execution and absolute reliability when it matters most.
*   **Memory Efficiency**: Because the system tracks a *statistical sample* of users (rather than the entire population), the memory footprint remains incredibly small (measured in megabytes, not gigabytes), entirely eliminating the risk of an Out-Of-Memory (OOM) crash.

---

## 1. The Vault (`Vault` Class)
*   **Purpose**: The absolute privacy boundary. It is the only component in the entire system that is allowed to see or hold real phone numbers.
*   **Mechanics**: When a phone number is enrolled, the Vault hashes it (using SHA-256) into a 16-character string. It stores a dictionary mapping `Hash -> Real Number`. 
*   **Usage**: The rest of the engine only ever passes around the hashed ID. The Vault is only queried at the very last second when the system needs to send the real number out to the CAMARA telecom API.

## 2. The Device Registry (`DeviceRegistry` Class)
This class manages the geographical state of devices without ever knowing their true identities.

### The Two Groups (Sentinels vs. Panel)
The system purposefully divides tracked devices into two distinct groups to solve two different problems:
1.  **Sentinels**: A small, unbalanced fleet of devices given geofence subscriptions. We place more sentinels near expected events (like a stadium). Because their placement is unbalanced, they are great for *locating* a crowd, but mathematically terrible for *counting* one.
2.  **Panel**: A uniform, random sample of all app users across the entire city. Because this sample mathematically mirrors the city's true population distribution, the engine uses the panel to accurately *count* the crowd.

### Key Functions
*   **`place()` / `remove_from()`**: Updates the live location of a hashed device (e.g., logging that device `X` entered the Marina district at time `t`).
*   **`fleet()`**: Returns a list of all hashed devices currently known to be inside a specific district. This is used by the orchestrator to calculate the percentage of a district that is currently experiencing network congestion.
*   **`people_from_panel()`**: The core mathematical function that extrapolates a final headcount. It takes the ratio of panel members found inside a zone and multiplies it by the city's total population to produce an unbiased estimate of the true crowd size.

