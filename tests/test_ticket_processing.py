# Purpose: Simple unit tests for ticket_processing canonicalization and minimal CRUD functions.

import pandas as pd
import os
from analytics.ticket_processing import (
    canonicalize_details,
    generate_event_hash,
    initialize_ticket_files,
    create_ticket,
    assign_ticket,
    clear_ticket,
    get_unallocated_tickets_count,
    load_tickets,
    load_cleared_exceptions,
)


def test_canonicalize_details_patterns():
    # Z-Score bucketing
    assert canonicalize_details("Duration: Z-Score = 4.20") == "Duration: Z-Score = 4"
    assert canonicalize_details("Spread: Z-Score = -5.2") == "Spread: Z-Score = -5"
    # MaxMin value stripping
    assert canonicalize_details("sec_Spread.csv: Value 1250 > threshold 1000") == "sec_Spread.csv: Value > threshold"
    # Staleness bucketing
    assert canonicalize_details("sec_Duration.csv: Stale for 7 days") == "sec_Duration.csv: Stale for 1+ weeks"
    assert canonicalize_details("sec_Duration.csv: Stale for 16 days").endswith("months") or \
        canonicalize_details("sec_Duration.csv: Stale for 16 days").endswith("weeks")


def test_event_hash_stable():
    a = generate_event_hash("ZScore", "XS1", "Duration: Z-Score = 4.20")
    b = generate_event_hash("ZScore", "XS1", "Duration: Z-Score = 4.85")
    # Same canonical bucket (4) should produce same hash
    assert a == b


def test_ticket_minimal_crud_flow(tmp_path):
    data_dir = str(tmp_path)
    initialize_ticket_files(data_dir)
    # Start empty
    assert get_unallocated_tickets_count(data_dir) == 0

    # Create ticket
    tid = create_ticket("MaxMin", "XS000", "sec_Spread.csv: Value 1250 > threshold 1000", data_dir)
    assert isinstance(tid, str) and tid.startswith("TICKET-")
    assert get_unallocated_tickets_count(data_dir) == 1

    # Assign
    ok = assign_ticket(tid, "AnalystA", data_dir)
    assert ok is True

    # Clear
    ok2 = clear_ticket(tid, "AnalystA", "Explained by event", data_dir)
    assert ok2 is True

    # Files updated
    df_t = load_tickets(data_dir)
    df_c = load_cleared_exceptions(data_dir)
    assert not df_t.empty and not df_c.empty
    assert (df_t["TicketID"] == str(tid)).any()
    assert (df_c["TicketID"] == str(tid)).any()

