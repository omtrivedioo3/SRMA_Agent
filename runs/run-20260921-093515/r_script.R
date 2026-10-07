# ============================================================================
# Reproducible R Meta-Analysis Script — Run ID: run-20260921-093515
# Outcome: Risk and severity of Cytokine Release Syndrome (CRS)
# Generated per PRISMA 2020 & Cochrane Handbook specifications
# ============================================================================
library(meta)
library(metafor)

m_data <- data.frame(
  study   = c("Immunology et al. (2020). NCT04499573", "Ltd. et al. (2026). NCT07360288", "University (2022). NCT05691153", "University et al. (2026). NCT07443137", "Center et al. (2024). PMID:39441941", "Center et al. (2012)", "University (2025)", "University et al. (2025)", "Inc. et al. (2024). NCT06248086"),
  event_e = c(10, 5, 5, 10, 15, 5, 5, 30, 15),
  n_e     = c(10, 10, 10, 10, 30, 10, 10, 60, 90),
  event_c = c(10, 5, 5, 10, 15, 5, 5, 30, 15),
  n_c     = c(10, 10, 10, 10, 30, 10, 10, 60, 90)
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