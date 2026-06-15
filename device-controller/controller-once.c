#include "raw_client.h"
#include "raw_proto.h"

#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

struct options {
	const char *interface;
	struct raw_request request;
	int timeout_ms;
};

static void print_usage(const char *program)
{
	fprintf(stderr,
		"Usage: %s -i IFACE [--sequence N] --sensor N "
		"[--threshold N] --forced-output 0|1 [--timeout-ms N]\n",
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
	opts->request.threshold = 500;
	opts->timeout_ms = 1000;
	opts->request.sequence = (uint32_t)time(NULL);

	for (int i = 1; i < argc; i++) {
		if ((strcmp(argv[i], "-i") == 0 ||
		    strcmp(argv[i], "--interface") == 0) && i + 1 < argc) {
			opts->interface = argv[++i];
		} else if (strcmp(argv[i], "--sequence") == 0 && i + 1 < argc) {
			if (parse_u32(argv[++i], &opts->request.sequence) < 0)
				return -1;
		} else if (strcmp(argv[i], "--sensor") == 0 && i + 1 < argc) {
			if (parse_u16(argv[++i], &opts->request.sensor) < 0)
				return -1;
		} else if (strcmp(argv[i], "--threshold") == 0 && i + 1 < argc) {
			if (parse_u16(argv[++i], &opts->request.threshold) < 0)
				return -1;
		} else if (strcmp(argv[i], "--forced-output") == 0 &&
		    i + 1 < argc) {
			if (parse_u16(argv[++i], &opts->request.forced_output) < 0 ||
			    opts->request.forced_output > 1)
				return -1;
		} else if (strcmp(argv[i], "--timeout-ms") == 0 && i + 1 < argc) {
			if (parse_int(argv[++i], &opts->timeout_ms) < 0)
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

int main(int argc, char **argv)
{
	struct options opts;
	struct raw_client client;
	struct raw_response response;
	int sent;

	if (parse_options(argc, argv, &opts) < 0) {
		print_usage(argv[0]);
		return 2;
	}

	if (raw_client_open(&client, opts.interface, opts.timeout_ms) < 0) {
		fprintf(stderr, "failed to open raw socket on %s: %s\n",
			opts.interface, strerror(errno));
		return 1;
	}

	sent = raw_client_send_request(&client, &opts.request);
	if (sent < 0) {
		fprintf(stderr, "failed to send request: %s\n", strerror(errno));
		raw_client_close(&client);
		return 1;
	}
	printf("sent request seq=%u bytes=%d sensor=%u threshold=%u forced_output=%u\n",
		opts.request.sequence, sent, opts.request.sensor,
		opts.request.threshold, opts.request.forced_output);

	if (raw_client_receive_response(&client, opts.request.sequence,
	    &response) < 0) {
		fprintf(stderr, "response timeout or receive error: %s\n",
			strerror(errno));
		raw_client_close(&client);
		return 1;
	}

	printf("received response seq=%u output=%u status=%u\n",
		response.sequence, response.output, response.status);
	raw_client_close(&client);
	return response.status == RAW_STATUS_OK ? 0 : 1;
}
