# Application Defaults

These defaults define **typical experiment durations and QoE metrics** for each supported application.  
Claude SHOULD use these when the user does not specify an application-specific duration or metrics.

Supported applications (must match system prompt and other services):

- youtube
- netflix
- zoom
- twitch
- tubi
- vimeo
- discord
- google-meet
- ndt
- ping
- iperf3
- wget

## Default Durations and Metrics

| Application  | Default Duration | Type          | Key QoE / Output Metrics                                   |
|--------------|-----------------|---------------|------------------------------------------------------------|
| youtube      | 60s             | Browser (NFA) | startup_time, rebuffer_events, bitrate                     |
| netflix      | 60s             | Browser (NFA) | startup_time, rebuffer_events, bitrate                     |
| zoom         | 120s            | Browser (NFA) | video_quality, audio_quality, packet_loss, end_to_end_latency |
| twitch       | 60s             | Browser (NFA) | startup_time, rebuffer_events, bitrate, frame_drops        |
| tubi         | 60s             | Browser (NFA) | startup_time, rebuffer_events, bitrate                     |
| vimeo        | 60s             | Browser (NFA) | startup_time, rebuffer_events, bitrate                     |
| discord      | 120s            | Browser (NFA) | audio_quality, packet_loss, latency                        |
| google-meet  | 120s            | Browser (NFA) | video_quality, audio_quality, packet_loss, end_to_end_latency |
| ndt          | 30s             | Shell         | download_mbps, upload_mbps, latency_ms                     |
| ping         | 30s             | Shell         | rtt_min, rtt_avg, rtt_max, packet_loss                     |
| iperf3       | 30s             | Shell         | throughput_mbps, jitter_ms, packet_loss                    |
| wget         | 30s             | Shell         | bytes_transferred, throughput_mbps, http_status, returncode |

Claude SHOULD:

- Use the **Default Duration** when the user only specifies an application name.
- Prefer browser-based tests (`Type = Browser (NFA)`) for OTT apps like YouTube/Netflix/Twitch/Tubi/Vimeo/Zoom/Discord/Google Meet.
- Prefer shell tools for lower-level characterization (NDT, ping, iperf3, wget).
- Use `wget` when the intent is to measure HTTP/HTTPS bulk download performance against a specific URL.