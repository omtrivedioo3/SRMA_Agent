# ============================================================================
# Reproducible R Meta-Analysis Script — Run ID: run-20261007-093214
# Outcome: Reduce stroke or systemic embolism
# Generated per PRISMA 2020 & Cochrane Handbook specifications
# ============================================================================
library(meta)
library(metafor)

m_data <- data.frame(
  study  = c("Khachatryan et al. (2022). PMID:36399317"),
  n_e    = c(40744),
  mean_e = c(75.3),
  sd_e   = c(11.2),
  n_c    = c(40744),
  mean_c = c(75.3),
  sd_c   = c(11.2)
)

m_res <- metacont(
  n.e = n_e, mean.e = mean_e, sd.e = sd_e,
  n.c = n_c, mean.c = mean_c, sd.c = sd_c,
  data = m_data, studlab = study,
  sm = "SMD",
  method.tau = "REML", random = TRUE
)
summary(m_res)
forest(m_res, layout = "Cochrane", col.square = "navy", prediction = TRUE)