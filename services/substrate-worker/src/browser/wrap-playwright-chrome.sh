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
exec nsenter -t "\${namespace_pid}" -n -- "${real_path}" "\$@"
EOF
  chmod 755 "${chrome_path}"
done
