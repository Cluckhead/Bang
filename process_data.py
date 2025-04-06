# This script serves as a pre-processing step for specific CSV files within the 'Data' directory.
# It targets files prefixed with 'pre_', reads them, and performs data aggregation and cleaning.
# The core logic involves grouping rows based on identical values across most columns, excluding 'Funds' and 'Security Name'.
# For rows sharing the same 'Security Name' but differing in other data points, the 'Security Name' is suffixed
# (e.g., _1, _2) to ensure uniqueness. The 'Funds' associated with identical data rows are aggregated
# into a single list-like string representation (e.g., '[FUND1,FUND2]').
# The processed data is then saved to a new CSV file prefixed with 'new_'.

# process_data.py
# This script processes CSV files in the 'Data' directory that start with 'pre_'.
# It merges rows based on identical values in all columns except 'Funds'.
# Duplicated 'Security Name' entries with differing data are suffixed (_1, _2, etc.).
# The aggregated 'Funds' are stored as a list in the output file.

import os
import pandas as pd

def process_csv_file(input_path, output_path):
    """
    Reads a 'pre_' CSV file, processes it according to the rules,
    and writes the result to a 'new_' CSV file.

    Args:
        input_path (str): Path to the input CSV file (e.g., 'Data/pre_sec_duration.csv').
        output_path (str): Path to the output CSV file (e.g., 'Data/new_sec_duration.csv').
    """
    try:
        # Read the input CSV
        df = pd.read_csv(input_path)
        print(f"Processing file: {input_path}")

        # Store original columns order, excluding Funds for grouping keys
        original_cols = df.columns.tolist()
        if 'Funds' not in original_cols or 'Security Name' not in original_cols:
             print(f"Skipping {input_path}: Missing required columns 'Funds' or 'Security Name'.")
             return

        # Identify columns to check for identity (all except Funds and Security Name)
        id_cols = [col for col in original_cols if col not in ['Security Name', 'Funds']]

        processed_rows = []

        # Group by the primary identifier 'Security Name'
        grouped_by_sec = df.groupby('Security Name', sort=False)

        for sec_name, sec_group in grouped_by_sec:
            # Within each security group, further group by all other identifying columns
            # This separates rows where the same Security Name has different associated data
            try:
                sub_grouped = sec_group.groupby(id_cols, dropna=False, sort=False) # dropna=False to treat NaNs as equal for grouping
                distinct_versions = [group for _, group in sub_grouped]
            except KeyError:
                # If id_cols is empty (only Security Name and Funds exist), treat as one version
                 distinct_versions = [sec_group]


            num_versions = len(distinct_versions)

            # Iterate through each distinct version found for the current Security Name
            for i, current_version_df in enumerate(distinct_versions):
                # Aggregate the unique 'Funds' for this specific version
                funds_list = sorted(current_version_df['Funds'].unique().tolist())

                # Take the first row of this version as the template for the output row
                new_row_series = current_version_df.iloc[0].copy()

                # Assign the aggregated funds as a string formatted like a list: "[FUND1,FUND2,...]"
                new_row_series['Funds'] = f"[{','.join(funds_list)}]"

                # If there was more than one distinct version for this Security Name, suffix the name
                if num_versions > 1:
                    new_row_series['Security Name'] = f"{sec_name}_{i+1}"
                # Else: keep the original Security Name (already set in new_row_series)

                # Append the processed row (as a dictionary) to our results list
                processed_rows.append(new_row_series.to_dict())

        if not processed_rows:
            print(f"No data processed for {input_path}. Output file will be empty or header-only.")
            # Create an empty DataFrame with original columns if no rows processed
            output_df = pd.DataFrame(columns=original_cols)
        else:
             # Create the final DataFrame from the list of processed rows
            output_df = pd.DataFrame(processed_rows)
             # Ensure the column order matches the original input file
            output_df = output_df[original_cols]


        # Write the processed data to the new CSV file
        # The Funds column now contains comma-separated strings, which pandas will quote if necessary.
        output_df.to_csv(output_path, index=False)
        print(f"Successfully created: {output_path}")

    except FileNotFoundError:
        print(f"Error: Input file not found - {input_path}")
    except pd.errors.EmptyDataError:
         print(f"Error: Input file is empty - {input_path}")
    except Exception as e:
        print(f"An unexpected error occurred processing {input_path}: {e}")


def main():
    """
    Main function to find and process all 'pre_*.csv' files in the 'Data' directory.
    """
    input_dir = 'Data'
    input_prefix = 'pre_'
    output_prefix = 'new_'

    if not os.path.isdir(input_dir):
        print(f"Error: Input directory '{input_dir}' not found.")
        return

    # Iterate through all files in the specified directory
    for filename in os.listdir(input_dir):
        # Check if the file matches the pattern 'pre_*.csv'
        if filename.startswith(input_prefix) and filename.endswith('.csv'):
            input_file_path = os.path.join(input_dir, filename)
            # Construct the output filename by replacing 'pre_' with 'new_'
            output_filename = filename.replace(input_prefix, output_prefix, 1)
            output_file_path = os.path.join(input_dir, output_filename)

            # Process the individual CSV file
            process_csv_file(input_file_path, output_file_path)

if __name__ == "__main__":
    # Ensure the script runs the main function when executed directly
    main() 