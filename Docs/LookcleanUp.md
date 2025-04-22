# Design Aesthetic Guidelines for Strategic Data Platform

**Clean, Grid-Based Layout**
- Use a clean and structured grid system to display complex tables and charts. Maintain ample whitespace for readability, especially in dense areas like fund holdings and comparison tables.

**Modern Professional Palette**
- Apply a neutral, professional colour scheme with selective use of accent colours (e.g., green for “held”, red for “not held”) to convey meaning, not just style. Use tones like slate, steel, navy, and soft white as base colours.

**High-Information Density, Low Clutter**
- Prioritise functional minimalism. Design for users who are analysts or data professionals—give them quick access to complex data without unnecessary UI decoration or distractions.

**Intuitive Hierarchical Navigation**
- Use a consistent sidebar or top-bar navigation system with clearly labelled routes (e.g., "Compare", "Staleness", "Issues"). Allow deep linking into views like /compare/<type>/details/<security_id> without losing context.

**Responsive, Multi-Device Friendly**
- Ensure designs adapt elegantly to varying screen sizes, from large monitors to smaller laptops. Tables should collapse or scroll gracefully; charts should remain legible.

**Interactive and Accessible Data Visualisations**
- Use modern charting libraries (e.g. D3.js or Recharts) to create responsive, overlayed time-series charts. Ensure tooltips, zooming, and date-range selection are easily operable.

**Consistency in Iconography and Typography**
- Use a professional sans-serif font (e.g., Inter, Roboto, or Helvetica Neue) and stick to a consistent size and weight hierarchy. Icons should be minimal, functional, and consistently styled throughout the app.

**Smart Use of State Indicators**
- Use colour and subtle icons or badges to indicate state: stale data, placeholder patterns, held/not held, issue status. Avoid relying solely on colour—pair with shapes or labels for accessibility.

**Elegant Table Styling**
- Tables are central to this app. Use alternating row shading, sticky headers, in-table filters, and hover effects for enhanced clarity. Clearly separate static attributes from dynamic metrics with visual hierarchy.

**Developer & User Efficiency**
- Design with power users in mind: include keyboard shortcuts, persistent filters, and remember user preferences where possible. Expose back-end traceability (e.g., data sources, last update) in an unobtrusive but accessible way.