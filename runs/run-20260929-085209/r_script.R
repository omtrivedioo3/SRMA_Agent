# ============================================================================
# Reproducible R Meta-Analysis Script — Run ID: run-20260929-085209
# Outcome: Incidence and risk of Cytokine Release Syndrome (CRS)
# Generated per PRISMA 2020 & Cochrane Handbook specifications
# ============================================================================
library(meta)
library(metafor)

m_data <- data.frame(
  study   = c("Russia (2025). NCT06721598", "deng (2025)", "Dou (2026). NCT07575919"),
  event_e = c(20, 20, 5),
  n_e     = c(100, 100, 10),
  event_c = c(25, 30, 5),
  n_c     = c(100, 100, 10)
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