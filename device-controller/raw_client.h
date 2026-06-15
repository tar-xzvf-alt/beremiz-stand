#ifndef RAW_CLIENT_H
#define RAW_CLIENT_H

#include <net/ethernet.h>
#include <stdint.h>

struct raw_client {
	int fd;
	int ifindex;
	unsigned char local_mac[ETH_ALEN];
};

struct raw_request {
	uint32_t sequence;
	uint16_t sensor;
	uint16_t threshold;
	uint16_t forced_output;
};

struct raw_response {
	uint32_t sequence;
	uint16_t output;
	uint16_t status;
};

int raw_client_open(struct raw_client *client, const char *interface,
	int timeout_ms);
void raw_client_close(struct raw_client *client);
int raw_client_send_request(struct raw_client *client,
	const struct raw_request *request);
int raw_client_receive_response(struct raw_client *client, uint32_t sequence,
	struct raw_response *response);

#endif
