#define _GNU_SOURCE
#include <seccomp.h>
#include <sys/resource.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

static void limit(int kind, rlim_t value) {
    struct rlimit bounds = {value, value};
    if (setrlimit(kind, &bounds)) _exit(125);
}
static void rule(scmp_filter_ctx ctx, const char *name) {
    int call = seccomp_syscall_resolve_name(name);
    if (call >= 0 && seccomp_rule_add(ctx, SCMP_ACT_ALLOW, call, 0)) _exit(125);
}
int main(int argc, char **argv) {
    if (argc != 2 || (strcmp(argv[1], "render2") && strcmp(argv[1], "render1") && strcmp(argv[1], "ocr") && strcmp(argv[1], "info") && strcmp(argv[1], "text") && strcmp(argv[1], "version") && strcmp(argv[1], "probe") && strcmp(argv[1], "probe_cpu") && strcmp(argv[1], "probe_memory") && strcmp(argv[1], "probe_output"))) return 125;
    limit(RLIMIT_CPU, 3);
    limit(RLIMIT_AS, 256UL * 1024 * 1024);
    limit(RLIMIT_FSIZE, 0);
    limit(RLIMIT_CORE, 0);
    limit(RLIMIT_NOFILE, 32);
    limit(RLIMIT_NPROC, 0);
    if (clearenv() || setenv("OMP_THREAD_LIMIT", "1", 1) || setenv("LC_ALL", "C", 1) || setenv("HOME", "/nonexistent", 1) || chdir("/")) return 125;
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)) return 125;
    scmp_filter_ctx ctx = seccomp_init(SCMP_ACT_ERRNO(EPERM));
    if (!ctx) return 125;
    const char *allowed[] = {
        "read", "write", "readv", "writev", "close", "close_range", "exit", "exit_group", "execve",
        "fstat", "newfstatat", "stat", "lstat", "statx", "access", "faccessat", "faccessat2",
        "lseek", "pread64", "readlink", "readlinkat", "getdents64", "getcwd", "fcntl", "ioctl",
        "mmap", "mprotect", "munmap", "mremap", "madvise", "brk", "futex", "futex_time64",
        "rt_sigaction", "rt_sigprocmask", "rt_sigreturn", "sigaltstack", "restart_syscall",
        "clock_gettime", "clock_gettime64", "clock_nanosleep", "nanosleep", "gettimeofday",
        "getrandom", "getpid", "getppid", "gettid", "getuid", "geteuid", "getgid", "getegid",
        "set_tid_address", "set_robust_list", "rseq", "arch_prctl", "prlimit64", "getrlimit",
        "sched_getaffinity", "sched_yield", "uname", "sysinfo", "fadvise64", "dup", "dup2", "dup3"
    };
    for (size_t i = 0; i < sizeof(allowed)/sizeof(allowed[0]); i++) rule(ctx, allowed[i]);
    unsigned long mask = O_ACCMODE | O_CREAT | O_TRUNC | O_APPEND | (O_TMPFILE & ~O_DIRECTORY);
    int call = seccomp_syscall_resolve_name("open");
    if (call >= 0 && seccomp_rule_add(ctx, SCMP_ACT_ALLOW, call, 1, SCMP_A1(SCMP_CMP_MASKED_EQ, mask, 0))) return 125;
    call = seccomp_syscall_resolve_name("openat");
    if (call >= 0 && seccomp_rule_add(ctx, SCMP_ACT_ALLOW, call, 1, SCMP_A2(SCMP_CMP_MASKED_EQ, mask, 0))) return 125;
    if (seccomp_load(ctx)) return 125;
    seccomp_release(ctx);
    if (!strcmp(argv[1], "probe_cpu")) {
        volatile unsigned long count = 0;
        while (1) count++;
    }
    if (!strcmp(argv[1], "probe_memory")) {
        void *large = malloc(512UL * 1024 * 1024);
        if (large) return 126;
        puts("bounded");
        return 0;
    }
    if (!strcmp(argv[1], "probe_output")) {
        char block[4096]; memset(block, 'x', sizeof(block));
        while (1) if (write(1, block, sizeof(block)) <= 0) return 0;
    }
    if (!strcmp(argv[1], "probe")) {
        errno = 0;
        if (socket(AF_INET, SOCK_STREAM, 0) != -1 || errno != EPERM) return 126;
        errno = 0;
        if (socket(AF_UNIX, SOCK_STREAM, 0) != -1 || errno != EPERM) return 126;
        errno = 0;
        if (open("/run/butler-pdf/forbidden", O_WRONLY | O_CREAT, 0600) != -1 || errno != EPERM) return 126;
        errno = 0;
        if (fork() != -1 || errno != EPERM) return 126;
        errno = 0;
        if (unlink("/run/butler-pdf/worker.sock") != -1 || errno != EPERM) return 126;
        puts("confined");
        return 0;
    }
    if (!strcmp(argv[1], "render1") || !strcmp(argv[1], "render2")) {
        char *page = !strcmp(argv[1], "render1") ? "1" : "2";
        char *args[] = {"/usr/bin/pdftoppm", "-f", page, "-l", page, "-singlefile", "-gray", "-scale-to", "1600", "-", NULL};
        execv(args[0], args);
    } else if (!strcmp(argv[1], "ocr")) {
        char *args[] = {"/usr/bin/tesseract", "stdin", "stdout", "-l", "eng+fra+spa", "--psm", "6", NULL};
        execv(args[0], args);
    } else if (!strcmp(argv[1], "info")) {
        char *args[] = {"/usr/bin/pdfinfo", "-", NULL};
        execv(args[0], args);
    } else if (!strcmp(argv[1], "version")) {
        char *args[] = {"/usr/bin/pdftotext", "-v", NULL};
        execv(args[0], args);
    } else {
        char *args[] = {"/usr/bin/pdftotext", "-layout", "-enc", "UTF-8", "-eol", "unix", "-", "-", NULL};
        execv(args[0], args);
    }
    return 125;
}
