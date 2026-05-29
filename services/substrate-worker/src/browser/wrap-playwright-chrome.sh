#!/bin/sh
set -eu

find /usr/local/bin/playwright-browsers -type f -name chrome | while IFS= read -r chrome_path; do
  real_path="${chrome_path}.real"

  if [ -f "${real_path}" ]; then
    continue
  fi

  mv "${chrome_path}" "${real_path}"
  cat > "${chrome_path}" <<EOF
#!/bin/sh
namespace="\${SUBSTRATE_BROWSER_NAMESPACE:-ns1}"
pid_file="\${SUBSTRATE_NAMESPACE_PID_FILE:-/var/run/substrate/\${namespace}.pid}"

if [ ! -r "\${pid_file}" ]; then
  echo "Missing namespace PID file: \${pid_file}" >&2
  exit 1
fi

namespace_pid="\$(cat "\${pid_file}")"

# Fake mic/camera injection.
# --use-fake-ui-for-media-stream   suppress permission dialogs
# --use-fake-device-for-media-stream  enable software fake devices
# --use-file-for-fake-audio-capture   stream WAV as microphone (loops)
# --use-file-for-fake-video-capture   stream MJPEG as camera (loops)
# All four flags are added when EITHER file var is set. Individual file
# flags are only appended when the corresponding env var points at an
# existing file, so each can be toggled independently.
fake_media_args=""
if { [ -n "\${SUBSTRATE_FAKE_AUDIO_FILE:-}" ] && [ -f "\${SUBSTRATE_FAKE_AUDIO_FILE}" ]; } || \
   { [ -n "\${SUBSTRATE_FAKE_VIDEO_FILE:-}" ] && [ -f "\${SUBSTRATE_FAKE_VIDEO_FILE}" ]; }; then
  fake_media_args="--use-fake-ui-for-media-stream --use-fake-device-for-media-stream"
  if [ -n "\${SUBSTRATE_FAKE_AUDIO_FILE:-}" ] && [ -f "\${SUBSTRATE_FAKE_AUDIO_FILE}" ]; then
    fake_media_args="\${fake_media_args} --use-file-for-fake-audio-capture=\${SUBSTRATE_FAKE_AUDIO_FILE}"
  fi
  if [ -n "\${SUBSTRATE_FAKE_VIDEO_FILE:-}" ] && [ -f "\${SUBSTRATE_FAKE_VIDEO_FILE}" ]; then
    fake_media_args="\${fake_media_args} --use-file-for-fake-video-capture=\${SUBSTRATE_FAKE_VIDEO_FILE}"
  fi
fi

exec nsenter -t "\${namespace_pid}" -n -- "${real_path}" \${fake_media_args} "\$@"
EOF
  chmod 755 "${chrome_path}"
done
