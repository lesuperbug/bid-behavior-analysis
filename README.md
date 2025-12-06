Overview
This project examines how non-dispatchable generation, wind and solar, affects bidding behaviour and market power in Alberta's wholesale electricity market. The AESO market is highly concentrated and marked by nearly perfectly inelastic demand, giving large generators significant scope to raise prices above marginal cost. The question is whether increasing penetration of renewables reduces that market power and alters how firms submit bids into the merit order.

Using AESO hourly data from 2020 (internal load, wind/solar output, generator bids), the analysis constructs residual demand curves for Heartland Generation and compares them across hours with high vs. low renewable availability. When wind output is high, residual demand falls sharply and pool prices are much lower-consistent with weakened market power. A two-way fixed-effects model (plant FE x hour FE) shows that wind output causally reduces prices, while solar (negligible at the time) does not. Crucially, the bidding behaviour of thermal generators does not change: firms do not adjust their bids in response to renewables. Instead, renewables mechanically reduce market power by shifting residual demand leftward; the supply curves of incumbents remain stable.

What the Code Does
The repository contains a fully automated pipeline that:
1. Pulls and prepares AESO market data. The script collects hourly market data (merit order, internal load, renewable output), cleans it, and constructs a consistent panel suitable for analysis.
2. Builds key variables used in the research paper. This includes residual demand curves, supply curve reconstructions, and the regressors needed for the econometric model.
3. Runs the same statistical tests described in the paper. You'll get:
    Ordinary Least Squares (OLS) and FE regressions
    Coefficient estimates for renewable output effects
    Statistical significance levels
    Tables that replicate the logic of the paper's empirical findings
4. Outputs clean regression tables. These are printed to the console in a tidy format-ready for interpretation or copying into a document.