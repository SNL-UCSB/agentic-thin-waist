/* cca_preload.c — LD_PRELOAD shim that calls setsockopt(TCP_CONGESTION)
 *
 * Why: Linux restricts `sysctl net.ipv4.tcp_congestion_control` writes in
 * non-init network namespaces to algorithms listed in the (global,
 * non-init-writable) tcp_allowed_congestion_control. The substrate worker
 * runs application workflows inside a child netns (ns1), so it can't
 * change ns1's default CCA to BBR / Vegas / Westwood / etc. by sysctl.
 *
 * Per-socket setsockopt(TCP_CONGESTION) is a different code path: any
 * process holding CAP_NET_ADMIN can set ANY loaded CCA, no allowed-list
 * gate. The substrate worker runs privileged, so this works.
 *
 * This shim intercepts socket() and connect() and, if the env var
 * TCP_CCA is set, calls setsockopt on TCP sockets before the connect()
 * completes. Result: the application's TCP flow uses the requested CCA
 * regardless of namespace and regardless of tcp_allowed_congestion_control.
 *
 * Compile: gcc -O2 -fPIC -shared -o cca_preload.so cca_preload.c -ldl
 * Use:     LD_PRELOAD=/usr/local/lib/cca_preload.so TCP_CCA=bbr wget …
 */

#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <unistd.h>

typedef int (*orig_socket_t)(int, int, int);
typedef int (*orig_connect_t)(int, const struct sockaddr *, socklen_t);

static const char *g_cca = NULL;
static int g_verbose = 0;

__attribute__((constructor)) static void cca_preload_init(void) {
    g_cca = getenv("TCP_CCA");
    g_verbose = getenv("TCP_CCA_VERBOSE") != NULL;
    if (g_verbose && g_cca) {
        fprintf(stderr, "[cca_preload] active: TCP_CCA=%s\n", g_cca);
    }
}

static int apply_cca(int sockfd) {
    if (!g_cca || !*g_cca) return 0;
    int rc = setsockopt(sockfd, IPPROTO_TCP, TCP_CONGESTION,
                        g_cca, (socklen_t)strlen(g_cca));
    if (rc < 0 && g_verbose) {
        fprintf(stderr,
                "[cca_preload] setsockopt(TCP_CONGESTION=%s) on fd %d failed: %s\n",
                g_cca, sockfd, strerror(errno));
    } else if (g_verbose) {
        fprintf(stderr,
                "[cca_preload] set TCP_CONGESTION=%s on fd %d\n", g_cca, sockfd);
    }
    return rc;
}

int socket(int domain, int type, int protocol) {
    static orig_socket_t orig = NULL;
    if (!orig) orig = (orig_socket_t)dlsym(RTLD_NEXT, "socket");

    int fd = orig(domain, type, protocol);
    if (fd < 0) return fd;

    /* Only apply to TCP sockets (IPv4 + IPv6). SOCK_STREAM can be OR'd
     * with SOCK_CLOEXEC / SOCK_NONBLOCK on Linux; mask those off. */
    int base_type = type & ~(SOCK_CLOEXEC | SOCK_NONBLOCK);
    if (base_type == SOCK_STREAM &&
        (domain == AF_INET || domain == AF_INET6) &&
        (protocol == 0 || protocol == IPPROTO_TCP)) {
        apply_cca(fd);
    }
    return fd;
}

/* Some libcs / apps call setsockopt() to override after socket(). Re-apply
 * on connect() to make sure the CCA we want sticks even if the app set its
 * own. (Real-world: wget doesn't, but better safe than silently downgraded.)
 */
int connect(int sockfd, const struct sockaddr *addr, socklen_t addrlen) {
    static orig_connect_t orig = NULL;
    if (!orig) orig = (orig_connect_t)dlsym(RTLD_NEXT, "connect");

    if (addr && (addr->sa_family == AF_INET || addr->sa_family == AF_INET6)) {
        /* Best-effort: ignore errors here (fd may already be unsuitable). */
        apply_cca(sockfd);
    }
    return orig(sockfd, addr, addrlen);
}
