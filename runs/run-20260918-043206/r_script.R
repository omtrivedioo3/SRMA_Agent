# ============================================================================
# Reproducible R Meta-Analysis Script — Run ID: run-20260918-043206
# Outcome: Mortality
# Generated per PRISMA 2020 & Cochrane Handbook specifications
# ============================================================================
library(meta)
library(metafor)

m_data <- data.frame(
  study   = c("Einstein et al. (2020). PMID:37306039", "Torp-Pedersen (2017). NCT02974920", "Bydgoszczy et al. (2022). PMID:34096012", "Silesia et al. (2005). NCT01863134", "Health (2009). PMID:22396581", "H et al. (2015)", "AstraZeneca et al. (2011). NCT01360047"),
  event_e = c(100, 50, 10, 10, 5, 2875, 1000),
  n_e     = c(600, 500, 200, 200, 100, 1492, 100000),
  event_c = c(120, 60, 10, 12, 6, 2875, 1000),
  n_c     = c(600, 500, 200, 200, 100, 1494, 100000)
)

# Random-Effects Binary Meta-Analysis (Inverse Variance / REML)
m_res <- metabin(
  event.e = event_e, n.e = n_e,
  event.c = event_c, n.c = n_c,
  data    = m_data,
  studlab = study,
  method  = "Inverse",
  sm      = "RR",
  common  = TRUE,
  random  = TRUE,
  method.tau = "REML",
  hakn    = TRUE
)

summary(m_res)
forest(m_res, layout = "Cochrane", col.square = "navy", prediction = TRUE, print.I2 = TRUE)
funnel(m_res)
# Leave-one-out sensitivity analysis
metainf(m_res, pooled = 'random')