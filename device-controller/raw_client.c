#define _GNU_SOURCE

#include "raw_client.h"
#include "raw_proto.h"

#include <arpa/inet.h>
#include <errno.h>
#include <linux/if_packet.h>
#include <net/if.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>

int raw_client_open(struct raw_client *client, const char *interface,
	int timeout_ms)
{
	struct ifreq ifr;
	struct sockaddr_ll addr;
	struct timeval timeout;

	memset(client, 0, sizeof(*client));
	client->fd = socket(AF_PACKET, SOCK_RAW, htons(RAW_ETHERTYPE));
	if (client->fd < 0)
		return -1;

	memset(&ifr, 0, sizeof(ifr));
	strncpy(ifr.ifr_name, interface, IFNAMSIZ - 1);
	if (ioctl(client->fd, SIOCGIFINDEX, &ifr) < 0)
		goto fail;
	client->ifindex = ifr.ifr_ifindex;

	memset(&ifr, 0, sizeof(ifr));
	strncpy(ifr.ifr_name, interface, IFNAMSIZ - 1);
	if (ioctl(client->fd, SIOCGIFHWADDR, &ifr) < 0)
		goto fail;
	memcpy(client->local_mac, ifr.ifr_hwaddr.sa_data, ETH_ALEN);

	timeout.tv_sec = timeout_ms / 1000;
	timeout.tv_usec = (timeout_ms % 1000) * 1000;
	setsockopt(client->fd, SOL_SOCKET, SO_RCVTIMEO, &timeout,
		sizeof(timeout));

	memset(&addr, 0, sizeof(addr));
	addr.sll_family = AF_PACKET;
	addr.sll_protocol = htons(RAW_ETHERTYPE);
	addr.sll_ifindex = client->ifindex;
	if (bind(client->fd, (struct sockaddr *)&addr, sizeof(addr)) < 0)
		goto fail;

	return 0;

fail:
	raw_client_close(client);
	return -1;
}

void raw_client_close(struct raw_client *client)
{
	if (client->fd >= 0)
		close(client->fd);
	client->fd = -1;
	client->ifindex = 0;
}

int raw_client_send_request(struct raw_client *client,
	const struct raw_request *request)
{
	static const unsigned char broadcast[ETH_ALEN] = {
		0xff, 0xff, 0xff, 0xff, 0xff, 0xff
	};
	struct sockaddr_ll addr;
	unsigned char frame[14 + RAW_PAYLOAD_V2_SIZE];
	unsigned char *payload = frame + 14;

	memcpy(frame, broadcast, ETH_ALEN);
	memcpy(frame + ETH_ALEN, client->local_mac, ETH_ALEN);
	raw_write_be16(frame + 12, RAW_ETHERTYPE);

	memcpy(payload, RAW_MAGIC, 4);
	payload[4] = RAW_VERSION_V2;
	payload[5] = RAW_MSG_REQUEST;
	raw_write_be32(payload + 6, request->sequence);
	raw_write_be16(payload + 10, request->sensor);
	raw_write_be16(payload + 12, request->threshold);
	raw_write_be16(payload + 14, request->forced_output);

	memset(&addr, 0, sizeof(addr));
	addr.sll_family = AF_PACKET;
	addr.sll_ifindex = client->ifindex;
	addr.sll_halen = ETH_ALEN;
	memcpy(addr.sll_addr, broadcast, ETH_ALEN);

	return (int)sendto(client->fd, frame, sizeof(frame), 0,
		(struct sockaddr *)&addr, sizeof(addr));
}

int raw_client_receive_response(struct raw_client *client, uint32_t sequence,
	struct raw_response *response)
{
	unsigned char frame[2048];

	for (;;) {
		ssize_t length = recv(client->fd, frame, sizeof(frame), 0);
		const unsigned char *payload = frame + 14;

		if (length < 0)
			return -1;
		if (length < 14 + RAW_PAYLOAD_V2_SIZE)
			continue;
		if (memcmp(frame + ETH_ALEN, client->local_mac, ETH_ALEN) == 0)
			continue;
		if (raw_read_be16(frame + 12) != RAW_ETHERTYPE)
			continue;
		if (memcmp(payload, RAW_MAGIC, 4) != 0)
			continue;
		if (payload[4] != RAW_VERSION_V2 || payload[5] != RAW_MSG_RESPONSE)
			continue;
		if (raw_read_be32(payload + 6) != sequence)
			continue;

		response->sequence = sequence;
		response->output = raw_read_be16(payload + 10);
		response->status = raw_read_be16(payload + 12);
		return 0;
	}
}
