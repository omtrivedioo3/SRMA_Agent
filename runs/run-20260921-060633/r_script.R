# ============================================================================
# Reproducible R Meta-Analysis Script — Run ID: run-20260921-060633
# Outcome: Mortality
# Generated per PRISMA 2020 & Cochrane Handbook specifications
# ============================================================================
library(meta)
library(metafor)

m_data <- data.frame(
  study   = c("Trust et al. (2012)", "M.D. et al. (2000)", "University et al. (2021). PMID:26163482", "University et al. (2012). NCT01815008", "Hospital et al. (2025)", "Medicure et al. (2010). PMID:11419425", "University et al. (2013). PMID:20129551"),
  event_e = c(10, 163, 10, 10, 12, 100, 10),
  n_e     = c(100, 2000, 100, 100, 250, 1000, 100),
  event_c = c(10, 163, 10, 10, 15, 110, 10),
  n_c     = c(100, 2000, 100, 100, 250, 1000, 100)
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