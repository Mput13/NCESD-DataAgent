# Phase 2 Golden Coverage Matrix

Generated: 2026-05-10T13:02:27Z  
Total cases: 20  
Unresolved gaps: 0  

## Qdrant Server

- Collection: phase1_source_cards
- Vector count: 36321
- Status: ready
- Verified at: 2026-05-10T11:55:50Z

## Coverage Table

| Case ID | Category | Source Family | Source ID | Expected Terminal Outcome | Required Adapter | Filters Summary | Artifact Expectations | Missing Data Evidence |
|---------|----------|---------------|-----------|--------------------------|-----------------|-----------------|----------------------|----------------------|
| GC-001 | simple | world_bank | NY.GDP.MKTP.CD | needs_clarification | world_bank_adapter | geography=Russia; period=2024; indicator=GDP | IntentArtifact with metric=GDP, geography=Russia, period=2024 / SourceCandidateCard for FedStat GDP and World Bank GDP / | Clarification required: two valid sources (FedStat rubles vs World Bank USD/PPP) offer different methodologies; extracti |
| GC-002 | simple | fedstat | fedstat_gdp_ppp | passed | fedstat_adapter | geography=Russia; indicator=ВВП по ППС | IntentArtifact with explicit FedStat source preference / SourceCandidateCard for FedStat PPP GDP indicators / CoverageRe | — |
| GC-003 | comparative | world_bank | NY.GDP.MKTP.KD.ZG | passed | world_bank_adapter | geography=['BRA', 'RUS', 'IND', 'CHN', 'ZAF']; periods=['2015', '2016', '2017', '2018', '2019', '2020', '2021', '2022', '2023', '2024']; indicator=GDP growth | ResearchDesignArtifact listing countries, indicator, and annual period / World Bank SourceCandidateCard with indicator c | — |
| GC-004 | comparative | world_bank | FP.CPI.TOTL.ZG | passed | world_bank_adapter | geography=['RUS', 'KAZ', 'CHN']; indicator=CPI inflation | IntentArtifact with latest_available period policy / World Bank CPI/inflation SourceCandidateCard / CoverageReport ident | — |
| GC-005 | research | world_bank | SP.URB.TOTL.IN.ZS,SP.DYN.TFRT.IN | passed | world_bank_adapter | indicator=urbanization,fertility | ResearchDesignArtifact with hypothesis, dimensions, indicators, and join keys / Two or more World Bank SourceCandidateCa | — |
| GC-006 | research | fedstat | fedstat_real_income_russia | needs_clarification | fedstat_adapter | geography=Russia; indicator=реальные доходы населения | ResearchDesignArtifact with possible income, CPI/deflator, wage, and employment branches / FedStat and CKAN candidate so | Clarification required: multiple income-concept candidates exist (nominal, real disposable, per-capita) and the requeste |
| GC-007 | derived_metric | fedstat | fedstat_real_disposable_income | passed | fedstat_adapter | geography=Russia; indicator=реальные располагаемые доходы; base_year=2014 | ResearchDesignArtifact with formula inputs and base-year policy / SourceCandidateCards for nominal income and price defl | — |
| GC-008 | derived_metric | world_bank | NY.GDP.MKTP.KD | passed | world_bank_adapter | geography=['ARM', 'BLR', 'KAZ', 'KGZ', 'RUS']; indicator=GDP constant; normalize=first_available_year_100 | ResearchDesignArtifact with country set and normalization rule / World Bank GDP candidate / CoverageReport with first no | — |
| GC-009 | ambiguous | world_bank | FP.CPI.TOTL.ZG | needs_clarification | world_bank_adapter | — | IntentArtifact with missing geography, period, frequency, and inflation concept / Clarification question with concrete o | Clarification required: geography, period, frequency, and inflation concept are all missing; no source can be selected a |
| GC-010 | ambiguous | fedstat | fedstat_regional_income | needs_clarification | fedstat_adapter | — | IntentArtifact with missing country scope, income concept, period, and units / Optional candidate preview limited to sou | Clarification required: the request does not specify country, income concept, period, or units; FedStat regional income  |
| GC-011 | no_data | world_bank | FP.CPI.TOTL.ZG | not_found | world_bank_adapter | geography=PRK; period=2024; indicator=inflation | AttemptedSourceLog for World Bank and CKAN / RejectionReason entries for missing or insufficient coverage / NoDataExplan | World Bank does not publish CPI/inflation data for North Korea (PRK) for 2024; the indicator FP.CPI.TOTL.ZG has no row f |
| GC-012 | no_data | fedstat | fedstat_trade_russia_kazakhstan | not_found | ckan_adapter | geography=['Russia', 'Kazakhstan']; periods=['2010', '2011', '2012', '2013', '2014', '2015', '2016', '2017', '2018', '2019', '2020', '2021', '2022', '2023', '2024', '2025']; indicator=товарооборот | AttemptedSourceLog for FedStat and World Bank local dumps / CKAN discovery candidate list if available / NoDataExplanati | Local FedStat dumps do not contain bilateral goods-level trade data for Russia-Kazakhstan 2010-2025. World Bank WITS/tra |
| GC-013 | simple | ckan | 57319 | passed | ckan_adapter | emiss_code=57319 | CKAN package_search result compressed into SourceCandidateCard / Resource list with formats and provenance / FedStat loc | — |
| GC-014 | research | fedstat | fedstat_cpi_russia | passed | fedstat_adapter | geography=Russia; indicator=потребительские цены CPI | ResearchDesignArtifact with CPI and related price-index concepts / Multiple SourceCandidateCards with match_mode values  | — |
| GC-015 | comparative | world_bank | SP.POP.TOTL | passed | world_bank_adapter | geography=['RUS', 'KAZ']; indicator=total population | IntentArtifact with explicit World Bank source preference / World Bank population SourceCandidateCard / CoverageReport f | — |
| GC-016 | simple | fedstat | fedstat_cpi_coverage | passed | fedstat_adapter | geography=Russia; indicator=индекс потребительских цен ЕМИСС | FedStat SourceCandidateCard for CPI-related indicator / CoverageReport listing available periods without final numeric a | — |
| GC-017 | research | world_bank | SL.UEM.TOTL.ZS,NY.GDP.MKTP.KD | passed | world_bank_adapter | geography=Europe; indicator=unemployment GDP | ResearchDesignArtifact with indicator pair and geography group / World Bank source cards for unemployment and GDP / Cove | — |
| GC-018 | no_data | fedstat | fedstat_telegram_users | not_found | ckan_adapter | geography=Russia; indicator=пользователи телеграма | AttemptedSourceLog with FedStat and CKAN searches / NoDataExplanationArtifact with distinction between official statisti | Official regional Telegram-user data is not published by Rosstat or EMISS; FedStat local dump contains no social-media p |
| GC-019 | research | fedstat | fedstat_world_bank_ckan_source_cards | passed | fedstat_adapter | embedding_mode=text-search-doc; query_mode=text-search-query | EmbeddingConfigArtifact declaring provider/model family or credential-aware fallback / EmbeddingInputSpec for source-car | — |
| GC-020 | simple | fedstat | yandex_embedding_split_check | passed | fedstat_adapter | embedding_mode=text-search-doc; query_mode=text-search-query | EmbeddingConfigArtifact with document mode text-search-doc for source-card/chunk docs / EmbeddingConfigArtifact with que | — |
