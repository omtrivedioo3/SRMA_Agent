# ============================================================================
# Reproducible R Meta-Analysis Script — Run ID: run-20260921-073015
# Outcome: Incidence of severe (Grade 3 or higher) cytokine release syndrome
# Generated per PRISMA 2020 & Cochrane Handbook specifications
# ============================================================================
library(meta)
library(metafor)

# Fewer than 2 studies reported comparative arm-level event counts or means/SDs
# in the retrieved abstracts. Populate m_data below after full-text extraction:
m_data <- data.frame(
  study   = c("Study_1", "Study_2"),
  event_e = c(NA, NA), n_e = c(NA, NA),
  event_c = c(NA, NA), n_c = c(NA, NA)
)