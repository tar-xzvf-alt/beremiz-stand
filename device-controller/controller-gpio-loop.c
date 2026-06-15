#define _POSIX_C_SOURCE 199309L

#include "raw_client.h"
#include "raw_proto.h"

#include <errno.h>
#include <gpiod.h>
#include <pthread.h>
#include <sched.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#define CONTROLLER_RT_PRIORITY 80

struct options {
	const char *interface;
	const char *gpio_chip;
	unsigned int gpio_input;
	unsigned int gpio_output;
	uint32_t sequence;
	uint16_t low_sensor;
	uint16_t high_sensor;
	uint16_t threshold;
	int count;
	int timeout_ms;
};

static volatile sig_atomic_t running = 1;

static void handle_signal(int signal_number)
{
	(void)signal_number;
	running = 0;
}

static void configure_realtime(void)
{
	struct sched_param sp = { .sched_priority = CONTROLLER_RT_PRIORITY };

	(void)pthread_setschedparam(pthread_self(), SCHED_FIFO, &sp);
	(void)mlockall(MCL_CURRENT | MCL_FUTURE);
}

static void print_usage(const char *program)
{
	fprintf(stderr,
		"Usage: %s -i IFACE [--gpio-chip PATH] [--gpio-input N] "
		"[--gpio-output N] [--sequence N] [--count N] "
		"[--timeout-ms N] [--low-sensor N] [--high-sensor N] "
		"[--threshold N]\n",
		program);
}

static int parse_u16(const char *text, uint16_t *value)
{
	char *end = NULL;
	unsigned long parsed = strtoul(text, &end, 0);

	if (*text == '\0' || *end != '\0' || parsed > UINT16_MAX)
		return -1;
	*value = (uint16_t)parsed;
	return 0;
}

static int parse_u32(const char *text, uint32_t *value)
{
	char *end = NULL;
	unsigned long parsed = strtoul(text, &end, 0);

	if (*text == '\0' || *end != '\0' || parsed > UINT32_MAX)
		return -1;
	*value = (uint32_t)parsed;
	return 0;
}

static int parse_uint(const char *text, unsigned int *value)
{
	char *end = NULL;
	unsigned long parsed = strtoul(text, &end, 0);

	if (*text == '\0' || *end != '\0' || parsed > UINT32_MAX)
		return -1;
	*value = (unsigned int)parsed;
	return 0;
}

static int parse_int(const char *text, int *value)
{
	char *end = NULL;
	long parsed = strtol(text, &end, 0);

	if (*text == '\0' || *end != '\0' || parsed < 0 || parsed > INT32_MAX)
		return -1;
	*value = (int)parsed;
	return 0;
}

static int parse_options(int argc, char **argv, struct options *opts)
{
	memset(opts, 0, sizeof(*opts));
	opts->sequence = (uint32_t)time(NULL);
	opts->gpio_chip = "/dev/gpiochip4";
	opts->gpio_input = 6;
	opts->gpio_output = 7;
	opts->low_sensor = 400;
	opts->high_sensor = 600;
	opts->threshold = 500;
	opts->count = 0;
	opts->timeout_ms = 1000;

	for (int i = 1; i < argc; i++) {
		if ((strcmp(argv[i], "-i") == 0 ||
		    strcmp(argv[i], "--interface") == 0) && i + 1 < argc) {
			opts->interface = argv[++i];
		} else if (strcmp(argv[i], "--gpio-chip") == 0 && i + 1 < argc) {
			opts->gpio_chip = argv[++i];
		} else if (strcmp(argv[i], "--gpio-input") == 0 && i + 1 < argc) {
			if (parse_uint(argv[++i], &opts->gpio_input) < 0)
				return -1;
		} else if (strcmp(argv[i], "--gpio-output") == 0 && i + 1 < argc) {
			if (parse_uint(argv[++i], &opts->gpio_output) < 0)
				return -1;
		} else if (strcmp(argv[i], "--sequence") == 0 && i + 1 < argc) {
			if (parse_u32(argv[++i], &opts->sequence) < 0)
				return -1;
		} else if (strcmp(argv[i], "--count") == 0 && i + 1 < argc) {
			if (parse_int(argv[++i], &opts->count) < 0)
				return -1;
		} else if (strcmp(argv[i], "--timeout-ms") == 0 && i + 1 < argc) {
			if (parse_int(argv[++i], &opts->timeout_ms) < 0)
				return -1;
		} else if (strcmp(argv[i], "--low-sensor") == 0 && i + 1 < argc) {
			if (parse_u16(argv[++i], &opts->low_sensor) < 0)
				return -1;
		} else if (strcmp(argv[i], "--high-sensor") == 0 && i + 1 < argc) {
			if (parse_u16(argv[++i], &opts->high_sensor) < 0)
				return -1;
		} else if (strcmp(argv[i], "--threshold") == 0 && i + 1 < argc) {
			if (parse_u16(argv[++i], &opts->threshold) < 0)
				return -1;
		} else if (strcmp(argv[i], "-h") == 0 ||
		    strcmp(argv[i], "--help") == 0) {
			print_usage(argv[0]);
			exit(0);
		} else {
			return -1;
		}
	}

	if (opts->interface == NULL)
		return -1;
	return 0;
}

static int setup_gpio(const struct options *opts, struct gpiod_chip **chip,
	struct gpiod_line_request **request, struct gpiod_edge_event_buffer **evbuf)
{
	struct gpiod_line_settings *in_cfg = NULL;
	struct gpiod_line_settings *out_cfg = NULL;
	struct gpiod_line_config *line_cfg = NULL;
	struct gpiod_request_config *req_cfg = NULL;
	unsigned int offsets[2] = { opts->gpio_input, opts->gpio_output };
	int ret = -1;

	*chip = gpiod_chip_open(opts->gpio_chip);
	if (*chip == NULL)
		goto cleanup;

	in_cfg = gpiod_line_settings_new();
	out_cfg = gpiod_line_settings_new();
	line_cfg = gpiod_line_config_new();
	req_cfg = gpiod_request_config_new();
	if (in_cfg == NULL || out_cfg == NULL || line_cfg == NULL ||
	    req_cfg == NULL)
		goto cleanup;

	gpiod_line_settings_set_direction(in_cfg, GPIOD_LINE_DIRECTION_INPUT);
	gpiod_line_settings_set_edge_detection(in_cfg, GPIOD_LINE_EDGE_BOTH);
	gpiod_line_settings_set_direction(out_cfg, GPIOD_LINE_DIRECTION_OUTPUT);
	gpiod_line_settings_set_output_value(out_cfg, 0);

	if (gpiod_line_config_add_line_settings(line_cfg, &offsets[0], 1,
	    in_cfg) < 0)
		goto cleanup;
	if (gpiod_line_config_add_line_settings(line_cfg, &offsets[1], 1,
	    out_cfg) < 0)
		goto cleanup;

	gpiod_request_config_set_consumer(req_cfg, "rockpi-raw-controller");
	*request = gpiod_chip_request_lines(*chip, req_cfg, line_cfg);
	if (*request == NULL)
		goto cleanup;

	*evbuf = gpiod_edge_event_buffer_new(1);
	if (*evbuf == NULL)
		goto cleanup;

	ret = 0;

cleanup:
	if (ret < 0) {
		if (*evbuf != NULL)
			gpiod_edge_event_buffer_free(*evbuf);
		if (*request != NULL)
			gpiod_line_request_release(*request);
		if (*chip != NULL)
			gpiod_chip_close(*chip);
		*evbuf = NULL;
		*request = NULL;
		*chip = NULL;
	}
	if (in_cfg != NULL)
		gpiod_line_settings_free(in_cfg);
	if (out_cfg != NULL)
		gpiod_line_settings_free(out_cfg);
	if (line_cfg != NULL)
		gpiod_line_config_free(line_cfg);
	if (req_cfg != NULL)
		gpiod_request_config_free(req_cfg);
	return ret;
}

int main(int argc, char **argv)
{
	struct options opts;
	struct raw_client client;
	struct gpiod_chip *chip = NULL;
	struct gpiod_line_request *gpio_request = NULL;
	struct gpiod_edge_event_buffer *evbuf = NULL;
	uint32_t sequence;
	int failures = 0;
	int cycle = 0;

	if (parse_options(argc, argv, &opts) < 0) {
		print_usage(argv[0]);
		return 2;
	}

	signal(SIGINT, handle_signal);
	signal(SIGTERM, handle_signal);
	configure_realtime();

	if (setup_gpio(&opts, &chip, &gpio_request, &evbuf) < 0) {
		fprintf(stderr, "failed to setup GPIO %s input=%u output=%u: %s\n",
			opts.gpio_chip, opts.gpio_input, opts.gpio_output,
			strerror(errno));
		return 1;
	}

	if (raw_client_open(&client, opts.interface, opts.timeout_ms) < 0) {
		fprintf(stderr, "failed to open raw socket on %s: %s\n",
			opts.interface, strerror(errno));
		gpiod_edge_event_buffer_free(evbuf);
		gpiod_line_request_release(gpio_request);
		gpiod_chip_close(chip);
		return 1;
	}

	sequence = opts.sequence;
/*
	printf("controller-gpio-loop started iface=%s gpio=%s input=%u output=%u\n",
		opts.interface, opts.gpio_chip, opts.gpio_input, opts.gpio_output);
	fflush(stdout);
*/

	while (running && (opts.count == 0 || cycle < opts.count)) {
		struct gpiod_edge_event *event;
		enum gpiod_edge_event_type event_type;
		struct raw_request request;
		struct raw_response response;
		const char *edge_name;
		int sent;
		int output_value;
		int wait_status = gpiod_line_request_read_edge_events(gpio_request,
			evbuf, 1);

		if (wait_status < 0) {
			if (errno == EINTR)
				break;
			fprintf(stderr, "GPIO edge read failed: %s\n", strerror(errno));
			failures++;
			continue;
		}
		if (wait_status == 0)
			continue;

		event = gpiod_edge_event_buffer_get_event(evbuf, 0);
		if (event == NULL)
			continue;

		event_type = gpiod_edge_event_get_event_type(event);
		edge_name = event_type == GPIOD_EDGE_EVENT_RISING_EDGE ?
			"RISE" : "FALL";

		request.sequence = sequence++;
		request.threshold = opts.threshold;
		if (event_type == GPIOD_EDGE_EVENT_RISING_EDGE) {
			request.sensor = opts.high_sensor;
			request.forced_output = 0;
		} else {
			request.sensor = opts.low_sensor;
			request.forced_output = 1;
		}

		sent = raw_client_send_request(&client, &request);
		if (sent < 0) {
			fprintf(stderr, "cycle=%d seq=%u edge=%s send failed: %s\n",
				cycle + 1, request.sequence, edge_name, strerror(errno));
			failures++;
			continue;
		}

		if (raw_client_receive_response(&client, request.sequence,
		    &response) < 0) {
			fprintf(stderr, "cycle=%d seq=%u edge=%s response timeout: %s\n",
				cycle + 1, request.sequence, edge_name, strerror(errno));
			failures++;
			continue;
		}

		output_value = response.status == RAW_STATUS_OK && response.output != 0;
		if (gpiod_line_request_set_value(gpio_request, opts.gpio_output,
		    output_value) < 0) {
			fprintf(stderr, "cycle=%d seq=%u GPIO output failed: %s\n",
				cycle + 1, request.sequence, strerror(errno));
			failures++;
		}

		cycle++;
		/*
		printf("cycle=%d seq=%u edge=%s sensor=%u threshold=%u forced_output=%u output=%u status=%u gpio_out=%d net_us=%ld total_us=%ld\n",
			cycle, request.sequence, edge_name, request.sensor,
			request.threshold, request.forced_output, response.output,
			response.status, output_value, elapsed_us(&t_sent, &t_recv),
			elapsed_us(&t_edge, &t_done));
		fflush(stdout);
		*/

		if (response.status != RAW_STATUS_OK)
			failures++;
	}

	gpiod_line_request_set_value(gpio_request, opts.gpio_output, 0);
	raw_client_close(&client);
	gpiod_edge_event_buffer_free(evbuf);
	gpiod_line_request_release(gpio_request);
	gpiod_chip_close(chip);
	return failures == 0 ? 0 : 1;
}
