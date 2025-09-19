# Purpose: This file handles automatic ticket generation and management for data exceptions.
# It supports creating tickets from breaches detected in run_all_checks.py, assigning tickets to users,
# and clearing tickets with permanent suppression logic to prevent re-generation.

import pandas as pd
import os
import hashlib
import re
import math
from datetime import datetime
from typing import Optional, List, Tuple, Any, Dict
import logging
from core.io_lock import install_pandas_file_locks

REQUIRED_TICKET_COLUMNS = [
    "TicketID",
    "EventHash", 
    "GenerationDate",
    "SourceCheck",
    "EntityID",
    "Details",
    "Status",
    "AssignedTo",
    "AssignedDate",
    "ClearedBy",
    "ClearedDate",
    "ClearanceReason",
]

REQUIRED_CLEARED_COLUMNS = [
    "EventHash",
    "TicketID", 
    "ClearedBy",
    "ClearedDate",
    "ClearanceReason",
]

logger = logging.getLogger(__name__)
# Reduce log verbosity during large ticket operations to improve performance
logger.setLevel(logging.WARNING)

# Install global file locks in case this module is used via CLI or scripts
try:
    install_pandas_file_locks()
except Exception:
    pass


def canonicalize_details(details: str) -> str:
    """
    Canonicalize details string to create stable hashes for ticket suppression.
    
    This function normalizes violation details to prevent duplicate tickets for
    the same type of issue with minor value changes, while still allowing
    escalation for materially worse violations.
    
    Handles three types of violations:
    1. Z-Score: Buckets by integer Z-score value for escalation
    2. MaxMin: Removes specific values, keeps violation direction
    3. Staleness: Buckets by time periods (weekly buckets)
    
    Args:
        details (str): Original details string from violation detection
        
    Returns:
        str: Canonicalized details string for stable hashing
        
    Examples:
        "Duration Change: Z-Score = 4.20" -> "Duration Change: Z-Score = 4"
        "sec_Spread.csv: Value 1250 > threshold 1000" -> "sec_Spread.csv: Value > threshold"
        "sec_Duration.csv: Stale for 7 days" -> "sec_Duration.csv: Stale for 1+ weeks"
    """
    original_details = details
    
    # Handle Z-Score violations: "metric field: Z-Score = 4.20"
    zscore_match = re.search(r"(.+):\s*Z-Score\s*=\s*([-]?\d+(?:\.\d+)?)", details)
    if zscore_match:
        prefix = zscore_match.group(1)
        z_value = float(zscore_match.group(2))
        
        # Bucket by integer value for escalation logic
        # This allows re-alerting if violation gets significantly worse
        z_bucket = int(abs(z_value))  # 3.2 and 3.8 both -> bucket 3, but 4.1 -> bucket 4
        
        # Preserve the sign for negative Z-scores
        sign = "-" if z_value < 0 else ""
        canonical = f"{prefix}: Z-Score = {sign}{z_bucket}"
        
        logger.debug(f"Canonicalized Z-Score: '{original_details}' -> '{canonical}'")
        return canonical
    
    # Handle MaxMin violations: "file.csv: Value 1250 > threshold 1000"
    maxmin_match = re.search(r"(.+):\s*Value\s+.+\s*([><])\s*threshold\s+.+", details)
    if maxmin_match:
        prefix = maxmin_match.group(1)
        operator = maxmin_match.group(2)
        
        # Remove specific values, keep only the violation type
        canonical = f"{prefix}: Value {operator} threshold"
        
        logger.debug(f"Canonicalized MaxMin: '{original_details}' -> '{canonical}'")
        return canonical
    
    # Handle Staleness violations: "file.csv: Stale for 7 days"
    staleness_match = re.search(r"(.+):\s*Stale for\s+(\d+)\s+days?", details)
    if staleness_match:
        prefix = staleness_match.group(1)
        days = int(staleness_match.group(2))
        
        # Bucket by weekly periods to avoid daily re-ticketing
        # But still allow escalation for increasingly stale data
        if days <= 7:
            period = "1+ weeks"
        elif days <= 14:
            period = "2+ weeks"  
        elif days <= 21:
            period = "3+ weeks"
        elif days <= 30:
            period = "1+ months"
        else:
            # For very stale data, bucket by months
            months = math.ceil(days / 30)
            period = f"{months}+ months"
            
        canonical = f"{prefix}: Stale for {period}"
        
        logger.debug(f"Canonicalized Staleness: '{original_details}' -> '{canonical}'")
        return canonical
    
    # Fallback: if format doesn't match expected patterns, return as-is
    # This ensures the function is safe for unexpected detail formats
    logger.debug(f"No canonicalization pattern matched for: '{original_details}'")
    return details


def generate_event_hash(source_check: str, entity_id: str, details: str) -> str:
    """Generate a unique hash for an event to prevent duplicate tickets.
    
    Uses canonicalized details to create stable hashes that suppress
    duplicate tickets for the same underlying issue while allowing
    escalation for materially worse violations.
    """
    canonical_details = canonicalize_details(details)
    hash_input = f"{source_check}|{entity_id}|{canonical_details}"
    event_hash = hashlib.md5(hash_input.encode()).hexdigest()
    
    # Log the canonicalization for debugging purposes
    if canonical_details != details:
        logger.debug(f"Hash generation - Original: '{details}' -> Canonical: '{canonical_details}' -> Hash: {event_hash}")
    
    return event_hash

# -----------------------------
# Batch-mode write optimisation
# -----------------------------
# To speed up long-running validation scripts we can collect ticket changes
# in memory and flush them to disk once at the end.  This avoids hundreds of
# per-ticket CSV writes which were a major proportion of runtime.

_BATCH_MODE: bool = False  # Whether updates should be buffered
_pending_tickets: Dict[str, pd.DataFrame] = {}  # key = data_folder_path


def enable_batch_mode() -> None:
    """Enable batch buffering of ticket writes."""
    global _BATCH_MODE
    _BATCH_MODE = True


def flush_batch_writes() -> None:
    """Write all pending ticket DataFrames to disk and disable batch mode."""
    global _BATCH_MODE, _pending_tickets
    for folder, df in list(_pending_tickets.items()):
        try:
            _save_tickets(df.copy(), folder, force_write=True)
        except Exception:  # pragma: no cover – log inside _save_tickets
            pass
    _pending_tickets.clear()
    _BATCH_MODE = False


def load_tickets(data_folder_path: str) -> pd.DataFrame:
    """Loads the autogenerated tickets from the CSV file into a pandas DataFrame."""
    tickets_file = os.path.join(data_folder_path, "autogen_tickets.csv")
    try:
        if os.path.exists(tickets_file):
            try:
                df = pd.read_csv(
                    tickets_file, parse_dates=["GenerationDate", "AssignedDate", "ClearedDate"]
                )
                # Check and add missing columns
                existing_columns = df.columns.tolist()
                columns_added = False
                for col in REQUIRED_TICKET_COLUMNS:
                    if col not in existing_columns:
                        logger.info(f"Adding missing column '{col}' to tickets DataFrame.")
                        if "Date" in col:
                            df[col] = pd.NaT
                        elif col == "Status":
                            df[col] = "Unallocated"
                        else:
                            df[col] = None
                        columns_added = True
                        
                if columns_added:
                    logger.info("Saving tickets file with newly added columns.")
                    _save_tickets(df.copy(), data_folder_path)
                    # Re-read after saving to ensure correct types
                    df = pd.read_csv(
                        tickets_file, parse_dates=["GenerationDate", "AssignedDate", "ClearedDate"]
                    )
                
                # Ensure Status exists and fill missing with 'Unallocated'
                if "Status" not in df.columns:
                    df["Status"] = "Unallocated"
                else:
                    df["Status"] = df["Status"].fillna("Unallocated")
                    
                # Convert date columns
                df["GenerationDate"] = pd.to_datetime(df["GenerationDate"]).dt.date
                df["AssignedDate"] = pd.to_datetime(df["AssignedDate"]).dt.date  
                df["ClearedDate"] = pd.to_datetime(df["ClearedDate"]).dt.date
                df["TicketID"] = df["TicketID"].astype(str)
                
                # Reorder columns
                df = df[REQUIRED_TICKET_COLUMNS]
                return df
            except Exception as e:
                logger.error(f"Error parsing tickets file {tickets_file}: {e}", exc_info=True)
                return pd.DataFrame(columns=REQUIRED_TICKET_COLUMNS)
        else:
            logger.info(f"Tickets file not found at {tickets_file}. Returning empty DataFrame.")
            return pd.DataFrame(columns=REQUIRED_TICKET_COLUMNS)
    except Exception as e:
        logger.error(f"Unexpected error in load_tickets: {e}", exc_info=True)
        return pd.DataFrame(columns=REQUIRED_TICKET_COLUMNS)


def load_cleared_exceptions(data_folder_path: str) -> pd.DataFrame:
    """Loads the cleared exceptions suppression list from CSV."""
    cleared_file = os.path.join(data_folder_path, "cleared_exceptions.csv")
    try:
        if os.path.exists(cleared_file):
            df = pd.read_csv(cleared_file, parse_dates=["ClearedDate"])
            df["ClearedDate"] = pd.to_datetime(df["ClearedDate"]).dt.date
            return df
        else:
            logger.info(f"Cleared exceptions file not found at {cleared_file}. Returning empty DataFrame.")
            return pd.DataFrame(columns=REQUIRED_CLEARED_COLUMNS)
    except Exception as e:
        logger.error(f"Error loading cleared exceptions: {e}", exc_info=True)
        return pd.DataFrame(columns=REQUIRED_CLEARED_COLUMNS)


def _save_tickets(df: pd.DataFrame, data_folder_path: str, force_write: bool = False) -> None:
    """Saves the tickets DataFrame back to the CSV file."""
    tickets_file = os.path.join(data_folder_path, "autogen_tickets.csv")
    try:
        # Ensure all required columns exist before saving
        for col in REQUIRED_TICKET_COLUMNS:
            if col not in df.columns:
                logger.warning(f"Column '{col}' missing before saving. Adding it.")
                if "Date" in col:
                    df[col] = pd.NaT
                elif col == "Status":
                    df[col] = "Unallocated"
                else:
                    df[col] = None
                    
        # Reorder columns before saving
        df_to_save = df[REQUIRED_TICKET_COLUMNS].copy()
        
        # Convert date columns to string format
        date_cols = ["GenerationDate", "AssignedDate", "ClearedDate"]
        for col in date_cols:
            if col in df_to_save.columns:
                df_to_save[col] = pd.to_datetime(df_to_save[col]).dt.strftime("%Y-%m-%d")
                df_to_save[col] = df_to_save[col].replace("NaT", "")
                
        # Handle NaN in other object columns
        object_cols = df_to_save.select_dtypes(include=["object"]).columns
        for col in object_cols:
            df_to_save[col] = df_to_save[col].fillna("")
            
        if _BATCH_MODE and not force_write:
            _pending_tickets[data_folder_path] = df_to_save
        else:
            df_to_save.to_csv(tickets_file, index=False)
    except Exception as e:
        logger.error(f"Error saving tickets file: {e}", exc_info=True)


def _save_cleared_exceptions(df: pd.DataFrame, data_folder_path: str) -> None:
    """Saves the cleared exceptions DataFrame back to the CSV file."""
    cleared_file = os.path.join(data_folder_path, "cleared_exceptions.csv")
    try:
        df_to_save = df[REQUIRED_CLEARED_COLUMNS].copy()
        df_to_save["ClearedDate"] = pd.to_datetime(df_to_save["ClearedDate"]).dt.strftime("%Y-%m-%d")
        df_to_save["ClearedDate"] = df_to_save["ClearedDate"].replace("NaT", "")
        
        # Handle NaN in other columns
        object_cols = df_to_save.select_dtypes(include=["object"]).columns
        for col in object_cols:
            df_to_save[col] = df_to_save[col].fillna("")
            
        df_to_save.to_csv(cleared_file, index=False)
    except Exception as e:
        logger.error(f"Error saving cleared exceptions file: {e}", exc_info=True)


def _generate_ticket_id(existing_ids: pd.Series) -> str:
    """Generates a unique sequential ticket ID (e.g., TICKET-001)."""
    valid_ids = existing_ids.dropna().astype(str).str.strip()
    valid_ids = valid_ids[valid_ids != ""]
    if valid_ids.empty:
        return "TICKET-001"
    numeric_parts = (
        valid_ids.str.extract(r"TICKET-(\d+)", expand=False).dropna().astype(int)
    )
    if numeric_parts.empty:
        logger.warning("No existing IDs match the format 'TICKET-XXX'. Starting from 1.")
        return "TICKET-001"
    max_num = numeric_parts.max()
    new_num = max_num + 1
    return f"TICKET-{new_num:03d}"


def should_create_ticket(event_hash: str, data_folder_path: str) -> bool:
    """Check if a ticket should be created for this event hash."""
    # Check if the event is in the suppression list
    cleared_df = load_cleared_exceptions(data_folder_path)
    if not cleared_df.empty and event_hash in cleared_df["EventHash"].values:
        logger.debug(f"Event hash {event_hash} is suppressed (previously cleared)")
        return False
        
    # Check if there's already an active ticket for this event
    tickets_df = load_tickets(data_folder_path)
    if not tickets_df.empty:
        active_tickets = tickets_df[
            (tickets_df["EventHash"] == event_hash) & 
            (tickets_df["Status"].isin(["Unallocated", "Assigned", "WaitingRerun"]))
        ]
        if not active_tickets.empty:
            logger.debug(f"Event hash {event_hash} already has an active ticket")
            return False
    
    return True


def create_ticket(
    source_check: str,
    entity_id: str, 
    details: str,
    data_folder_path: str
) -> Optional[str]:
    """
    Create a new autogenerated ticket for a data exception.
    Uses smart aggregation - updates existing tickets for the same entity/source instead of creating duplicates.
    """
    try:
        event_hash = generate_event_hash(source_check, entity_id, details)
        
        if not should_create_ticket(event_hash, data_folder_path):
            return None
            
        df = load_tickets(data_folder_path)
        
        # Check for existing unallocated/assigned ticket for same entity and source
        existing_mask = (
            (df["EntityID"] == entity_id) & 
            (df["SourceCheck"] == source_check) & 
            (df["Status"].isin(["Unallocated", "Assigned"]))
        )
        
        if existing_mask.any():
            # Update existing ticket with latest details
            ticket_idx = existing_mask.idxmax()
            ticket_id = df.loc[ticket_idx, "TicketID"]
            
            # Update the details to show latest breach info and count
            existing_details = df.loc[ticket_idx, "Details"]
            if "| Updated:" in existing_details:
                # Extract count from existing details
                parts = existing_details.split("| Updated:")
                base_details = parts[0].strip()
                count_part = parts[1].split("times")[0].strip()
                try:
                    count = int(count_part) + 1
                except:
                    count = 2
            else:
                base_details = existing_details
                count = 2
            
            # Extract the new violation value from details for display
            if ": Value " in details:
                new_value = details.split(": Value ")[1].split(" ")[0]
                updated_details = f"{base_details} | Updated: {count} times, latest value: {new_value}"
            else:
                updated_details = f"{base_details} | Updated: {count} times"
                
            df.loc[ticket_idx, "Details"] = updated_details
            df.loc[ticket_idx, "EventHash"] = event_hash  # Update with latest hash
            
            # Save updated tickets
            _save_tickets(df, data_folder_path)
            logger.info(f"Updated existing ticket {ticket_id} for {source_check}: {entity_id} (count: {count})")
            return ticket_id
        
        else:
            # Create new ticket
            new_id = _generate_ticket_id(df["TicketID"])
            
            new_ticket = pd.DataFrame({
                "TicketID": [new_id],
                "EventHash": [event_hash],
                "GenerationDate": [datetime.now().date()],
                "SourceCheck": [source_check],
                "EntityID": [entity_id],
                "Details": [details],
                "Status": ["Unallocated"],
                "AssignedTo": [""],
                "AssignedDate": [pd.NaT],
                "ClearedBy": [""],
                "ClearedDate": [pd.NaT],
                "ClearanceReason": [""],
            })
            
            # Set proper dtypes for string columns
            new_ticket["AssignedTo"] = new_ticket["AssignedTo"].astype(str)
            new_ticket["ClearedBy"] = new_ticket["ClearedBy"].astype(str)
            new_ticket["ClearanceReason"] = new_ticket["ClearanceReason"].astype(str)
            
            # Ensure all required columns
            for col in REQUIRED_TICKET_COLUMNS:
                if col not in new_ticket.columns:
                    new_ticket[col] = pd.NaT if "Date" in col else None
                    
            new_ticket = new_ticket[REQUIRED_TICKET_COLUMNS]
            df_updated = pd.concat([df, new_ticket], ignore_index=True)
            _save_tickets(df_updated, data_folder_path)
            
            logger.info(f"Created new ticket {new_id} for {source_check}: {entity_id}")
            return new_id
            
    except Exception as e:
        logger.error(f"Error creating ticket: {e}", exc_info=True)
        return None


def assign_ticket(ticket_id: str, assigned_to: str, data_folder_path: str) -> bool:
    """Assign a ticket to a user."""
    try:
        df = load_tickets(data_folder_path)
        df["TicketID"] = df["TicketID"].astype(str)
        ticket_id_str = str(ticket_id)
        
        matching_indices = df[df["TicketID"] == ticket_id_str].index
        if not matching_indices.empty:
            idx = matching_indices[0]
            if df.loc[idx, "Status"] != "Unallocated":
                logger.warning(f"Ticket ID {ticket_id_str} is not unallocated.")
                return False
                
            df.loc[idx, "Status"] = "Assigned"
            df.loc[idx, "AssignedTo"] = str(assigned_to)
            df.loc[idx, "AssignedDate"] = pd.to_datetime(datetime.now().date())
            _save_tickets(df, data_folder_path)
            
            logger.info(f"Assigned ticket {ticket_id_str} to {assigned_to}")
            return True
        else:
            logger.warning(f"Ticket ID {ticket_id_str} not found.")
            return False
    except Exception as e:
        logger.error(f"Error assigning ticket {ticket_id}: {e}", exc_info=True)
        return False


def clear_ticket(
    ticket_id: str,
    cleared_by: str, 
    clearance_reason: str,
    data_folder_path: str
) -> bool:
    """Clear a ticket and add its event hash to the suppression list."""
    try:
        df = load_tickets(data_folder_path)
        df["TicketID"] = df["TicketID"].astype(str)
        ticket_id_str = str(ticket_id)
        
        matching_indices = df[df["TicketID"] == ticket_id_str].index
        if not matching_indices.empty:
            idx = matching_indices[0]
            if df.loc[idx, "Status"] != "Assigned":
                logger.warning(f"Ticket ID {ticket_id_str} is not assigned.")
                return False
                
            event_hash = df.loc[idx, "EventHash"]
            
            # Update ticket status
            df.loc[idx, "Status"] = "Cleared"
            df.loc[idx, "ClearedBy"] = str(cleared_by)
            df.loc[idx, "ClearedDate"] = pd.to_datetime(datetime.now().date())
            df.loc[idx, "ClearanceReason"] = str(clearance_reason)
            _save_tickets(df, data_folder_path)
            
            # Add to suppression list
            cleared_df = load_cleared_exceptions(data_folder_path)
            new_cleared = pd.DataFrame({
                "EventHash": [event_hash],
                "TicketID": [ticket_id_str],
                "ClearedBy": [cleared_by],
                "ClearedDate": [datetime.now().date()],
                "ClearanceReason": [clearance_reason],
            })
            
            cleared_updated = pd.concat([cleared_df, new_cleared], ignore_index=True)
            _save_cleared_exceptions(cleared_updated, data_folder_path)
            
            logger.info(f"Cleared ticket {ticket_id_str} and added to suppression list")
            return True
        else:
            logger.warning(f"Ticket ID {ticket_id_str} not found.")
            return False
    except Exception as e:
        logger.error(f"Error clearing ticket {ticket_id}: {e}", exc_info=True)
        return False


def get_unallocated_tickets_count(data_folder_path: str) -> int:
    """Get count of unallocated tickets for dashboard display."""
    try:
        df = load_tickets(data_folder_path)
        if df.empty:
            return 0
        unallocated = df[df["Status"] == "Unallocated"]
        return len(unallocated)
    except Exception as e:
        logger.error(f"Error getting unallocated tickets count: {e}", exc_info=True)
        return 0


def bulk_assign_tickets(ticket_ids: List[str], assigned_to: str, data_folder_path: str) -> Tuple[int, int]:
    """
    Assign multiple tickets to a user in bulk.
    Returns tuple of (successfully_assigned, total_attempted).
    """
    try:
        df = load_tickets(data_folder_path)
        df["TicketID"] = df["TicketID"].astype(str)
        
        success_count = 0
        total_count = len(ticket_ids)
        
        for ticket_id_str in [str(tid) for tid in ticket_ids]:
            matching_indices = df[df["TicketID"] == ticket_id_str].index
            if not matching_indices.empty:
                idx = matching_indices[0]
                if df.loc[idx, "Status"] == "Unallocated":
                    df.loc[idx, "Status"] = "Assigned"
                    df.loc[idx, "AssignedTo"] = str(assigned_to)
                    df.loc[idx, "AssignedDate"] = pd.to_datetime(datetime.now().date())
                    success_count += 1
                else:
                    logger.warning(f"Ticket ID {ticket_id_str} is not unallocated (status: {df.loc[idx, 'Status']}).")
            else:
                logger.warning(f"Ticket ID {ticket_id_str} not found.")
        
        if success_count > 0:
            _save_tickets(df, data_folder_path)
            logger.info(f"Bulk assigned {success_count}/{total_count} tickets to {assigned_to}")
        
        return success_count, total_count
    except Exception as e:
        logger.error(f"Error in bulk assign tickets: {e}", exc_info=True)
        return 0, len(ticket_ids)


def bulk_clear_tickets(ticket_ids: List[str], cleared_by: str, clearance_reason: str, data_folder_path: str) -> Tuple[int, int]:
    """
    Clear multiple tickets in bulk.
    Returns tuple of (successfully_cleared, total_attempted).
    """
    try:
        df = load_tickets(data_folder_path)
        df["TicketID"] = df["TicketID"].astype(str)
        
        success_count = 0
        total_count = len(ticket_ids)
        
        cleared_records = []
        
        for ticket_id_str in [str(tid) for tid in ticket_ids]:
            matching_indices = df[df["TicketID"] == ticket_id_str].index
            if not matching_indices.empty:
                idx = matching_indices[0]
                if df.loc[idx, "Status"] == "Assigned":
                    event_hash = df.loc[idx, "EventHash"]
                    
                    # Update ticket status
                    df.loc[idx, "Status"] = "Cleared"
                    df.loc[idx, "ClearedBy"] = str(cleared_by)
                    df.loc[idx, "ClearedDate"] = pd.to_datetime(datetime.now().date())
                    df.loc[idx, "ClearanceReason"] = str(clearance_reason)
                    
                    # Prepare for suppression list
                    cleared_records.append({
                        "EventHash": event_hash,
                        "TicketID": ticket_id_str,
                        "ClearedBy": cleared_by,
                        "ClearedDate": datetime.now().date(),
                        "ClearanceReason": clearance_reason,
                    })
                    
                    success_count += 1
                else:
                    logger.warning(f"Ticket ID {ticket_id_str} is not assigned (status: {df.loc[idx, 'Status']}).")
            else:
                logger.warning(f"Ticket ID {ticket_id_str} not found.")
        
        if success_count > 0:
            # Save updated tickets
            _save_tickets(df, data_folder_path)
            
            # Add to suppression list
            cleared_df = load_cleared_exceptions(data_folder_path)
            new_cleared = pd.DataFrame(cleared_records)
            cleared_updated = pd.concat([cleared_df, new_cleared], ignore_index=True)
            _save_cleared_exceptions(cleared_updated, data_folder_path)
            
            logger.info(f"Bulk cleared {success_count}/{total_count} tickets by {cleared_by}")
        
        return success_count, total_count
    except Exception as e:
        logger.error(f"Error in bulk clear tickets: {e}", exc_info=True)
        return 0, len(ticket_ids)

# --- NEW: Retest Later Helpers --------------------------------------------------

def _reset_ticket_for_retest(df: pd.DataFrame, idx: int) -> None:
    """Helper to reset a ticket row back to an unallocated state for retesting."""
    df.loc[idx, "Status"] = "WaitingRerun"
    df.loc[idx, "AssignedTo"] = None
    df.loc[idx, "AssignedDate"] = pd.NaT
    # Do NOT update Cleared* fields or EventHash – retaining history is useful


def retest_ticket(ticket_id: str, data_folder_path: str) -> bool:
    """Mark a single ticket for retest (moves it back to Unallocated)."""
    try:
        df = load_tickets(data_folder_path)
        df["TicketID"] = df["TicketID"].astype(str)
        ticket_id_str = str(ticket_id)

        matching_indices = df[df["TicketID"] == ticket_id_str].index
        if not matching_indices.empty:
            idx = matching_indices[0]
            if df.loc[idx, "Status"] == "WaitingRerun":
                logger.info(f"Ticket {ticket_id_str} already marked WaitingRerun – skipping retest.")
                return True

            _reset_ticket_for_retest(df, idx)
            _save_tickets(df, data_folder_path)
            logger.info(f"Ticket {ticket_id_str} reset for retest.")
            return True
        else:
            logger.warning(f"Ticket ID {ticket_id_str} not found (retest).")
            return False
    except Exception as e:
        logger.error(f"Error retesting ticket {ticket_id}: {e}", exc_info=True)
        return False


def bulk_retest_tickets(ticket_ids: List[str], data_folder_path: str) -> Tuple[int, int]:
    """Bulk retest – moves tickets back to Unallocated. Returns (success, total)."""
    try:
        df = load_tickets(data_folder_path)
        df["TicketID"] = df["TicketID"].astype(str)

        success_count = 0
        total_count = len(ticket_ids)

        for ticket_id_str in [str(tid) for tid in ticket_ids]:
            matching_indices = df[df["TicketID"] == ticket_id_str].index
            if not matching_indices.empty:
                idx = matching_indices[0]
                if df.loc[idx, "Status"] != "WaitingRerun":
                    _reset_ticket_for_retest(df, idx)
                    success_count += 1
            else:
                logger.warning(f"Ticket ID {ticket_id_str} not found for bulk retest.")

        if success_count > 0:
            _save_tickets(df, data_folder_path)
            logger.info(f"Bulk retest: reset {success_count}/{total_count} tickets.")

        return success_count, total_count
    except Exception as e:
        logger.error(f"Error in bulk retest tickets: {e}", exc_info=True)
        return 0, len(ticket_ids)


def get_tickets_by_filters(
    data_folder_path: str,
    source_filter: str = None,
    status_filter: str = None,
    entity_filter: str = None,
    assigned_to_filter: str = None
) -> pd.DataFrame:
    """
    Get tickets filtered by various criteria.
    """
    try:
        df = load_tickets(data_folder_path)
        if df.empty:
            return df
        
        # Apply filters
        if source_filter and source_filter != "All":
            df = df[df["SourceCheck"] == source_filter]
        
        if status_filter and status_filter != "All":
            df = df[df["Status"] == status_filter]
        
        if entity_filter:
            df = df[df["EntityID"].str.contains(entity_filter, case=False, na=False)]
        
        if assigned_to_filter and assigned_to_filter != "All":
            if assigned_to_filter == "Unassigned":
                df = df[df["Status"] == "Unallocated"]
            else:
                df = df[df["AssignedTo"] == assigned_to_filter]
        
        return df
    except Exception as e:
        logger.error(f"Error filtering tickets: {e}", exc_info=True)
        return pd.DataFrame(columns=REQUIRED_TICKET_COLUMNS)


def initialize_ticket_files(data_folder_path: str) -> None:
    """Initialize the ticket files if they don't exist."""
    tickets_file = os.path.join(data_folder_path, "autogen_tickets.csv")
    cleared_file = os.path.join(data_folder_path, "cleared_exceptions.csv")
    
    try:
        if not os.path.exists(tickets_file):
            df = pd.DataFrame(columns=REQUIRED_TICKET_COLUMNS)
            _save_tickets(df, data_folder_path)
            logger.info(f"Initialized new tickets file at {tickets_file}.")
            
        if not os.path.exists(cleared_file):
            df = pd.DataFrame(columns=REQUIRED_CLEARED_COLUMNS)
            _save_cleared_exceptions(df, data_folder_path)
            logger.info(f"Initialized new cleared exceptions file at {cleared_file}.")
    except Exception as e:
        logger.error(f"Error initializing ticket files: {e}", exc_info=True) 