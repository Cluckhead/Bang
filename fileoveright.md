Great! Here’s a detailed, actionable plan for both the **UI** and **backend** to support:
- Running extra funds and extra dates
- Overwriting overlapping data (if a fund/date exists, it is replaced)
- Expanding (appending) new data otherwise
- A clear UI showing when each fund/date combination was last written to
- Retaining the “Run and Overwrite” button to start every file from scratch

---

## 1. **UI Changes (`get_data.html` and JS)**

### a. **Date Range Selection**
- Replace or supplement the “Days Back” and “End Date” fields with a **date range picker** (Start Date, End Date).
- Optionally, keep “Days Back” for quick selection, but when a custom range is picked, use that.

### b. **Overwrite/Expand Mode**
- Add a **dropdown or radio group**:
  - “Expand (append new data, overwrite overlaps)”
  - “Run and Overwrite All” (existing button, starts every file from scratch)

### c. **Status Table**
- Add a new table (or extend the existing one) to show, for each fund/date combination:
  - Fund
  - Date
  - File Name
  - Last Written (timestamp, if available)
  - Action Taken (Overwritten, Appended, Skipped, Error)
- This table is updated after each run.

### d. **Confirmation**
- If “Run and Overwrite All” is selected, show a confirmation dialog.

---

## 2. **Backend/API Changes**

### a. **API Parameters**
- Accept:
  - `start_date`, `end_date` (or a list of dates)
  - `funds` (list)
  - `mode`: `"expand"` or `"overwrite_all"`

### b. **Processing Logic**
- For **expand** mode:
  - For each fund/date:
    - If data exists for that fund/date, **overwrite** it.
    - If not, **append** as new.
- For **overwrite_all** mode:
  - For each relevant file, **delete all existing data** and write only the new data.

### c. **Tracking Last Written**
- For each fund/date/file, record the last written timestamp (could be a new column in the file, or a separate metadata file, or just in the response summary).

### d. **Result Reporting**
- Return a summary for each fund/date/file:
  - Action taken (Overwritten, Appended, Skipped, Error)
  - Last written timestamp

---

## 3. **Implementation Steps**

### **UI**
1. Add a date range picker (start/end date) to the form.
2. Add a dropdown/radio for “Expand” vs “Run and Overwrite All”.
3. Update JS to send `start_date`, `end_date`, `mode` in the API request.
4. Update the results table to show fund/date/file/action/last written.
5. Add a confirmation dialog for “Run and Overwrite All”.

### **Backend**
1. Update `/run-api-calls` and `/rerun-api-call` endpoints to accept new parameters.
2. Refactor file processing:
   - For “expand”: load file, drop rows for selected fund/date, append new data, save.
   - For “overwrite_all”: clear file, write only new data.
3. For each fund/date/file, record the action and last written timestamp in the response.
4. Return a detailed summary to the frontend.

---

## 4. **Example User Flow**

1. User selects funds: FUND1, FUND2.
2. User picks date range: 2024-05-01 to 2024-05-10.
3. User selects “Expand (append/overwrite overlaps)” and clicks “Simulate API Calls”.
4. Results table shows, for each fund/date/file, whether data was appended or overwritten, and the last written time.
5. User selects “Run and Overwrite All”, confirms, and all files are reset and rewritten from scratch.

---

## 5. **Technical Notes**

- **Overwrite on overlap:** For “expand”, always drop existing rows for the fund/date before appending new data.
- **Last written tracking:** If not storing in the data file, keep a simple JSON or CSV metadata file per data file, mapping (fund, date) to last written timestamp.
- **Atomic writes:** Use temp files and rename to avoid corruption.
- **Performance:** For large files, use pandas for efficient row filtering and appending.

---

## 6. **Next Steps**

Would you like to start with the UI or backend code?  
Or should I provide a code sketch for both in parallel (recommended for clarity)?
