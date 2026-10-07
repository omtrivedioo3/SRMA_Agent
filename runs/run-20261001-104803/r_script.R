# ============================================================================
# Reproducible R Meta-Analysis Script — Run ID: run-20261001-104803
# Outcome: Cytokine Release Syndrome (CRS)
# Generated per PRISMA 2020 & Cochrane Handbook specifications
# ============================================================================
library(meta)
library(metafor)

# Single-Arm Proportional Meta-Analysis (Logit Transformation)
m_prop_data <- data.frame(
  study = c("Neelapu et al. (2017). PMID:29226797", "Raje et al. (2019). PMID:31042825"),
  event = c(43, 25),
  n     = c(101, 33)
)
m_prop <- metaprop(event = event, n = n, studlab = study, data = m_prop_data, sm = 'PLOGIT', method.tau = 'REML')
summary(m_prop)
forest(m_prop, layout = "Cochrane", col.square = "navy")