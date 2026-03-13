# CTP Clusters

This file documents the **Cross-Traffic Profile (CTP)** clusters that can be attached to experiments.  
The exact cluster IDs and parameters should be synchronized with the CTP service once it is running.

## Current Placeholder Taxonomy

Until real data is available, Claude SHOULD treat these clusters as **examples** of common cross-traffic behaviors:

| Cluster ID          | Description                       | Burstiness | Avg Load (relative) | Notes                                  |
|---------------------|-----------------------------------|-----------|---------------------|----------------------------------------|
| ctp_low_background  | Light background web browsing     | low       | low                 | mostly idle, occasional short flows    |
| ctp_video_moderate  | Competing HD video stream         | medium    | medium              | smooth but sustained throughput demand |
| ctp_bulk_transfer   | Large file download / backup      | low       | high                | long-lived, greedy TCP flows           |
| ctp_chatty_apps     | Many small interactive flows      | high      | low–medium          | e.g., chat, presence, small RPCs       |
| ctp_mobile_bursty   | Bursty mobile traffic             | high      | medium              | strong temporal correlation            |

Claude SHOULD:

- Refer to clusters by their **ID** (e.g., `ctp_video_moderate`) rather than inventing new names.
- Treat burstiness qualitatively (low / medium / high) when reasoning about queueing and latency.
- Prefer **ctp_low_background** when the user does not specify cross-traffic but wants "typical home use".

## Future Integration Notes

- Once the CTP service is live, this file should be regenerated from real telemetry or service metadata.
- The orchestration service can expose an endpoint (e.g., `GET /ctps`) that returns the authoritative list of clusters.
- Claude SHOULD always align its descriptions with the latest version of this file.