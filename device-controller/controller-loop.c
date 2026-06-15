#define _POSIX_C_SOURCE 199309L

#include "raw_client.h"
#include "raw_proto.h"

#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

struct options {
	const char *interface;
	uint32_t sequence;
	uint16_t low_sensor;
	uint16_t high_sensor;
	uint16_t threshold;
	int count;
	int period_ms;
	int timeout_ms;
};

static void print_usage(const char *program)
{
	fprintf(stderr,
		"Usage: %s -i IFACE [--sequence N] [--count N] "
		"[--period-ms N] [--timeout-ms N] [--low-sensor N] "
		"[--high-sensor N] [--threshold N]\n",
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
	opts->low_sensor = 400;
	opts->high_sensor = 600;
	opts->threshold = 500;
	opts->count = 0;
	opts->period_ms = 1000;
	opts->timeout_ms = 1000;

	for (int i = 1; i < argc; i++) {
		if ((strcmp(argv[i], "-i") == 0 ||
		    strcmp(argv[i], "--interface") == 0) && i + 1 < argc) {
			opts->interface = argv[++i];
		} else if (strcmp(argv[i], "--sequence") == 0 && i + 1 < argc) {
			if (parse_u32(argv[++i], &opts->sequence) < 0)
				return -1;
		} else if (strcmp(argv[i], "--count") == 0 && i + 1 < argc) {
			if (parse_int(argv[++i], &opts->count) < 0)
				return -1;
		} else if (strcmp(argv[i], "--period-ms") == 0 && i + 1 < argc) {
			if (parse_int(argv[++i], &opts->period_ms) < 0)
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

static void sleep_ms(int period_ms)
{
	struct timespec req;

	req.tv_sec = period_ms / 1000;
	req.tv_nsec = (long)(period_ms % 1000) * 1000000L;
	nanosleep(&req, NULL);
}

int main(int argc, char **argv)
{
	struct options opts;
	struct raw_client client;
	int failures = 0;

	if (parse_options(argc, argv, &opts) < 0) {
		print_usage(argv[0]);
		return 2;
	}

	if (raw_client_open(&client, opts.interface, opts.timeout_ms) < 0) {
		fprintf(stderr, "failed to open raw socket on %s: %s\n",
			opts.interface, strerror(errno));
		return 1;
	}

	for (int cycle = 0; opts.count == 0 || cycle < opts.count; cycle++) {
		struct raw_request request;
		struct raw_response response;
		uint16_t expected_output;
		int sent;

		request.sequence = opts.sequence + (uint32_t)cycle;
		request.threshold = opts.threshold;
		if ((cycle % 2) == 0) {
			request.sensor = opts.low_sensor;
			request.forced_output = 1;
			expected_output = 0;
		} else {
			request.sensor = opts.high_sensor;
			request.forced_output = 0;
			expected_output = 1;
		}

		sent = raw_client_send_request(&client, &request);
		if (sent < 0) {
			fprintf(stderr, "cycle=%d seq=%u send failed: %s\n",
				cycle + 1, request.sequence, strerror(errno));
			failures++;
			goto next_cycle;
		}

		if (raw_client_receive_response(&client, request.sequence,
		    &response) < 0) {
			fprintf(stderr, "cycle=%d seq=%u response timeout: %s\n",
				cycle + 1, request.sequence, strerror(errno));
			failures++;
			goto next_cycle;
		}

		printf("cycle=%d seq=%u sensor=%u threshold=%u forced_output=%u output=%u status=%u\n",
			cycle + 1, request.sequence, request.sensor,
			request.threshold, request.forced_output,
			response.output, response.status);
		if (response.status != RAW_STATUS_OK ||
		    response.output != expected_output)
			failures++;

next_cycle:
		fflush(stdout);
		if (opts.count == 0 || cycle + 1 < opts.count)
			sleep_ms(opts.period_ms);
	}

	raw_client_close(&client);
	return failures == 0 ? 0 : 1;
}
