# Experiment results

Synthetic model; abstract time units. Error bars are 95% t intervals across independent replication means.

| Scenario | Mean arrival-to-collection | 95% interval | Paired change vs baseline |
|---|---:|---|---|
| baseline | 22.24 | [21.64, 22.83] | — |
| extra_picker | 19.44 | [19.06, 19.83] | -2.80 [-3.13, -2.46] |
| extra_packer | 18.59 | [18.27, 18.92] | -3.65 [-4.04, -3.25] |
| faster_courier | 17.22 | [16.63, 17.81] | -5.02 [-5.06, -4.98] |
| fifo_picking | 22.26 | [21.65, 22.86] | +0.02 [-0.04, +0.08] |

Intervals are per comparison, without multiple-comparison correction. They quantify simulation sampling uncertainty, not uncertainty about real operations.

See report.json for all metrics and configuration, and replications.csv for every measured run.
