#define _GNU_SOURCE

#include "raw_proto.h"

#include <arpa/inet.h>
#include <errno.h>
#include <linux/if_packet.h>
#include <net/ethernet.h>
#include <net/if.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>

struct options {
	const char *interface;
	uint32_t sequence;
	uint16_t sensor;
	uint16_t threshold;
	uint16_t forced_output;
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
	opts->threshold = 500;
	opts->timeout_ms = 1000;
	opts->sequence = (uint32_t)time(NULL);

	for (int i = 1; i < argc; i++) {
		if ((strcmp(argv[i], "-i") == 0 || strcmp(argv[i], "--interface") == 0) &&
		    i + 1 < argc) {
			opts->interface = argv[++i];
		} else if (strcmp(argv[i], "--sequence") == 0 && i + 1 < argc) {
			if (parse_u32(argv[++i], &opts->sequence) < 0)
				return -1;
		} else if (strcmp(argv[i], "--sensor") == 0 && i + 1 < argc) {
			if (parse_u16(argv[++i], &opts->sensor) < 0)
				return -1;
		} else if (strcmp(argv[i], "--threshold") == 0 && i + 1 < argc) {
			if (parse_u16(argv[++i], &opts->threshold) < 0)
				return -1;
		} else if (strcmp(argv[i], "--forced-output") == 0 && i + 1 < argc) {
			if (parse_u16(argv[++i], &opts->forced_output) < 0 ||
			    opts->forced_output > 1)
				return -1;
		} else if (strcmp(argv[i], "--timeout-ms") == 0 && i + 1 < argc) {
			if (parse_int(argv[++i], &opts->timeout_ms) < 0)
				return -1;
		} else if (strcmp(argv[i], "-h") == 0 || strcmp(argv[i], "--help") == 0) {
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

static int open_raw_socket(const char *interface, int timeout_ms,
	int *ifindex, unsigned char local_mac[ETH_ALEN])
{
	struct ifreq ifr;
	struct sockaddr_ll addr;
	struct timeval timeout;
	int fd = socket(AF_PACKET, SOCK_RAW, htons(RAW_ETHERTYPE));
	if (fd < 0)
		return -1;

	memset(&ifr, 0, sizeof(ifr));
	strncpy(ifr.ifr_name, interface, IFNAMSIZ - 1);
	if (ioctl(fd, SIOCGIFINDEX, &ifr) < 0)
		goto fail;
	*ifindex = ifr.ifr_ifindex;

	memset(&ifr, 0, sizeof(ifr));
	strncpy(ifr.ifr_name, interface, IFNAMSIZ - 1);
	if (ioctl(fd, SIOCGIFHWADDR, &ifr) < 0)
		goto fail;
	memcpy(local_mac, ifr.ifr_hwaddr.sa_data, ETH_ALEN);

	timeout.tv_sec = timeout_ms / 1000;
	timeout.tv_usec = (timeout_ms % 1000) * 1000;
	setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));

	memset(&addr, 0, sizeof(addr));
	addr.sll_family = AF_PACKET;
	addr.sll_protocol = htons(RAW_ETHERTYPE);
	addr.sll_ifindex = *ifindex;
	if (bind(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0)
		goto fail;

	return fd;

fail:
	close(fd);
	return -1;
}

static int send_request(int fd, int ifindex, const unsigned char local_mac[ETH_ALEN],
	const struct options *opts)
{
	static const unsigned char broadcast[ETH_ALEN] = {
		0xff, 0xff, 0xff, 0xff, 0xff, 0xff
	};
	struct sockaddr_ll addr;
	unsigned char frame[14 + RAW_PAYLOAD_V2_SIZE];
	unsigned char *payload = frame + 14;

	memcpy(frame, broadcast, ETH_ALEN);
	memcpy(frame + ETH_ALEN, local_mac, ETH_ALEN);
	raw_write_be16(frame + 12, RAW_ETHERTYPE);

	memcpy(payload, RAW_MAGIC, 4);
	payload[4] = RAW_VERSION_V2;
	payload[5] = RAW_MSG_REQUEST;
	raw_write_be32(payload + 6, opts->sequence);
	raw_write_be16(payload + 10, opts->sensor);
	raw_write_be16(payload + 12, opts->threshold);
	raw_write_be16(payload + 14, opts->forced_output);

	memset(&addr, 0, sizeof(addr));
	addr.sll_family = AF_PACKET;
	addr.sll_ifindex = ifindex;
	addr.sll_halen = ETH_ALEN;
	memcpy(addr.sll_addr, broadcast, ETH_ALEN);

	return (int)sendto(fd, frame, sizeof(frame), 0,
		(struct sockaddr *)&addr, sizeof(addr));
}

static int receive_response(int fd, const unsigned char local_mac[ETH_ALEN],
	uint32_t sequence, uint16_t *output, uint16_t *status)
{
	unsigned char frame[2048];
	for (;;) {
		ssize_t length = recv(fd, frame, sizeof(frame), 0);
		const unsigned char *payload = frame + 14;
		if (length < 0)
			return -1;
		if (length < 14 + RAW_PAYLOAD_V2_SIZE)
			continue;
		if (memcmp(frame + ETH_ALEN, local_mac, ETH_ALEN) == 0)
			continue;
		if (raw_read_be16(frame + 12) != RAW_ETHERTYPE)
			continue;
		if (memcmp(payload, RAW_MAGIC, 4) != 0)
			continue;
		if (payload[4] != RAW_VERSION_V2 || payload[5] != RAW_MSG_RESPONSE)
			continue;
		if (raw_read_be32(payload + 6) != sequence)
			continue;

		*output = raw_read_be16(payload + 10);
		*status = raw_read_be16(payload + 12);
		return 0;
	}
}

int main(int argc, char **argv)
{
	struct options opts;
	unsigned char local_mac[ETH_ALEN];
	uint16_t output = 0;
	uint16_t status = 0;
	int ifindex = 0;
	int fd;
	int sent;

	if (parse_options(argc, argv, &opts) < 0) {
		print_usage(argv[0]);
		return 2;
	}

	fd = open_raw_socket(opts.interface, opts.timeout_ms, &ifindex, local_mac);
	if (fd < 0) {
		fprintf(stderr, "failed to open raw socket on %s: %s\n",
			opts.interface, strerror(errno));
		return 1;
	}

	sent = send_request(fd, ifindex, local_mac, &opts);
	if (sent < 0) {
		fprintf(stderr, "failed to send request: %s\n", strerror(errno));
		close(fd);
		return 1;
	}
	printf("sent request seq=%u bytes=%d sensor=%u threshold=%u forced_output=%u\n",
		opts.sequence, sent, opts.sensor, opts.threshold, opts.forced_output);

	if (receive_response(fd, local_mac, opts.sequence, &output, &status) < 0) {
		fprintf(stderr, "response timeout or receive error: %s\n", strerror(errno));
		close(fd);
		return 1;
	}

	printf("received response seq=%u output=%u status=%u\n",
		opts.sequence, output, status);
	close(fd);
	return status == RAW_STATUS_OK ? 0 : 1;
}
