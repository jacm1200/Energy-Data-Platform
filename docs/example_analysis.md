# Example analysis

I generated the chart and CSV beside this file from the PostgreSQL daily comparison query on 2026-10-28.

The example has one overlapping UTC day, 2026-01-01:

| Measure | Result | Coverage |
| --- | ---: | ---: |
| Average day-ahead price | 20.125 EUR/MWh | 4 intervals |
| Average temperature | 1.2 °C | 24 observations |
| Average wind speed | 1.0708 m/s | 24 observations |

The four price rows match the committed ENTSO-E parser fixture. They are synthetic test values, not a live market response. I use this output to demonstrate UTC aggregation, joining, coverage counts, and report generation; it is too small to support a market pattern or a relationship claim. Replace them with approved live ENTSO-E data before drawing business conclusions.

The weather values come from the Open-Meteo Historical Weather API for the Madrid coordinates in `.env.example`. Attribute the source as **Weather data by [Open-Meteo.com](https://open-meteo.com/)** under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

Regenerate both outputs after loading the two tables:

```powershell
python -m energy_platform.report
```
