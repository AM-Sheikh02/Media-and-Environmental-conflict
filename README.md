# Media and Environmental Conflict

Data pipeline for analyzing media coverage of environmental conflicts
(droughts, wildfires, mining disputes, illegal logging, wildlife trade,
pollution, and conservation disputes) using the GDELT database.

Built to support the chapter "Media Representation and Environmental
Conflict: Narratives, Power, and Public Engagement in the Anthropocene."

## What it does

- Pulls recent news articles by environmental conflict category via the
  GDELT 2.0 Doc API
- Pulls multi-year coverage volume and tone data via GDELT's GKG
  BigQuery dataset
- Generates visualizations: coverage-over-time line chart, small
  multiples by category, and total coverage by category
