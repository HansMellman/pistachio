import pandas as pd
from config import COLUMNS_TO_BLANK_BEFORE_EXPORT, export_filepath


def export_advanced_html(
    df, filename, columns, title="Data Table", row_filter=None, page_len=100
):
    """
    Export df[columns] to an HTML file with DataTables (using the searchbuilder extension).
    """
    working_df = df.copy()
    if row_filter is not None:
        working_df = working_df[row_filter].copy()

    working_df = working_df[columns]

    # Clean NaN values in configured columns for proper HTML sorting
    clean_cols = [c for c in COLUMNS_TO_BLANK_BEFORE_EXPORT if c in working_df.columns]
    working_df[clean_cols] = working_df[clean_cols].fillna("")

    # Define a safe formatter that leaves non-numeric values unchanged
    def safe_format(fmt_func):
        def wrapped(val):
            try:
                return fmt_func(val)
            except Exception:
                return val

        return wrapped

    # Apply baseball‑style formatting
    fmt = {}
    for col in working_df.columns:
        if col in (
            "best",
            "bestP",
            "war_hitting",
            "sp_war",
            "rp_war",
            "sp_warP",
            "rp_warP",
            "DH",
            "C",
            "CF",
            "RF",
            "LF",
            "SS",
            "2B",
            "3B",
            "1B",
            "DHP",
            "1BP",
            "2BP",
            "3BP",
            "SSP",
            "LFP",
            "CFP",
            "RFP",
            "CP",
        ):
            fmt[col] = safe_format("{:.1f}".format)
        elif col.endswith("_def"):
            fmt[col] = safe_format("{:.1f}".format)
        elif "wOBA" in col:
            fmt[col] = safe_format("{:.3f}".format)
        elif col in ("pWOBA", "pWOBAR", "pWOBAL"):
            fmt[col] = safe_format("{:.3f}".format)
        elif "wRC+" in col:
            fmt[col] = safe_format("{:.0f}".format)

    styled = working_df.style.format(fmt)
    html_table = styled.to_html(index=False, escape=False)
    # Ensure the table has the id DataTables expects:
    html_table = html_table.replace("<table ", '<table id="data" ', 1)

    full = HTML_DARK_TEMPLATE.format(title=title, table=html_table, page_len=page_len)
    path = export_filepath / filename
    with open(path, "w", encoding="utf-8") as f:
        f.write(full)
    print(f"✅ Exported {title} → {path}")


def export_hitters(df):
    """
    Wrapper to export the hitters page.
    """
    cols = [
        "name",
        "org",
        "age",
        "pa",
        "best",
        "pos",
        "wRC+",
        "wOBA",
        "wOBAR",
        "wOBAL",
        "DH",
        "C",
        "CF",
        "RF",
        "LF",
        "SS",
        "2B",
        "3B",
        "1B",
        "wOBAP",
        "flag",
    ]
    filt = df["wOBA"] > 0.270
    export_advanced_html(
        df,
        filename="hitters.html",
        columns=cols,
        title="Hitters",
        row_filter=filt,
        page_len=100,
    )


EXPORT_PAGES = [
    {
        "filename": "hitters.html",
        "title": "Hitters",
        "columns": [
            "name",
            "org",
            "minor",
            "age",
            "pa",
            "best",
            "bestP",
            "pos",
            "field",
            "wRC+",
            "wOBA",
            "wOBAR",
            "wOBAL",
            "wOBAP",
            "DH",
            "1B",
            "2B",
            "3B",
            "SS",
            "LF",
            "CF",
            "RF",
            "C",
            "flag",
        ],
        "filter": lambda df: df["wOBAP"] > 0.200,
        "page_len": 100,
    },
    {
        "filename": "pitchers.html",
        "title": "Pitchers",
        "columns": [
            "name",
            "org",
            "minor",
            "age",
            "ip",
            "sp_war",
            "rp_war",
            "pwOBA",
            "pwOBAR",
            "pwOBAL",
            "sp_warP",
            "rp_warP",
            "pwOBAP",
            "flag",
        ],
        "filter": lambda df: df["pwOBAP"] < 1.000,
        "page_len": 100,
    },
    {
        "filename": "hit_prospects.html",
        "title": "Hitter prospects",
        "columns": [
            "name",
            "org",
            "minor",
            "age",
            "pa",
            "best",
            "bestP",
            "posP",
            "field",
            "wOBA",
            "wOBAR",
            "wOBAL",
            "wOBAP",
            "DHP",
            "1BP",
            "2BP",
            "3BP",
            "SSP",
            "LFP",
            "CFP",
            "RFP",
            "CP",
            "Cfram",
            "flag",
        ],
        "filter": lambda df: df["wOBAP"] > 0.200,
        "page_len": 100,
    },
    # More pages can be added here
]


def export_html_pages(df):
    """
    Export multiple pages using the EXPORT_PAGES definitions.
    """
    for page in EXPORT_PAGES:
        filt = page["filter"](df) if page.get("filter") else None
        export_advanced_html(
            df=df,
            filename=page["filename"],
            columns=page["columns"],
            title=page["title"],
            row_filter=filt,
            page_len=page.get("page_len", 100),
        )


# ------------------------------------------------------------------
# Organization report export (multi-table HTML)
# ------------------------------------------------------------------


def _safe_format(fmt_func):
    def wrapped(val):
        try:
            return fmt_func(val)
        except Exception:
            return val

    return wrapped


def _pct_formatter(val):
    try:
        if pd.isna(val):
            return ""
        return f"{float(val) * 100:.1f}%"
    except Exception:
        return val


def _df_to_report_table(df: pd.DataFrame, table_id: str) -> str:
    """
    Convert a dataframe to an HTML table for the org report page.
    """
    working_df = df.copy()

    # Define formatters
    fmt = {}
    for col in working_df.columns:
        if (
            col in ("pos_WAR", "sp_war", "rp_war")
            or col.endswith("_war")
            or col.endswith("_WAR")
        ):
            fmt[col] = _safe_format("{:.1f}".format)
        elif col in ("wOBA", "wOBA_vs", "pwOBA", "pwOBAR", "pwOBAL", "wOBAR", "wOBAL"):
            fmt[col] = _safe_format("{:.3f}".format)
        elif col == "wRC+":
            fmt[col] = _safe_format("{:.0f}".format)
        elif col in ("BB%", "HR%", "K%"):
            fmt[col] = _pct_formatter
        elif col in ("age", "pa", "ip", "minor", "slot"):
            fmt[col] = _safe_format("{:.0f}".format)

    styled = working_df.style.format(fmt)
    html_table = styled.to_html(index=False, escape=False)
    html_table = html_table.replace(
        "<table ", f'<table id="{table_id}" class="report-table" ', 1
    )
    return html_table


HTML_ORG_REPORT_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>{title}</title>

  <!-- DataTables core -->
  <link rel="stylesheet" href="https://cdn.datatables.net/1.13.4/css/jquery.dataTables.min.css"/>
  <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap" rel="stylesheet"/>

  <script src="https://code.jquery.com/jquery-3.5.1.min.js"></script>
  <script src="https://cdn.datatables.net/1.13.4/js/jquery.dataTables.min.js"></script>

  <style>
    body {{
      background:#1c1c1c;
      color:#e0e0e0;
      margin:0;
      padding:1.25rem;
      font-family: 'Roboto', sans-serif;
    }}

    h1 {{
      margin: 0 0 0.5rem 0;
      font-size: 1.4rem;
      font-weight: 600;
    }}

    .sub {{
      margin: 0 0 1.25rem 0;
      font-size: 0.9rem;
      opacity: 0.85;
    }}

    .section {{
      margin: 1.25rem 0 2rem 0;
      padding-top: 0.5rem;
      border-top: 1px solid rgba(255,255,255,0.08);
    }}

    .section h2 {{
      margin: 0 0 0.75rem 0;
      font-size: 1.05rem;
      font-weight: 500;
    }}

    .summary {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 0.75rem;
      margin: 0.75rem 0 1rem 0;
    }}

    .card {{
      background: #262626;
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 10px;
      padding: 0.75rem 0.9rem;
    }}

    .card .k {{
      font-size: 0.8rem;
      opacity: 0.8;
      margin-bottom: 0.25rem;
    }}

    .card .v {{
      font-size: 1.1rem;
      font-weight: 600;
    }}

    table.dataTable {{
      background:#1c1c1c;
      color:#e0e0e0;
      font-size:0.82rem;
    }}

    table.dataTable thead th {{
      background:#2f2f2f;
      color:#e0e0e0;
    }}

    table.dataTable tbody tr:nth-child(odd)  {{ background:#262626; }}
    table.dataTable tbody tr:nth-child(even) {{ background:#1e1e1e; }}
    table.dataTable tbody tr:hover {{ background: rgba(255,255,255,0.05); }}

    /* remove the "Show X entries" / search bar for small report tables */
    div.dataTables_length, div.dataTables_filter, div.dataTables_info, div.dataTables_paginate {{
      display: none;
    }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <p class="sub">{subtitle}</p>

  <div class="summary">
    {summary_cards}
  </div>

  {sections}

<script>
$(document).ready(function(){{
  $('table.report-table').each(function(){{
    $(this).DataTable({{
      paging: false,
      searching: false,
      info: false,
      ordering: true,
      order: []
    }});
  }});
}});
</script>
</body>
</html>
"""


def export_org_report(df: pd.DataFrame, org_abbr: str | None = None) -> None:
    """
    Build and export a single-page org report with:
      - Starting lineup vs RHP and vs LHP (one-player-per-position)
      - Batting order vs RHP and vs LHP
      - 5-man rotation and 8-man bullpen
    """
    from config import team_managed
    from org_report import (
        build_batting_order,
        build_pitching_staff,
        build_starting_lineup,
    )

    org = org_abbr or team_managed

    lineup_r = build_starting_lineup(df, org_abbr=org, side="R")
    lineup_l = build_starting_lineup(df, org_abbr=org, side="L")

    order_r = build_batting_order(lineup_r, side="R")
    order_l = build_batting_order(lineup_l, side="L")

    rotation, bullpen = build_pitching_staff(df, org_abbr=org, n_sp=5, n_rp=8)

    # Summaries
    def _sum_numeric(series):
        try:
            return float(pd.to_numeric(series, errors="coerce").fillna(0).sum())
        except Exception:
            return 0.0

    sum_lineup_r = _sum_numeric(lineup_r.get("pos_WAR"))
    sum_lineup_l = _sum_numeric(lineup_l.get("pos_WAR"))
    sum_rot = _sum_numeric(rotation.get("sp_war"))
    sum_pen = _sum_numeric(bullpen.get("rp_war"))

    summary_cards = "\n".join(
        [
            f'<div class="card"><div class="k">Org</div><div class="v">{org}</div></div>',
            f'<div class="card"><div class="k">Lineup WAR (vs RHP)</div><div class="v">{sum_lineup_r:.1f}</div></div>',
            f'<div class="card"><div class="k">Lineup WAR (vs LHP)</div><div class="v">{sum_lineup_l:.1f}</div></div>',
            f'<div class="card"><div class="k">Rotation WAR (Top 5)</div><div class="v">{sum_rot:.1f}</div></div>',
            f'<div class="card"><div class="k">Bullpen WAR (Top 8)</div><div class="v">{sum_pen:.1f}</div></div>',
        ]
    )

    # Column ordering / selection for readability
    lineup_cols = [
        "pos",
        "name",
        "age",
        "minor",
        "pa",
        "pos_WAR",
        "wOBA_vs",
        "wRC+",
        "field",
    ]
    order_cols = ["slot", "pos", "name", "wOBA_vs", "wRC+"]
    rot_cols = ["name", "age", "minor", "ip", "sp_war", "pwOBA", "pwOBAR", "pwOBAL"]
    pen_cols = ["name", "age", "minor", "ip", "rp_war", "pwOBA", "pwOBAR", "pwOBAL"]

    lineup_r_disp = lineup_r[[c for c in lineup_cols if c in lineup_r.columns]]
    lineup_l_disp = lineup_l[[c for c in lineup_cols if c in lineup_l.columns]]
    order_r_disp = order_r[[c for c in order_cols if c in order_r.columns]]
    order_l_disp = order_l[[c for c in order_cols if c in order_l.columns]]
    rotation_disp = rotation[[c for c in rot_cols if c in rotation.columns]]
    bullpen_disp = bullpen[[c for c in pen_cols if c in bullpen.columns]]

    sections_html = []
    sections_html.append(
        '<div class="section"><h2>Starting lineup (vs RHP)</h2>'
        + _df_to_report_table(lineup_r_disp, "lineup_r")
        + "</div>"
    )
    sections_html.append(
        '<div class="section"><h2>Batting order (vs RHP)</h2>'
        + _df_to_report_table(order_r_disp, "order_r")
        + "</div>"
    )
    sections_html.append(
        '<div class="section"><h2>Starting lineup (vs LHP)</h2>'
        + _df_to_report_table(lineup_l_disp, "lineup_l")
        + "</div>"
    )
    sections_html.append(
        '<div class="section"><h2>Batting order (vs LHP)</h2>'
        + _df_to_report_table(order_l_disp, "order_l")
        + "</div>"
    )
    sections_html.append(
        '<div class="section"><h2>Rotation (Top 5 SP)</h2>'
        + _df_to_report_table(rotation_disp, "rotation")
        + "</div>"
    )
    sections_html.append(
        '<div class="section"><h2>Bullpen (Top 8 RP)</h2>'
        + _df_to_report_table(bullpen_disp, "bullpen")
        + "</div>"
    )

    full = HTML_ORG_REPORT_TEMPLATE.format(
        title=f"{org} Org Report",
        subtitle="Generated by Pistachio (projected lineup + staff + batting orders).",
        summary_cards=summary_cards,
        sections="\n".join(sections_html),
    )

    path = export_filepath / "org_report.html"
    with open(path, "w", encoding="utf-8") as f:
        f.write(full)

    print(f"✅ Exported Org Report → {path}")


# ------------------------------------------------------------------
# Advanced DataTables HTML export (dark theme, compact, SearchBuilder)
# ------------------------------------------------------------------

HTML_DARK_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>{title}</title>
  <!-- DataTables core & extensions -->
  <link rel="stylesheet" href="https://cdn.datatables.net/1.13.4/css/jquery.dataTables.min.css"/>
  <link rel="stylesheet" href="https://cdn.datatables.net/searchbuilder/1.4.0/css/searchBuilder.dataTables.min.css"/>
  <link rel="stylesheet" href="https://cdn.datatables.net/fixedheader/3.3.2/css/fixedHeader.dataTables.min.css"/>
  <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap" rel="stylesheet"/>
  <script src="https://code.jquery.com/jquery-3.5.1.min.js"></script>
  <script src="https://cdn.datatables.net/1.13.4/js/jquery.dataTables.min.js"></script>
  <script src="https://cdn.datatables.net/searchbuilder/1.4.0/js/dataTables.searchBuilder.min.js"></script>
  <script src="https://cdn.datatables.net/fixedheader/3.3.2/js/dataTables.fixedHeader.min.js"></script>

  <style>
    /* ----- Dark theme & compact table ----- */
    body {{
      background:#1c1c1c; color:#e0e0e0; margin:0; padding:1rem; font-family:Arial,Helvetica,sans-serif;
      font-family: 'Roboto', sans-serif;
    }}
    table.dataTable {{
      background:#1c1c1c; color:#e0e0e0; font-size:0.8rem;
      font-family: 'Roboto', sans-serif;
    }}
    /* zebra striping with dark tones */
    table.dataTable tbody tr:nth-child(odd)  {{ background:#262626; }}
    table.dataTable tbody tr:nth-child(even) {{ background:#1e1e1e; }}
    /* subtle hover effect */
    table.dataTable tbody tr:hover {{ background: rgba(255,255,255,0.05); }}
    /* header */
    table.dataTable thead th {{
      background:#2f2f2f; color:#e0e0e0;
      box-shadow: 0 2px 4px rgba(0,0,0,0.5);
    }}

    /* inline top controls (search builder, length, filter) */
    #data-searchBuilderContainer,
    div.dataTables_length,
    div.dataTables_filter {{
      display: inline-block;
      vertical-align: middle;
      margin-right: 1rem;
    }}
    /* remove "Custom Search Builder" title */
    #data-searchBuilderContainer .dtsb-header {{
      display: none;
    }}
    /* hide the SearchBuilder title text */
    #data-searchBuilderContainer .dtsb-title {{
      display: none !important;
    }}

    /* style length selector and search input for visibility */
    div.dataTables_length label,
    div.dataTables_filter label {{
      color: #e0e0e0;
    }}
    div.dataTables_length select,
    div.dataTables_filter input {{
      color: #e0e0e0;
      background: #2f2f2f;
      border: none;
    }}
    /* header row layout */
    .header-row {{
      display: flex;
      align-items: center;
      font-size: 1rem;
      margin-bottom: 1rem;
    }}
    .header-row h2 {{
      margin: 0;
      font-size: 1rem;
      font-weight: normal;
      color: #e0e0e0;
    }}
    #header-controls {{
      margin-left: 1rem;
    }}
  </style>
</head>
<body>
  <div class="header-row">
    <h2>{title}</h2>
    <div id="header-controls"></div>
  </div>
  {table}
<script>
$.fn.dataTable.ext.order['numeric-empty-last-asc'] = function(settings, col) {{
    return this.api().column(col, {{order:'index'}}).nodes().map(function(td) {{
        var v = parseFloat($(td).text());
        return isNaN(v) ? Infinity : v;
    }});
}};
$.fn.dataTable.ext.order['numeric-empty-last-desc'] = function(settings, col) {{
    return this.api().column(col, {{order:'index'}}).nodes().map(function(td) {{
        var v = parseFloat($(td).text());
        return isNaN(v) ? -Infinity : v;
    }});
}};
$(document).ready(function(){{
    var ascCols = ['pwOBA','pwOBAR','pwOBAL'];
    var descCols = ['sp_war','rp_war'];
    var numDefs = ascCols.map(function(name) {{
        return {{
            targets: $('#data thead th').filter(function() {{ return $(this).text() === name; }}).index(),
            orderDataType: 'numeric-empty-last-asc',
            orderSequence: ['asc','desc']
        }};
    }}).concat(descCols.map(function(name) {{
        return {{
            targets: $('#data thead th').filter(function() {{ return $(this).text() === name; }}).index(),
            orderDataType: 'numeric-empty-last-desc',
            orderSequence: ['desc','asc']
        }};
    }}));
  $('#data').DataTable({{
      dom: 'Qlfrtip',            // Q = SearchBuilder, l = length selector, f = search bar, r = processing, t = table, i = info, p = paging
      pageLength: {page_len},
      ordering: true,
      searching: true,
      paging: true,
      fixedHeader: true,
      stripeClasses: ['odd', 'even'],
      searchBuilder: {{ }},
      columnDefs: [ {{ targets: 0, visible: false }} ].concat(numDefs)
  }});
      // move SearchBuilder UI into header controls
      $('#data-searchBuilderContainer').appendTo('#header-controls');
      // rename the add button
      $('.dtsb-add').text('Add search filter');
}});
</script>
</body>
</html>
"""
