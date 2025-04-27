## Phase 1: Frontend Refactoring Plan: FiveThirtyEight Style

**Goal:** Recast the BANG Data Checker frontend to align with the provided style guide, ensuring it runs offline without server-side dependencies for styling or core UI interactions.

**Overall Approach:** We'll tackle this in layers, starting with foundational elements (CSS, layout, typography) and then moving to specific components and interactions. This ensures consistency and minimizes rework.

**Key Considerations for AI Developer:**

- Offline First: All styling and core UI JavaScript must function without a server connection after initial load. Use downloaded libraries or CDN links that can be cached. Avoid server-side rendering dependencies for UI elements.
- Consistency: Apply styles (colors, fonts, spacing, cards) uniformly across all templates as defined below.
- Responsiveness: No need for responsiveness this will only ever be loaded on widescreen desktops

- Clean Code: Remove old CSS classes (e.g., Bootstrap) and ensure HTML is semantic.

## Phase 2: Foundational Setup & Global Styles

### 2.1 CSS Framework & Reset
2.1.1 Action: All styling will be implemented using Tailwind CSS with a custom configuration and local build process for offline support.
2.1.2 File(s): tailwind.config.js, static/css/style.css (for any additional overrides), integrate Tailwind build output into templates/base.html.
2.1.3 Details:
- Tailwind will be set up with a local build process. The configuration (tailwind.config.js) will define the specified palette (Section 2), fonts (Section 3), and spacing (e.g., rounded-lg for 8px radius, shadow shadow-[0_0_4px_rgba(0,0,0,0.06)]).
- Remove all existing Bootstrap CSS links and classes from templates/base.html and other templates.
2.1.4 Templates to Update for Tailwind Migration:
- base.html: ✅ COMPLETE - Bootstrap classes/dependencies removed, layout/navigation ready for Tailwind, tested.
- index.html: ✅ COMPLETE - Bootstrap classes removed, ready for Tailwind refactor, tested.
- metric_page_js.html: ✅ COMPLETE - Bootstrap classes and dependencies removed, ready for Tailwind refactor, tested.
- securities_page.html: ✅ COMPLETE - Bootstrap classes and dependencies removed, ready for Tailwind refactor, tested.
- security_details_page.html: ✅ COMPLETE Remove Bootstrap classes, refactor two-column layout/cards/tables/buttons/charts with Tailwind, test.
- watchlist_page.html: ✅ COMPLETE Remove Bootstrap classes, refactor table/cards/buttons/forms with Tailwind, test.
- get_data.html: 🟡 INCOMPLETE - Bootstrap removal requires manual review due to file size/complexity.
- inspect_results.html: ✅ COMPLETE - Bootstrap classes removed, ready for Tailwind refactor, tested.
- maxmin_dashboard.html: ✅ COMPLETE  Remove Bootstrap classes, refactor dashboard/cards/buttons with Tailwind, test.
- maxmin_details.html: ✅ COMPLETE Remove Bootstrap classes, refactor details table/cards/buttons with Tailwind, test.
- comparison_summary_base.html: ✅ COMPLETE Remove Bootstrap classes, refactor summary table/cards/buttons/forms with Tailwind, test.
- exclusions_page.html: ✅ COMPLETE Remove Bootstrap classes, refactor exclusions table/cards/forms/buttons with Tailwind, test.
- curve_summary.html: ✅ COMPLETE Remove Bootstrap classes, refactor summary table/cards/buttons with Tailwind, test.
- fund_detail_page.html: ✅ COMPLETE Remove Bootstrap classes, refactor grid/cards/charts/forms with Tailwind, test.
- issues_page.html: ✅ COMPLETE Remove Bootstrap classes, refactor forms/tables/cards/buttons with Tailwind, test.
- comparison_details_base.html: ✅ COMPLETE Remove Bootstrap classes, refactor detail layout/cards/tables/charts with Tailwind, test.
- attribution_charts.html: ✅ COMPLETE Remove Bootstrap classes, refactor grid/cards/charts/forms with Tailwind, test.
- staleness_details.html: ✅ COMPLETE Remove Bootstrap classes, refactor details layout/cards/tables with Tailwind, test.
- staleness_dashboard.html: ✅ COMPLETE Remove Bootstrap classes, refactor dashboard layout/cards/tables with Tailwind, test.
- error.html: ✅ COMPLETE Remove Bootstrap classes, refactor error card/button/layout with Tailwind, test.
- attribution_security_page.html: ✅ COMPLETE Remove Bootstrap classes, refactor table/cards/forms/buttons with Tailwind, test.
- attribution_radar.html: ✅ COMPLETE Remove Bootstrap classes, refactor grid/cards/charts/forms with Tailwind, test.
- attribution_summary.html: ✅ COMPLETE Remove Bootstrap classes, refactor tables/cards/forms/buttons with Tailwind, test.
- weight_check_page.html: ✅ COMPLETE Remove Bootstrap classes, refactor tables/cards/layout with Tailwind, test.
- fund_duration_details.html: ✅ COMPLETE Remove Bootstrap classes, refactor details layout/cards/tables with Tailwind, test.
- curve_details.html: ✅ COMPLETE Remove Bootstrap classes, refactor chart/data table/cards/forms with Tailwind, test.

For each template:
1. Remove all Bootstrap classes and dependencies.
2. Refactor layout and components using Tailwind utility classes as per the style guide.
3. Test for correct layout and functionality.

### 2.2 Typography Setup
2.2.1 Action: Integrate Merriweather Sans and Inter , plus Roboto Mono web fonts. ✅ COMPLETE
2.2.2 File(s): templates/base.html, static/css/style.css (or Tailwind config).
2.2.3 Details:
- Add Google Fonts <link> tags in templates/base.html.
- Configure Tailwind's theme.fontFamily or define base CSS: body { font-family: 'Inter', sans-serif; font-size: 15px; line-height: 1.5; color: #333; }, h1 { font-family: 'Merriweather Sans', sans-serif; font-size: 32px; font-weight: 700; } etc. (Section 3).

### 2.3 Color Palette Implementation
2.3.1 Action: Define the color palette for use in styles. ✅ COMPLETE
2.3.2 File(s): static/css/style.css (CSS variables) or tailwind.config.js (Tailwind theme colors).
2.3.3 Details:
- Configure Tailwind's theme.extend.colors (e.g., primary: '#E34A33', secondary: '#1F7A8C', ...) or define CSS variables (--color-primary-accent: #E34A33; etc.) based on Section 2.

## Phase 3: Core Layout Refactoring

### 3.1 Base Template Structure (base.html)
3.1.1 Action: Rebuild the main layout in templates/base.html using the new navigation structure (Section 4). ✅ COMPLETE
3.1.2 File(s): templates/base.html, static/css/style.css, static/js/main.js. ✅ COMPLETE
3.1.3 Details: ✅ COMPLETE
- Top Bar (60px): Create a <div> with fixed position, height 60px. Use Flexbox/Grid for layout: Logo, Product Name, Env Pill (left); Search, User Avatar (right). Apply neutral background, padding. (Section 4.1).
- Sidebar (220px): Create a <div> with fixed position, width 220px. Populate <ul> with navigation links (<a>) for primary sections (Time-Series, Checks & Comparisons, etc.). Apply basic styling. (Section 4.2).

- Main Content Area: Create a <main> element with `ml-[220px] pt-[60px]`.

### 3.2 Breadcrumbs
3.2.1 Action: Add a {% block breadcrumbs %}{% endblock %} placeholder in templates/base.html below the top bar. ✅ COMPLETE
3.2.2 File(s): templates/base.html. ✅ COMPLETE
3.2.3 Details: Style minimally (e.g., small font size, neutral color). Individual templates will populate this block. ✅ COMPLETE

### 3.3 Filters Drawer
3.3.1 Action: Implement the slide-in filters drawer. ✅ COMPLETE
3.3.2 File(s): templates/base.html (add <aside> structure, initially positioned off-screen right), static/css/style.css (add styles for positioning, background, shadow, transform: translateX(100%); transition: transform...;), static/js/main.js (add event listener to "Show Filters" button to toggle a class like .filters-drawer-open on the <body>, which CSS uses to apply transform: translateX(0);). (Section 4.4). ✅ COMPLETE
3.3.3 Details: HTML structure added to base.html with Tailwind classes for positioning, initial state (translate-x-full), and transitions. JS added to main.js to toggle translate-x-full class on button click. ✅ COMPLETE

## Phase 4: Component & Page Styling (Template-by-Template)

(Apply relevant actions from the style guide to each template file listed below)

### 4.1 templates/base.html
4.1.1 Layout: Implement Phase 3 changes.
4.1.2 Typography: Link web fonts, apply base body font styles (Section 3).
4.1.3 CSS: Link new CSS/Tailwind. Remove old framework links.

### 4.2 templates/index.html (Dashboard)
4.2.1 Layout: Implement Dashboard Pattern (Section 5.1). Use CSS Grid (grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-4) for metric tiles.
4.2.2 Cards: Style metric tiles: div with bg-[#F7F7F7] rounded-lg shadow-[0_0_4px_rgba(0,0,0,0.06)] p-4. (Section 1.3).
4.2.3 Typography: Apply H1/H2 styles (Section 3). Style metric name: text-base font-semibold text-[#333]. Style KPI/sparkline placeholder (large font).
4.2.4 Buttons: Style "View Details" links: a tag with bg-primary text-white px-3 py-1 rounded-md text-sm. (Section 5.1, Section 2 - Primary Accent).
4.2.5 Tables: Restyle Z-Score summary table: minimal borders (e.g., border-b border-[#E5E5E5]), row hover (hover:bg-gray-100), status indicators if applicable (Section 5.2).
4.2.6 Interactions: Apply button hover effect (Section 7). Implement skeleton loaders (Section 7).

### 4.3 templates/metric_page_js.html (Time-Series Metric Detail)
4.3.1 Layout: Ensure content is within the main content area. Use grid (grid grid-cols-1 lg:grid-cols-2 gap-4) for fund sections.
4.3.2 Cards: Wrap each fund's chart+table section in a card (div.card styled as above).
4.3.3 Typography: Apply H3 styles for fund codes. Ensure table text/chart labels use Inter/Roboto 15px (Section 3).
4.3.4 Buttons: Style toggles (use custom styled checkbox or Tailwind plugin) and "Inspect" button (Secondary accent #1F7A8C background). (Section 2, Section 7).
4.3.5 Tables: Restyle metrics tables per fund (Section 5.2). Apply conditional row highlighting (.high-z, .very-high-z) based on Z-score using status colors (Section 2).
4.3.6 Charts: Ensure JS configures charts per Section 6 (white bg, gridlines #E5E5E5, axis labels #666 12px, 2px line width, chart palette colors, tooltip style).
4.3.7 Interactions: Apply button/card hover (Section 7). Skeleton loaders for charts (Section 7). Handle empty states ({% if not fund_data %}).
4.3.8 Forms: Style Fund Group filter dropdown (Section 7).

### 4.4 templates/securities_page.html (Security Summary)
4.4.1 Layout: Main content area.
4.4.2 Cards: Wrap filter form and table in cards.
4.4.3 Typography: H2 heading, table headers (600 weight), body text (Section 3).
4.4.4 Buttons: Style "Apply Filters" (Primary), "Clear Filters" (Secondary/Outline).
4.4.5 Tables: Restyle main table: sticky header, hairline dividers (border-b border-[#E5E5E5]), row hover (hover:bg-gray-100), pagination styling (condensed, right-aligned). (Section 5.2).
4.4.6 Forms: Style search input, filter dropdowns (border border-[#CCCCCC] focus:ring-secondary), "Exclude Min=0" toggle. (Section 7).
4.4.7 Interactions: Button/card hover (Section 7). Empty state message ({% if not securities_data %}).

### 4.5 templates/security_details_page.html (Security Detail)
4.5.1 Layout: Two-column grid (lg:grid-cols-10 gap-4), left (lg:col-span-3), right (lg:col-span-7). Single column on smaller screens. (Section 5.3).
4.5.2 Cards: Style left metadata tile and right chart containers as cards.
4.5.3 Typography: H3/H5 headings, metadata lists (ul/li styled minimally), chart axis/titles (Section 3, Section 6).
4.5.4 Buttons: Style "Bloomberg YAS" (Primary), "Raise Issue" (Warning), "Add Exclusion" (Danger).
4.5.5 Charts: Ensure JS configures charts per Section 6. Style chart toolbar links (subtle text, e.g., text-sm text-secondary hover:text-primary).
4.5.6 Tables: Style Fund Holdings table: minimal borders, row hover, green/red cell backgrounds (bg-success/bg-danger with opacity). (Section 5.2). Consider wrapping in collapsible accordion if long.
4.5.7 Interactions: Button/card hover (Section 7). Skeleton loaders for charts (Section 7). Handle empty chart states.

### 4.6 templates/comparison_summary_base.html (Generic Comparison Summary)
4.6.1 Layout: Main content area.
4.6.2 Cards: Wrap filter form and table in cards.
4.6.3 Typography: H2 heading, table headers (600 weight), body text (Section 3).
4.6.4 Buttons: Style "Apply Filters" (Primary), "Clear Filters" (Secondary/Outline).
4.6.5 Tables: Restyle comparison table: sticky header, hairline dividers, row hover, pagination. Use status badges (bg-success/bg-warning) for "Same Date Range". (Section 5.2).
4.6.6 Forms: Style filter dropdowns, "Show Sold" toggle. (Section 7).
4.6.7 Interactions: Button/card hover (Section 7). Empty state message.

### 4.7 templates/comparison_details_base.html (Generic Comparison Detail)
4.7.1 Layout: Two-column grid (e.g., lg:grid-cols-3 gap-4), chart (lg:col-span-2), stats (lg:col-span-1). Single column below lg.
4.7.2 Cards: Style chart container and statistics container as cards.
4.7.3 Typography: H3 heading, stats list (ul/li), chart axis/titles (Section 3, Section 6).
4.7.4 Charts: Ensure JS configures comparison chart using Blue (#1F77B4) / Orange (#FF7F0E) and other Section 6 styles.
4.7.5 Tables: Style Fund Holdings table: minimal borders, row hover, green/red cell backgrounds. (Section 5.2).
4.7.6 Interactions: Card hover (Section 7). Skeleton loader for chart.

### 4.8 templates/exclusions_page.html
4.8.1 Layout: Main content area. Optional two-column grid (list left, form right).
4.8.2 Cards: Wrap exclusions list table and add form in cards.
4.8.3 Typography: H2/H4 headings, table/form label fonts (Section 3).
4.8.4 Buttons: Style "Remove" (Danger), "Add Exclusion" (Primary). (Section 2).
4.8.5 Tables: Restyle exclusions table (Section 5.2).
4.8.6 Forms: Restyle form inputs/selects/textarea per Section 7.
4.8.7 Interactions: Button/card hover (Section 7).

### 4.9 templates/issues_page.html
4.9.1 Layout: Main content area. Optional two-column grid (form left, list right).
4.9.2 Cards: Wrap "Raise Issue" form and "Open Issues" table in cards.
4.9.3 Typography: H2/H4 headings, table/form label fonts (Section 3).
4.9.4 Buttons: Style "Raise Issue" (Primary), "Close" (Success). (Section 2).
4.9.5 Tables: Restyle issues tables (Section 5.2). Use status badges (e.g., bg-danger for Open).
4.9.6 Forms: Restyle form inputs/selects/textarea/radio buttons per Section 7.
4.9.7 Interactions: Button/card hover (Section 7).
4.9.8 Modal Dependency: Note that the "Close Issue" modal currently relies on Bootstrap's structure and JavaScript for functionality. The modal's *content* has been styled with Tailwind, but the underlying modal mechanism is still Bootstrap. We should make a note to revisit and fully replace the modal implementation later if a complete Bootstrap removal is desired.

### 4.10 templates/curve_summary.html
4.10.1 Layout: Main content area.
4.10.2 Cards: Wrap summary table in a card.
4.10.3 Typography: H1 heading, table fonts (Section 3).
4.10.4 Buttons: Style "View Details" buttons (Secondary accent #1F7A8C). (Section 2).
4.10.5 Tables: Restyle summary table (Section 5.2). Use status badges (bg-success, bg-warning, bg-danger) based on Section 2 status colors.
4.10.6 Interactions: Button/card hover (Section 7).

### 4.11 templates/curve_details.html
4.11.1 Layout: Main content area.
4.11.2 Cards: Wrap chart and data table in cards.
4.11.3 Typography: H1 heading, table/chart fonts (Section 3, Section 6).
4.11.4 Charts: Ensure JS configures yield curve chart per Section 6.
4.11.5 Tables: Restyle data table (Section 5.2). Apply conditional row highlighting using status colors based on Z-Score.
4.11.6 Forms: Style date/history select dropdowns (Section 7).
4.11.7 Interactions: Card hover (Section 7). Skeleton loader for chart.

### 4.12 templates/maxmin_dashboard.html
4.12.1 Layout: Implement Dashboard Pattern (Section 5.1). Use CSS Grid for summary cards.
4.12.2 Cards: Style summary tiles as cards. Apply border color using status colors (Section 2) based on breach status.
4.12.3 Typography: H1 heading, card title/text styles (Section 3).
4.12.4 Buttons: Style "Max" (Danger outline), "Min" (Warning outline) details buttons.
4.12.5 Forms: Style threshold override inputs (Section 7).
4.12.6 Interactions: Button/card hover (Section 7).

### 4.13 templates/maxmin_details.html
4.13.1 Layout: Main content area.
4.13.2 Cards: Wrap details table in a card.
4.13.3 Typography: H1 heading, table fonts (Section 3).
4.13.4 Tables: Restyle breach details table (Section 5.2). Apply conditional row highlighting (Danger/Warning).
4.13.5 Interactions: Card hover (Section 7). Handle empty state.

### 4.14 templates/watchlist_page.html
4.14.1 Layout: Main content area.
4.14.2 Cards: Wrap watchlist table in a card.
4.14.3 Typography: H2 heading, table fonts (Section 3).
4.14.4 Buttons: Style "Add to Watchlist" (Success), "Clear" (Danger). Style modal buttons. (Section 2).
4.14.5 Tables: Restyle watchlist table (Section 5.2). Use status badges (Active/Cleared). JS to hide/show cleared rows/columns.
4.14.6 Forms: Style "Show Cleared" toggle. Style modal inputs/selects/textarea (Section 7).
4.14.7 Interactions: Button/card hover (Section 7). Handle empty state.

### 4.15 templates/weight_check_page.html
4.15.1 Layout: Main content area.
4.15.2 Cards: Wrap Fund/Benchmark tables in cards.
4.15.3 Typography: H1/H2 headings, table fonts (Section 3).
4.15.4 Tables: Restyle weight tables: sticky header/first column, hairline dividers, row hover. Apply conditional cell background (bg-danger opacity-low) for non-100% values. (Section 5.2).
4.15.5 Interactions: Card hover (Section 7).

### 4.16 templates/get_data.html (API Simulation/Management)
4.16.1 Layout: Main content area. Use clear headings/sections.
4.16.2 Cards: Wrap File Status, Run Form, Schedules, Audit sections in cards.
4.16.3 Typography: H2/H4 headings, form labels, table fonts (Section 3).
4.16.4 Buttons: Restyle all buttons using primary (#E34A33), secondary (#1F7A8C), success, warning, info, danger colors as appropriate. (Section 2).
4.16.5 Tables: Restyle File Status and Schedules tables (Section 5.2). Use status badges.
4.16.6 Forms: Restyle all inputs, selects, radio buttons, checkboxes per Section 7.
4.16.7 Interactions: Button/card hover (Section 7). Handle progress bar styling.

### 4.17 templates/attribution_summary.html
4.17.1 Layout: Main content area.
4.17.2 Cards: Wrap filter form and tables in cards.
4.17.3 Typography: H1/H3 headings, table fonts (Section 3).
4.17.4 Buttons: Style level toggle buttons (e.g., segmented control), "Apply Filters" (Primary).
4.17.5 Tables: Restyle Benchmark/Portfolio tables (Section 5.2).
4.17.6 Forms: Style filter dropdowns, date range slider controls per Section 7.
4.17.7 Interactions: Button/card hover (Section 7).

### 4.18 templates/attribution_security_page.html
4.18.1 Layout: Main content area.
4.18.2 Cards: Wrap filter form and table in cards.
4.18.3 Typography: H2 heading, table fonts (Section 3).
4.18.4 Buttons: Style filter form buttons/toggles.
4.18.5 Tables: Restyle security-level table: sticky header, hairline dividers, row hover, pagination. (Section 5.2).
4.18.6 Forms: Style filter inputs/selects/toggles per Section 7.
4.18.7 Interactions: Button/card hover (Section 7). Handle empty state.

### 4.19 templates/attribution_radar.html
4.19.1 Layout: Main content area. Grid for charts.
4.19.2 Cards: Wrap filter form and chart containers in cards.
4.19.3 Typography: H1/H3 headings, chart title fonts (Section 3, Section 6).
4.19.4 Charts: Ensure JS configures radar charts per Section 6 aesthetics.
4.19.5 Forms: Style filter dropdowns, level toggle, date slider controls per Section 7.
4.19.6 Interactions: Button/card hover (Section 7). Skeleton loaders for charts.

### 4.20 templates/attribution_charts.html
4.20.1 Layout: Main content area. Grid for charts.
4.20.2 Cards: Wrap filter form and chart containers in cards.
4.20.3 Typography: H1/H3 headings, chart title/axis fonts (Section 3, Section 6).
4.20.4 Charts: Ensure JS configures bar/line charts per Section 6 aesthetics.
4.20.5 Forms: Style filter dropdowns, toggle switch, date slider controls per Section 7.
4.20.6 Interactions: Button/card hover (Section 7). Skeleton loaders for charts.

### 4.21 templates/error.html
4.21.1 Layout: Main content area.
4.21.2 Typography: H4 heading, paragraph styles (Section 3).
4.21.3 Buttons: Style "Go to Dashboard" button (Primary).
4.21.4 Cards: Wrap error message in a card, use Danger status background/border. (Section 2).

### 4.22 templates/fund_detail_page.html
4.22.1 Layout: Main content area. Use grid for charts (grid grid-cols-1 lg:grid-cols-2 gap-4).
4.22.2 Cards: Wrap each chart in a card.
4.22.3 Typography: H1 heading, chart title/axis fonts (Section 3, Section 6).
4.22.4 Charts: Ensure JS configures charts per Section 6 aesthetics.
4.22.5 Forms: Style toggle switches per Section 7.
4.22.6 Interactions: Card hover (Section 7). Skeleton loaders for charts. Handle empty state.

### 4.23 templates/inspect_results.html
4.23.1 Layout: Main content area. Two-column grid (lg:grid-cols-2 gap-4).
4.23.2 Cards: Wrap tables and chart in cards.
4.23.3 Typography: H1/H2/H3 headings, table fonts, chart fonts (Section 3, Section 6).
4.23.4 Buttons: Style "Back" button (Secondary).
4.23.5 Tables: Restyle contributor/detractor tables (Section 5.2).
4.23.6 Charts: Ensure JS configures contribution bar chart (vertical bars, green/red status colors from Section 2).
4.23.7 Interactions: Button/card hover (Section 7). Skeleton loader for chart. Handle empty states.

## Phase 5: Chart & Interaction Refinement

### 5.1 Chart Styling (static/js/modules/charts/timeSeriesChart.js, other chart JS)
5.1.1 Action: Update Chart.js configurations to match the visual style (Section 6).
5.1.2 File(s): JavaScript files creating charts (static/js/modules/charts/timeSeriesChart.js, static/js/modules/ui/chartRenderer.js, etc.).
5.1.3 Details: Set white background, #E5E5E5 gridlines, 12px #666 axis labels, 2px line width, chart palette colors (ensure Blue/Orange for comparisons), styled tooltips (white card, accent border).
    **Note:** The actual rendering of charts within styled cards relies on the JavaScript in `static/js/modules/ui/chartRenderer.js` being updated to create the necessary card structure (e.g., `<div class="bg-[#F7F7F7] rounded-lg shadow-[0_0_4px_rgba(0,0,0,0.06)] p-4 hover:shadow-md transition-shadow">...</div>`) when it inserts the charts into the DOM.

### 5.2 Micro-interactions & States
5.2.1 Action: Implement hover effects, loading states, empty states (Section 7).
5.2.2 File(s): static/css/style.css, static/js/main.js, relevant templates.
5.2.3 Details: Add CSS for card hover (raise/shadow). Replace spinners with CSS skeleton loaders. Add empty state messages/illustrations ({% if not data %}).
   *Note: Implement sidebar collapse/expand toggle functionality here.*
  *Note: Adding Feather icons and implementing active link styling (e.g., `border-l-4 border-primary`) will be addressed in later component styling phases.*
  *Note: The JavaScript toggle for sidebar collapse/expand will be implemented in Phase 5 (Interaction Refinement).*
## Phase 6: Cleanup & Testing

### 6.1 Remove Old Styles
6.1.1 Action: Delete unused CSS/classes.

### 6.3 Offline Test
6.3.1 Action: Run flask run, disconnect network, access http://127.0.0.1:5000, verify rendering and functionality.

**This more detailed plan should give the AI assistant precise instructions for refactoring each template according to the style guide.**