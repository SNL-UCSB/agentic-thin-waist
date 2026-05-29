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

# If SUBSTRATE_FAKE_AUDIO_FILE is set and the file exists, stream it as the
# browser microphone. Chrome loops the file automatically, which suits a
# music/tone loop. The fake-device flags also suppress the real mic/camera.
fake_audio_args=""
if [ -n "\${SUBSTRATE_FAKE_AUDIO_FILE:-}" ] && [ -f "\${SUBSTRATE_FAKE_AUDIO_FILE}" ]; then
  fake_audio_args="--use-fake-ui-for-media-stream --use-fake-device-for-media-stream --use-file-for-fake-audio-capture=\${SUBSTRATE_FAKE_AUDIO_FILE}"
fi

exec nsenter -t "\${namespace_pid}" -n -- "${real_path}" \${fake_audio_args} "\$@"
EOF
  chmod 755 "${chrome_path}"
done
