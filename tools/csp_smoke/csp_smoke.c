/*
 * csp_smoke — single-slave A6N (CSP, mode 8) smoke test under IgH userspace.
 *
 * Targets the A6-200EC on the bench (alias 6, position 0). Reconfigures
 * variable PDO 0x1600 / 0x1A00 to include Mode-of-Operation, drives the
 * CiA 402 state machine to OperationEnabled, then runs a small sine wave
 * on Target Position around the actual position captured at first enable.
 *
 * Run as user in the `ethercat` group. Needs CAP_SYS_NICE for SCHED_FIFO
 * — without it the cyclic loop falls back to the default scheduler (still
 * works at 1 ms with our isolated CPU, just no priority guarantee).
 *
 * Ctrl-C exits — the master is torn down by process exit; the drive
 * watchdog will then drop it to SafeOP within a few cycles.
 */

#define _GNU_SOURCE
#include <errno.h>
#include <math.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sched.h>
#include <sys/mman.h>

#include "ecrt.h"

/* ------------------------------------------------------------------ config */

#define CYCLE_HZ        1000
#define PERIOD_NS       (1000000000L / CYCLE_HZ)
#define RT_CPU          1                /* isolated core, see rt_tuning.md */
#define RT_PRIO         80               /* below kernel watchdog/migration at 99 */

#define SO_VENDOR_ID    0x00400000u
#define SO_PRODUCT      0x00000715u
#define A6_ALIAS        6                /* A6-200EC on the bench */
#define A6_POS          0

#define MODE_CSP        8
#define SINE_AMPL       5000             /* ~0.04 rev on 17-bit encoder */
#define SINE_FREQ_HZ    0.2
#define HOLD_SECONDS    3.0              /* dwell at zero target after enable */

/* --------------------------------------------------------------- IgH state */

static ec_master_t *master;
static ec_domain_t *domain;
static uint8_t *domain_pd;

static int off_ctrl, off_target, off_mode_set;
static int off_status, off_actual, off_mode_disp, off_velocity;

static ec_pdo_entry_info_t rx_entries[] = {
    {0x6040, 0, 16}, /* ControlWord */
    {0x607A, 0, 32}, /* Target Position */
    {0x6060, 0,  8}, /* Mode of Operation */
};
static ec_pdo_entry_info_t tx_entries[] = {
    {0x6041, 0, 16}, /* StatusWord */
    {0x6064, 0, 32}, /* Position Actual */
    {0x6061, 0,  8}, /* Mode Display */
    {0x606C, 0, 32}, /* Velocity Actual */
};
static ec_pdo_info_t rx_pdos[] = { {0x1600, 3, rx_entries} };
static ec_pdo_info_t tx_pdos[] = { {0x1A00, 4, tx_entries} };
static ec_sync_info_t syncs[] = {
    {0, EC_DIR_OUTPUT, 0, NULL,    EC_WD_DISABLE}, /* SM0 MBox out */
    {1, EC_DIR_INPUT,  0, NULL,    EC_WD_DISABLE}, /* SM1 MBox in  */
    {2, EC_DIR_OUTPUT, 1, rx_pdos, EC_WD_ENABLE},  /* SM2 RxPDO    */
    {3, EC_DIR_INPUT,  1, tx_pdos, EC_WD_DISABLE}, /* SM3 TxPDO    */
    {0xff, EC_DIR_INVALID, 0, NULL, EC_WD_DEFAULT}, /* terminator */
};

/* --------------------------------------------------------------- helpers */

#define NSEC_PER_SEC 1000000000L
#define TIMESPEC2NS(T) ((uint64_t)(T).tv_sec * NSEC_PER_SEC + (T).tv_nsec)

static struct timespec ts_add(struct timespec a, struct timespec b)
{
    struct timespec r;
    if (a.tv_nsec + b.tv_nsec >= NSEC_PER_SEC) {
        r.tv_sec  = a.tv_sec + b.tv_sec + 1;
        r.tv_nsec = a.tv_nsec + b.tv_nsec - NSEC_PER_SEC;
    } else {
        r.tv_sec  = a.tv_sec + b.tv_sec;
        r.tv_nsec = a.tv_nsec + b.tv_nsec;
    }
    return r;
}

typedef enum { CIA_INIT, CIA_DISABLED, CIA_READY, CIA_SWITCHED_ON,
               CIA_OP_ENABLED, CIA_QUICK_STOP, CIA_FAULT, CIA_OTHER } cia_t;

static cia_t cia_decode(uint16_t sw)
{
    if ((sw & 0x4F) == 0x40) return CIA_DISABLED;     /* SwitchOnDisabled */
    if ((sw & 0x6F) == 0x21) return CIA_READY;        /* ReadyToSwitchOn */
    if ((sw & 0x6F) == 0x23) return CIA_SWITCHED_ON;
    if ((sw & 0x6F) == 0x27) return CIA_OP_ENABLED;
    if ((sw & 0x6F) == 0x07) return CIA_QUICK_STOP;
    if ((sw & 0x4F) == 0x0F) return CIA_FAULT;        /* Fault reaction active */
    if ((sw & 0x4F) == 0x08) return CIA_FAULT;
    if ((sw & 0x4F) == 0x00) return CIA_INIT;
    return CIA_OTHER;
}
static const char *cia_name(cia_t s)
{
    switch (s) {
    case CIA_INIT:        return "NotReady";
    case CIA_DISABLED:    return "SwitchOnDisabled";
    case CIA_READY:       return "ReadyToSwitchOn";
    case CIA_SWITCHED_ON: return "SwitchedOn";
    case CIA_OP_ENABLED:  return "OperationEnabled";
    case CIA_QUICK_STOP:  return "QuickStopActive";
    case CIA_FAULT:       return "Fault";
    default:              return "Other";
    }
}
static uint16_t cia_command(cia_t s, int fault_reset_pulse)
{
    switch (s) {
    case CIA_FAULT:       return fault_reset_pulse ? 0x80 : 0x00; /* edge */
    case CIA_DISABLED:    return 0x06; /* Shutdown -> Ready */
    case CIA_READY:       return 0x07; /* SwitchOn -> SwitchedOn */
    case CIA_SWITCHED_ON: return 0x0F; /* EnableOperation -> OpEnabled */
    case CIA_OP_ENABLED:  return 0x0F; /* hold */
    default:              return 0x00;
    }
}

/* --------------------------------------------------------------- main loop */

static volatile sig_atomic_t stop = 0;
static void on_sig(int s) { (void)s; stop = 1; }

static void cyclic(void)
{
    struct timespec wake;
    const struct timespec period = {0, PERIOD_NS};
    clock_gettime(CLOCK_MONOTONIC, &wake);
    uint64_t start_ns = TIMESPEC2NS(wake);

    cia_t last = CIA_OTHER;
    int32_t target_zero = 0;
    int enabled_once = 0;
    double enabled_at = 0.0;
    int fault_reset_edge = 1; /* toggle each cycle while in FAULT */
    uint64_t cycle = 0;
    ec_domain_state_t ds_prev = {0};

    while (!stop) {
        wake = ts_add(wake, period);
        if (clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &wake, NULL) != 0)
            break;

        ecrt_master_application_time(master, TIMESPEC2NS(wake));
        ecrt_master_receive(master);
        ecrt_domain_process(domain);

        uint16_t sw     = EC_READ_U16(domain_pd + off_status);
        int32_t  actual = EC_READ_S32(domain_pd + off_actual);
        int8_t   mode_d = EC_READ_S8 (domain_pd + off_mode_disp);
        int32_t  vel    = EC_READ_S32(domain_pd + off_velocity);
        cia_t    st     = cia_decode(sw);

        uint16_t cw = cia_command(st, fault_reset_edge);
        fault_reset_edge = !fault_reset_edge;

        /* Trajectory */
        int32_t target = actual;
        double now_s = (double)(TIMESPEC2NS(wake) - start_ns) / 1e9;
        if (st == CIA_OP_ENABLED) {
            if (!enabled_once) {
                target_zero = actual;
                enabled_at = now_s;
                enabled_once = 1;
                fprintf(stderr, "[%6lu] OpEnabled reached; zero=%d, hold %.1fs then sine ±%d @ %.1fHz\n",
                        (unsigned long)cycle, target_zero, HOLD_SECONDS,
                        SINE_AMPL, SINE_FREQ_HZ);
            }
            double t = now_s - enabled_at;
            if (t < HOLD_SECONDS) {
                target = target_zero;
            } else {
                double s = sin(2.0 * M_PI * SINE_FREQ_HZ * (t - HOLD_SECONDS));
                target = target_zero + (int32_t)(SINE_AMPL * s);
            }
        }

        EC_WRITE_S8 (domain_pd + off_mode_set, MODE_CSP);
        EC_WRITE_U16(domain_pd + off_ctrl,     cw);
        EC_WRITE_S32(domain_pd + off_target,   target);

        /* DC reference clock — use measured monotonic time, not wakeupTime,
           per dc_user example. Sync slaves every cycle. */
        struct timespec t_now;
        clock_gettime(CLOCK_MONOTONIC, &t_now);
        ecrt_master_sync_reference_clock_to(master, TIMESPEC2NS(t_now));
        ecrt_master_sync_slave_clocks(master);

        ecrt_domain_queue(domain);
        ecrt_master_send(master);

        if (st != last) {
            fprintf(stderr, "[%6lu] CiA: %-16s -> %-16s sw=0x%04x cw=0x%04x mode=%d\n",
                    (unsigned long)cycle, cia_name(last), cia_name(st), sw, cw, mode_d);
            last = st;
        }
        if ((cycle % CYCLE_HZ) == 0) {
            ec_domain_state_t ds;
            ecrt_domain_state(domain, &ds);
            if (ds.wc_state != ds_prev.wc_state || ds.working_counter != ds_prev.working_counter) {
                fprintf(stderr, "[%6lu] domain: WC=%u wc_state=%u\n",
                        (unsigned long)cycle, ds.working_counter, ds.wc_state);
            }
            ds_prev = ds;
            fprintf(stderr, "[%6lu] sw=0x%04x %-16s actual=%d target=%d vel=%d mode=%d\n",
                    (unsigned long)cycle, sw, cia_name(st), actual, target, vel, mode_d);
        }
        cycle++;
    }
}

/* --------------------------------------------------------------- main */

int main(void)
{
    signal(SIGINT,  on_sig);
    signal(SIGTERM, on_sig);

    if (mlockall(MCL_CURRENT | MCL_FUTURE) == -1)
        perror("mlockall");

    cpu_set_t set;
    CPU_ZERO(&set);
    CPU_SET(RT_CPU, &set);
    if (sched_setaffinity(0, sizeof(set), &set) == -1)
        perror("sched_setaffinity (continuing on default CPU)");

    master = ecrt_request_master(0);
    if (!master) { fprintf(stderr, "ecrt_request_master failed\n"); return 1; }

    domain = ecrt_master_create_domain(master);
    if (!domain) return 1;

    ec_slave_config_t *sc = ecrt_master_slave_config(master, A6_ALIAS, A6_POS,
                                                     SO_VENDOR_ID, SO_PRODUCT);
    if (!sc) { fprintf(stderr, "ecrt_master_slave_config failed\n"); return 1; }

    if (ecrt_slave_config_pdos(sc, EC_END, syncs)) {
        fprintf(stderr, "ecrt_slave_config_pdos failed\n"); return 1;
    }

    off_ctrl      = ecrt_slave_config_reg_pdo_entry(sc, 0x6040, 0, domain, NULL);
    off_target    = ecrt_slave_config_reg_pdo_entry(sc, 0x607A, 0, domain, NULL);
    off_mode_set  = ecrt_slave_config_reg_pdo_entry(sc, 0x6060, 0, domain, NULL);
    off_status    = ecrt_slave_config_reg_pdo_entry(sc, 0x6041, 0, domain, NULL);
    off_actual    = ecrt_slave_config_reg_pdo_entry(sc, 0x6064, 0, domain, NULL);
    off_mode_disp = ecrt_slave_config_reg_pdo_entry(sc, 0x6061, 0, domain, NULL);
    off_velocity  = ecrt_slave_config_reg_pdo_entry(sc, 0x606C, 0, domain, NULL);
    if (off_ctrl < 0 || off_target < 0 || off_mode_set < 0 ||
        off_status < 0 || off_actual < 0 || off_mode_disp < 0 || off_velocity < 0) {
        fprintf(stderr, "ecrt_slave_config_reg_pdo_entry failed\n"); return 1;
    }

    /* DC sync — AssignActivate 0x300 from ESI OpMode DC, 1 ms cycle, no shift */
    ecrt_slave_config_dc(sc, 0x0300, PERIOD_NS, 0, 0, 0);

    fprintf(stderr, "csp_smoke: activating master, cycle=%ld µs, RT_CPU=%d\n",
            PERIOD_NS / 1000, RT_CPU);
    if (ecrt_master_activate(master)) {
        fprintf(stderr, "ecrt_master_activate failed\n"); return 1;
    }
    domain_pd = ecrt_domain_data(domain);
    if (!domain_pd) return 1;

    struct sched_param sp = { .sched_priority = RT_PRIO };
    if (sched_setscheduler(0, SCHED_FIFO, &sp) == -1)
        perror("sched_setscheduler (continuing with default policy)");

    fprintf(stderr, "csp_smoke: PDO offsets ctrl=%d target=%d mode=%d / status=%d actual=%d disp=%d vel=%d\n",
            off_ctrl, off_target, off_mode_set, off_status, off_actual, off_mode_disp, off_velocity);
    fprintf(stderr, "csp_smoke: Ctrl-C to stop\n");
    cyclic();

    fprintf(stderr, "csp_smoke: exiting (master torn down on process exit)\n");
    return 0;
}
