# Core Engine Architecture: Presentation Guide
**Directory:** `/backend/app/core/`

This document provides a high-level, presentation-ready breakdown of the Core Engine. The Core modules manage the physical reality of the city, the financial constraints of the telecom APIs, and the privacy and location tracking of the citizens.

---

## 1. The Core Philosophy
**"Reliability & Privacy Above All"**
*   **Zero Database Dependency**: The entire live detection engine runs **100% in RAM**. During a mass-casualty crowd event, a database crash or cloud timeout would blind a traditional system. By operating strictly in memory, the engine guarantees absolute reliability and lightning-fast execution when it matters most.
*   **Privacy by Design**: The system is architected to track crowds without violating individual privacy, utilizing strict cryptographic hashing and minimal statistical sampling.

---

## 2. Security & Privacy Features (`registry.py`)
The system is built to protect citizen data at the deepest architectural level.
*   **The Cryptographic Vault**: The `Vault` acts as the absolute privacy boundary. It is the *only* component allowed to hold real phone numbers. The moment a user is enrolled, their number is secured using SHA-256 hashing. The entire AI, backend logic, and logging systems operate strictly using anonymous hashes.
*   **Just-In-Time Decryption**: The real phone number is only retrieved from the vault at the very last millisecond when the API client needs to ping the CAMARA telecom network.
*   **Statistical Sampling (The Panel)**: The system does not surveil every citizen. Instead, it tracks a "Panel"—a small, mathematically uniform random sample of users. This drastically minimizes the security footprint of the application while still providing highly accurate crowd estimations.

---

## 3. Financial Security & Spend Control (`budget.py`)
Because telecom APIs charge per call, a poorly optimized system could financially bankrupt the project during a single crowd surge. 
*   **Weighted Accounting**: The `Ledger` actively tracks API usage, assigning heavy financial weights to expensive GPS location calls and low weights to cheap reachability pings.
*   **The Bidding War**: When multiple crowds form simultaneously, zones must submit a `Request` (acting like an invoice) for API funds. The `Budget` acts as a central bank, utilizing a strict mathematical formula where **Urgency beats Size**. It refuses to spread money evenly (which yields weak data) and instead fully funds the most critical, immediate threat.
*   **Event Reserves**: The bank automatically holds back a percentage of the hourly budget if a scheduled event (like a stadium match) is approaching, ensuring funds aren't exhausted before the event even ends.

---

## 4. The Immutable Map (`city.py`)
The AI cannot be allowed to hallucinate physical geography. 
*   **The Single Source of Truth**: The Backend, the visual Dashboard, and the Crowd Simulator all load geography from a single shared JSON file upon boot. They can never disagree on a street's location or its width.
*   **The Golden Formula**: `Capacity = Width * 72`. The system knows exactly how many people can squeeze through a bottleneck (the narrowest street in a zone) per minute without making a single API call.
*   **Operator Guardrails**: If a human operator draws a custom emergency zone on the map, the system forces them to manually input the physical street width. The system refuses to guess, ensuring that manual zones are held to the exact same rigorous mathematical safety standards as pre-planned zones.

---

## 5. Key Presentation Talking Points (Summary)
When presenting the Core Architecture, emphasize these three pillars:
1.  **Unbreakable Architecture**: The 100% in-memory design ensures the crowd-safety system survives and continues tracking even if the backend databases crash.
2.  **Privacy First**: Deep SHA-256 hashing and statistical panel sampling guarantee that the system tracks *crowds*, not *individuals*.
3.  **Financial Intelligence**: The central bank algorithm mathematically prioritizes budget allocation to the most critical, time-sensitive threats, preventing API bankruptcy.

