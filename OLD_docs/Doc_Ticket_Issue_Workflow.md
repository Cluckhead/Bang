# Ticket & Issue Workflow

This document illustrates the end-to-end journey of an automatically generated data-quality ticket, from initial creation to final closure, and how it links to the Data Issues system.

```mermaid
flowchart TD
    A[Data Quality Check<br/>run_all_checks.py] --> B(Unallocated Ticket)
    B --> C{Bulk/Single Assign?}
    C -->|Assign| D[Assigned to User]
    D -->|Clear| E[Clear Modal]
    E -->|Raise Issue checked| I(Generate Issue)
    E -->|Raise Issue unchecked| F[Ticket Cleared ➜ Suppression]
    D -->|Mark for Retest| G[Waiting for Rerun]
    G --> H{Next Scheduled Run}
    H -->|Rerun| B

    I --> J[Issue Created]
    J --> K[Issue Detail Page]
    K -->|Add Comment| K
    K -->|Close Issue| L[Closed]

    style B fill:#fdf6b2,stroke:#e5e7eb
    style G fill:#fef3c7,stroke:#e5e7eb
    style D fill:#bfdbfe,stroke:#93c5fd
    style E fill:#d1fae5,stroke:#6ee7b7
    style F fill:#e0e7ff,stroke:#a5b4fc
    style J fill:#fcd34d,stroke:#fbbf24
    style K fill:#fef9c3,stroke:#fbbf24
    style L fill:#d1d5db,stroke:#9ca3af
```

Legend:

* **Unallocated Ticket** – Newly created, awaiting assignment.
* **Assigned to User** – Analyst owns the ticket.
* **Waiting for Rerun** – Ticket queued for the next data-quality run.
* **Clear Modal** – Analyst can clear the ticket and optionally raise an issue.
* **Issue Detail Page** – Supports comment timeline and status updates.

This workflow ensures transparency and preserves full audit trails from detection to remediation. 