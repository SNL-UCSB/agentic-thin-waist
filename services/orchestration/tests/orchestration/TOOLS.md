# Available Tools for Network Research Orchestration

## run_experiment(experiment_id, capacity_mbps, latency_ms, application, duration_seconds, num_trials, cc_algorithm, aqm_policy, ctp_cluster)
Create and run an experiment against substrate-worker and experiment-api.
- experiment_id (str): Unique experiment identifier.
- capacity_mbps (float): Link download capacity in Mbps.
- latency_ms (float): Added network latency in milliseconds.
- application (str): Target application workflow to run.
- duration_seconds (int): Experiment duration in seconds.
- num_trials (int, optional): Number of repeated trials.
- cc_algorithm (str, optional): Congestion control algorithm.
- aqm_policy (str, optional): Queue discipline/AQM policy used for shaping.
- ctp_cluster (str, optional): Optional CTP identifier or profile name.
Returns: {status, shape, experiment}

## query_results(experiment_id, application, limit)
Query telemetry data for one experiment or filtered result sets.
- experiment_id (str, optional): Specific experiment id to fetch.
- application (str, optional): Application filter.
- limit (int, optional): Maximum results.
Returns: {results}

## validate_ctp(capacity_mbps, latency_ms, ctp_cluster)
Validate CTP selection and service availability for an experiment config.
- capacity_mbps (float, optional): Capacity used to bound candidate intensity.
- latency_ms (float, optional): Latency context used for warnings.
- ctp_cluster (str, optional): Explicit CTP id to verify.
Returns: {valid, ctp_cluster_id, warnings, matches}

## get_available_applications()
List applications supported by orchestration and downstream workflows.
Returns: {applications}

## get_available_cc_algorithms()
List supported congestion-control algorithms.
Returns: {cc_algorithms}

## list_experiments()
List experiments from experiment-api and their current status.
Returns: {experiments}

